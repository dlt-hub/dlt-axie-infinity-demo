from functools import reduce
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple, Type, TypedDict, Union, cast, Sequence
from hexbytes import HexBytes
import requests

from dlt.common import Wei, logger
from dlt.common.typing import DictStrAny, StrAny
from dlt.common.schema import Schema
from dlt.common.sources import TDeferred, TItem, defer_iterator, with_retry, with_table_name

from dlt.pipeline import Pipeline
from dlt.pipeline.exceptions import MissingDependencyException

try:
    # import gracefully and produce nice exception that explains the user what to do
    from web3 import Web3, HTTPProvider
    from web3.middleware import geth_poa_middleware
    from eth_typing.evm import ChecksumAddress
    from web3._utils.method_formatters import get_result_formatters
    from web3._utils.rpc_abi import RPC
    from web3.types import LogReceipt, EventData, ABIEvent

    from examples.sources.eth_source_utils import maybe_load_abis, TABIInfo, ABIFunction
    from examples.sources.eth_source_utils import decode_log, decode_tx, fetch_sig_and_decode_log, fetch_sig_and_decode_tx, maybe_update_abi, prettify_decoded, save_abis
except ImportError:
    raise MissingDependencyException("Ethereum Source", ["web3"], "Web3 is a all purpose python library to interact with Ethereum-compatible blockchains.")

# this source gets full state of any Ethereum compatible blockchain.
# - can be easily scaled up to hundreds of parallel extractions (ie. via Airflow)
# - supports retrying if node fails
# - supports multi threaded extraction on single machine via get_deferred_source
# - supports pipeline state so it may be used to just get new blocks when they are available
# - the return value is iterator (or deferred iterator) so still mappings may be used (ie. to decode transactions and logs), see example


HTTP_PROVIDER_HEADERS = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.77 Safari/537.36"
    }
REQUESTS_TIMEOUT = (20, 12)


def get_schema() -> Schema:
    # all Ethereum compatible blockchains have the same schema so we just provide a nice yaml file
    return Pipeline.load_schema_from_file("ethereum/ethereum_schema.yml")


def get_blocks(
    node_url: str, last_block: int = None, max_blocks: int = None, max_initial_blocks: int = None, abi_dir: str = None, lag: int = 2, is_poa: bool = False, supports_batching: bool = True, state: DictStrAny = None
    ) -> Iterator[DictStrAny]:
    return _get_blocks(False, node_url, last_block, max_blocks, max_initial_blocks, abi_dir, lag, is_poa, supports_batching, state)  # type: ignore


def get_blocks_deferred(
    node_url: str, last_block: int = None, max_blocks: int = None, max_initial_blocks: int = None, abi_dir: str = None, lag: int = 2, is_poa: bool = False, supports_batching: bool = True, state: DictStrAny = None
    ) -> Iterator[TDeferred[DictStrAny]]:
    return _get_blocks(True, node_url, last_block, max_blocks, max_initial_blocks, abi_dir, lag, is_poa, supports_batching, state)  # type: ignore


def get_known_contracts(abi_dir: str) -> Iterator[DictStrAny]:
    # load abis and return as tables
    contracts = maybe_load_abis(abi_dir, only_for_decode=False)
    for contract in contracts.values():
        # fields to yield
        yield {k: contract.get(k) for k in ["address", "name", "type", "decimals", "token_name", "token_symbol"]}


def _get_blocks(is_deferred: bool, node_url: str, last_block: int, max_blocks: int, max_initial_blocks: int, abi_dir: str, lag: int, is_poa: bool, supports_batching: bool, state: DictStrAny) -> Union[Iterator[TItem], Iterator[TDeferred[DictStrAny]]]:
    # this code is run only once
    w3 = Web3(Web3.HTTPProvider(node_url, request_kwargs={"headers": HTTP_PROVIDER_HEADERS, "timeout": REQUESTS_TIMEOUT}))
    if is_poa:
        w3.middleware_onion.inject(geth_poa_middleware, layer=0)

    # load abis from abi_dir
    contracts = maybe_load_abis(abi_dir)

    # get chain id
    chain_id = w3.eth.chain_id

    # get block range
    current_block, last_block = _get_block_range(w3, state, last_block, max_blocks, max_initial_blocks, lag)
    if current_block > last_block:
        logger.info("No new blocks. exiting")
        return

    # code within the loop is executed on each yield from iterator
    while current_block <= last_block:
        logger.info(f"requesting block {current_block}")

        @defer_iterator
        @with_retry()
        def _get_block_deferred() -> List[DictStrAny]:
            # get block
            block = [_get_block(w3, current_block, chain_id, supports_batching)]
            # decode all transactions in the block
            block.extend(_decode_block(w3, block[0], abi_dir, contracts))
            # return all together
            return block

        @with_retry()
        def _get_block_retry() -> DictStrAny:
            return _get_block(w3, current_block, chain_id, supports_batching)

        # yield deferred items or actual item values
        if is_deferred:
            yield _get_block_deferred()
        else:
            block = _get_block_retry()
            # yield block
            yield block
            # yield decoded transactions one by one
            yield from _decode_block(w3, block, abi_dir, contracts)
        current_block += 1

    # this code is run after all items were yielded

    # update state, it will be read and stored with the pipeline instance ONLY when whole iterator finishes
    # state participates in the same atomic operation as data
    # this must happen after last yield
    if state is not None:
        logger.info(f"Saving pipeline state for next block {current_block}")
        state["ethereum_current_block"] = current_block


def _get_block_range(w3: Web3, state: DictStrAny, last_block: Optional[int], max_blocks: Optional[int], max_initial_blocks: Optional[int], lag: int) -> Tuple[int, int]:
    # last block is not provided then take the highest block from the chain
    if last_block is None:
        last_block = w3.eth.get_block_number() - lag
        logger.info(f"Got last block {last_block} from chain (with {lag} blocks lag")

    # get current block from the state if available
    state_current_block: int = None
    if state:
        state_current_block = state.get("ethereum_current_block")
    if state_current_block:
        # if max blocks not provided then take all the blocks
        if max_blocks is None:
            max_blocks = last_block + 1
        # get default current block
        current_block = last_block - max_blocks + 1
        current_block = max(state_current_block, current_block)
        logger.info(f"Will continue from saved state ({state_current_block}): obtaining blocks {current_block} to {last_block}")
        if current_block > state_current_block:
            logger.warning(f"Will skip blocks from {state_current_block} to {current_block - 1} because max blocks {max_blocks} was set")
    else:
        # if max blocks not provided then take all the blocks
        if max_initial_blocks is None:
            max_initial_blocks = last_block + 1
        # get default current block
        current_block = last_block - max_initial_blocks + 1
        logger.info(f"Getting blocks from {current_block} to {last_block}")

    assert current_block >= 0
    return current_block, last_block


def _get_block(w3: Web3, current_block: int, chain_id: int, supports_batching: bool) -> DictStrAny:
    logger.info(f"Requesting block {current_block} and transaction receipts")

    # get block with all transaction
    block = dict(w3.eth.get_block(current_block, full_transactions=True))
    # set explicit chain id
    block["chain_id"] = chain_id
    # rename some columns
    block["blockTimestamp"] = block.pop("timestamp")
    block["blockNumber"] = block.pop("number")
    block["blockHash"] = block.pop("hash")
    # get rid of AttributeDict (web3 didn't adopt TypedDict)
    attr_txs = cast(Sequence[Any], block["transactions"])
    transactions: Sequence[DictStrAny] = [dict(tx) for tx in attr_txs]
    # maybe_unknown_inputs: List[str] = []
    for tx in transactions:
        if "accessList" in tx and len(tx["accessList"]) > 0:
            tx["accessList"] = [dict(al) for al in tx["accessList"]]
        # propagate sorting and clustering info
        tx["blockTimestamp"] = block["blockTimestamp"]
        # rename columns
        tx["transactionHash"] = tx.pop("hash")
        # set value as wei
        tx["value"] = Wei.from_int256(tx["value"], 18)
        # overwrite chain_id which is not provided in all cases
        tx["chainId"] = chain_id

    block["transactions"] = transactions
    block["logsBloom"] = bytes(cast(HexBytes, block["logsBloom"]))  # serialize as bytes

    receipts = []
    log_formatters: Callable[..., Any] = get_result_formatters(RPC.eth_getLogs, w3.eth)  # type: ignore
    receipt_formatters: Callable[..., Any] = get_result_formatters(RPC.eth_getTransactionReceipt, w3.eth)  # type: ignore
    provider = cast(HTTPProvider, w3.provider)
    rpc_endpoint_url = provider.endpoint_uri
    if supports_batching:
        # get transaction receipts using batching. web3 does not support batching so we must
        # call node directly and then convert hex numbers to ints
        batch = []
        for idx, tx in enumerate(transactions):
            batch.append({
                "jsonrpc": "2.0",
                "method": "eth_getTransactionReceipt",
                "params": [tx["transactionHash"]],
                "id": idx
            })

        r = requests.post(rpc_endpoint_url, json=batch, timeout=REQUESTS_TIMEOUT, headers=HTTP_PROVIDER_HEADERS)
        r.raise_for_status()
        receipts = r.json()
    else:
        for idx, tx in enumerate(transactions):
            r = requests.post(rpc_endpoint_url, json={
                "jsonrpc": "2.0",
                "method": "eth_getTransactionReceipt",
                "params": [tx["transactionHash"]],
                "id": idx
            }, timeout=REQUESTS_TIMEOUT, headers=HTTP_PROVIDER_HEADERS)
            r.raise_for_status()
            receipts.append(r.json())
    for tx_receipt, tx in zip(receipts, transactions):
        if "result" not in tx_receipt:
            raise ValueError(tx_receipt)
        tx_receipt = receipt_formatters(tx_receipt["result"])
        assert tx_receipt["transactionHash"] == tx["transactionHash"]
        tx["transactionIndex"] = tx_receipt["transactionIndex"]
        tx["status"] = tx_receipt["status"]
        tx["logs"] = [dict(log) for log in log_formatters(tx_receipt["logs"])]
        log: LogReceipt = None
        for log in tx["logs"]:
            log["topic"] = log["topics"][0]
            # log["blockHash"] = block["hash"]

    return block


def _decoded_table_name(contract_name: str, typ_: str, abi_name: str, selector: HexBytes) -> str:
    # many selectors have overloads which would generate identical table names
    # add 1 byte suffix to the table name to reduce that probability sufficiently
    overload_suffix = hex(reduce(lambda p, n: p ^ n, selector))[2:]
    return f"{contract_name}_{typ_}_{abi_name}_{overload_suffix}"


def _decode_block(w3: Web3, block: StrAny, abi_dir: str, contracts: Dict[ChecksumAddress, TABIInfo]) -> Iterator[StrAny]:
    logger.info(f"Decoding {block['blockNumber']}")
    transactions: Sequence[Any] = block["transactions"]
    for tx in transactions:
        tx_info = {
            "blockNumber": tx["blockNumber"],
            "blockTimestamp": tx["blockTimestamp"],
            "transactionHash": tx["transactionHash"],
            "transactionIndex": tx["transactionIndex"],
            "_tx_address": tx["to"],
            "_tx_status": tx["status"]
        }
        # decode transaction
        if tx["to"] in contracts:
            abi_info = contracts[tx["to"]]
            tx_input = HexBytes(tx["input"])
            selector = tx_input[:4]
            tx_abi = cast(ABIFunction, abi_info["selectors"].get(selector))
            tx_args: DictStrAny = None
            fn_name: str = None

            if tx_abi:
                tx_args = decode_tx(w3.codec, tx_abi, tx_input[4:])
                fn_name = tx_abi["name"]
            else:
                if abi_info["unknown_selectors"].get(selector.hex()) is None:
                    # try to decode with an api
                    _, fn_name, tx_args, tx_abi = fetch_sig_and_decode_tx(w3.codec, tx_input)
                    maybe_update_abi(abi_info, selector, tx_abi, block["blockNumber"])

            if tx_args:
                table_name = _decoded_table_name(abi_info["name"], "call", fn_name, selector)
                tx_args =  with_table_name(tx_args, table_name)
                # yield arguments with reference to transaction
                tx_args.update(tx_info)
                logger.debug(f"Decoded tx {tx['transactionHash'].hex()} to {tx['to']} into {table_name}")
                yield prettify_decoded(abi_info, tx_args, tx_abi, selector)

        # decode logs
        log: LogReceipt
        for log in tx["logs"]:
            if log["address"] in contracts:
                abi_info = contracts[log["address"]]
                selector = log["topic"]
                event_abi = cast(ABIEvent, abi_info["selectors"].get(selector))
                event_data: EventData = None
                if event_abi:
                    event_data = decode_log(w3.codec, event_abi, log)
                else:
                    if abi_info["unknown_selectors"].get(selector.hex()) is None:
                        # try to decode with an api
                        _, event_data, event_abi = fetch_sig_and_decode_log(w3.codec, log)
                        maybe_update_abi(abi_info, selector, event_abi, block["blockNumber"])

                if event_data:
                    table_name = _decoded_table_name(abi_info["name"], "logs", event_data["event"], selector)
                    ev_args =  with_table_name(dict(event_data["args"]), table_name)
                    # yield arguments with reference to transaction and log
                    ev_args.update(tx_info)
                    ev_args.update({
                        "logIndex": event_data["logIndex"]
                    })
                    logger.debug(f"Decoded log {event_data['logIndex']} in tx {tx['transactionHash'].hex()} to {tx['to']} into {table_name}")
                    yield prettify_decoded(abi_info, ev_args, event_abi, selector)

    logger.info(f"Block {block['blockNumber']} decoded, saving abi changes")
    if abi_dir:
        # save abi dir after every decoded block to allow multi-threading or awaitable support
        save_abis(abi_dir, contracts.values())
