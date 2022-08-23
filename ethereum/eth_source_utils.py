import os
import itertools
from hexbytes import HexBytes
import requests
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Union, TypedDict, Tuple, cast

from web3.types import ABI, ABIElement, ABIFunction, ABIEvent, ABIFunctionParams, ABIEventParams,  ABIFunctionComponents, LogReceipt, EventData
from web3._utils.abi import get_abi_input_names, get_abi_input_types, map_abi_data, get_indexed_event_inputs, normalize_event_input_types
from web3._utils.normalizers import BASE_RETURN_NORMALIZERS
from web3._utils.events import get_event_data, get_event_abi_types_for_decoding
from eth_typing import HexStr
from eth_typing.evm import ChecksumAddress
from eth_abi.codec import ABIDecoder, TupleDecoder
from eth_abi.exceptions import DecodingError
from eth_abi.grammar import parse as parse_abi_type
from eth_utils.address import to_checksum_address
from eth_utils.abi import function_abi_to_4byte_selector, event_abi_to_log_topic

from dlt.common import json, Wei, logger
from dlt.common.typing import DictStrAny


class TABIInfo(TypedDict):
    address: str
    name: str
    should_decode: bool
    type: Optional[str]
    decimals: Optional[int]
    token_name: Optional[str]
    token_symbol: Optional[str]
    abi_file: str
    abi: ABI
    unknown_selectors: DictStrAny
    file_content: DictStrAny
    selectors: Dict[HexBytes, ABIElement]


class EthSigItem(TypedDict):
    name: str
    filtered: bool


def abi_to_selector(abi: ABIElement) -> HexBytes:
    if abi["type"] == "event":
        return HexBytes(event_abi_to_log_topic(abi))  # type: ignore
    elif abi["type"] == "function":
        return HexBytes(function_abi_to_4byte_selector(abi))  # type: ignore
    elif abi["type"] == "fallback":
        return HexBytes("0x")
    else:
        raise ValueError(abi)


def maybe_load_abis(abi_dir: str, only_for_decode: bool = True) -> Dict[ChecksumAddress, TABIInfo]:
    contracts: Dict[ChecksumAddress, TABIInfo] = {}
    if abi_dir:
        for abi_file in os.scandir(abi_dir):
            if not abi_file.is_file():
                continue
            address = to_checksum_address(os.path.basename(abi_file).split(".")[0])
            with open(abi_file, mode="r", encoding="utf-8") as f:
                abi: DictStrAny = json.load(f)
                info: TABIInfo = {
                    "address": address,
                    "name": abi['name'],
                    "should_decode": abi.get("should_decode", True),
                    "type": abi.get("type"),
                    "decimals": abi.get("decimals"),
                    "token_name": abi.get("token_name"),
                    "token_symbol": abi.get("token_symbol"),
                    "abi": abi.setdefault("abi", []),
                    "abi_file": abi_file.name,
                    "unknown_selectors": abi.setdefault("unknown_selectors", {}),
                    "file_content": abi,
                    "selectors": {abi_to_selector(a):a for a in abi["abi"] if a["type"] in ["function", "event"]}
                }
                if info["should_decode"] or not only_for_decode:
                    contracts[address] = info
    return contracts


def save_abis(abi_dir: str, abis: Iterable[TABIInfo]) -> None:
    for abi in abis:
        save_path = os.path.join(abi_dir, abi["abi_file"])
        # print(f"saving {save_path}")
        with open(save_path, mode="w", encoding="utf-8") as f:
            json.dump(abi["file_content"], f, indent=2)


def maybe_update_abi(abi_info: TABIInfo, selector: HexBytes, new_abi: ABIElement, in_block: int) -> None:
    add_info = {
        "selector": selector.hex(),
        "block": in_block
    }
    if not new_abi:
        abi_info["unknown_selectors"][selector.hex()] = add_info
        logger.warning(f"Could not resolve selector {selector.hex()} into abi for contract {abi_info['name']} at {abi_info['address']}")
    else:
        logger.warning(f"Decoded selector {selector.hex()} into {new_abi['name']} for contract {abi_info['name']} at {abi_info['address']}")
        # make sure that selector was not added in the mean time (mind the multi-threaded execution)
        if abi_info["selectors"].get(selector) is None:
            new_abi["_dlt_meta"] = add_info  # type: ignore
            abi_info["abi"].append(new_abi)  # type: ignore
            abi_info["selectors"][selector] = new_abi
        else:
            logger.warning(f"Selector {selector.hex()} abi for contract {abi_info['name']} at {abi_info['address']} already added")


def signature_to_abi(sig_type: str, sig: str) -> ABIElement:
    # get name and pass remainder for tokenization
    name, remainder = sig.split("(", maxsplit=1)

    # simple tokenizer that yields "(" ")" "," and tokens between them. empty tokens are ignored
    def tokens() -> Iterator[str]:
        start = 0
        pos = 0
        while pos < len(remainder):
            char = remainder[pos]
            if char in ["(", ")",","]:
                if pos - start > 0:
                    yield remainder[start:pos].strip()
                yield char
                start = pos = pos + 1
            else:
                # move to next "," and return token
                pos += 1

    tokens_gen = tokens()

    abi: ABIElement = {
        "name": name,
        "type": sig_type,  # type: ignore
        "inputs": [],
        "outputs": []
    }

    def _to_components(inputs: List[ABIFunctionComponents], param: str) -> None:
        typ_: str = None
        input_def: ABIFunctionParams = {}
        i = 0

        while tok := next(tokens_gen):
            if tok == "(":
                # step into component parsing
                input_def["components"] = []
                _to_components(input_def["components"], f"{param}_{i}")  # type: ignore
                typ_ = "tuple"
            elif tok == "[]":
                # mod last typ_ to be array
                assert typ_ is not None
                typ_ += tok
            elif tok in [")",","]:
                # add current type
                assert typ_ is not None
                input_def.update({
                    "name": f"{param}_{i}",
                    "type": typ_
                })
                inputs.append(input_def)
                if tok == ")":
                    # up from component parsing
                    return
                else:
                    # prepare for new type
                    input_def = {}
                    typ_ = None
                    i += 1
            else:
                typ_ = tok
    _to_components(abi["inputs"], "param")  # type: ignore

    return abi


def decode_tx(codec: ABIDecoder, abi: ABIFunction, params: HexBytes, raise_on_outstanding_data: bool = False) -> DictStrAny:
    names = get_abi_input_names(abi)
    types = get_abi_input_types(abi)

    def _decode(data: HexBytes) -> Any:
        # this copies decode_abi method but checks if full stream was consumed
        decoders = [
            codec._registry.get_decoder(type_str)
            for type_str in types
        ]

        decoder = TupleDecoder(decoders=decoders)
        stream = codec.stream_class(data)

        decoded = decoder(stream)
        outstanding_bytes = len(params) - stream.tell()
        if outstanding_bytes != 0 and raise_on_outstanding_data:
            raise DecodingError(f"Input stream contains {outstanding_bytes} outstanding bytes that were not decoded")
        return decoded

    decoded = _decode(params)
    normalized = map_abi_data(BASE_RETURN_NORMALIZERS, types, decoded)

    return dict(zip(names, normalized))


def decode_log(codec: ABIDecoder, abi: ABIEvent, log: LogReceipt) -> EventData:
    """Decodes raw log data using provided ABI. In case of missing indexes it will figure out the right combination by trying out all possibilities

    Args:
        codec (ABIDecoder): ABI decoder
        abi (ABIEvent): ABI of the event
        log (LogReceipt): raw log data

    Raises:
        ValueError: DecodeError or ValueError if no right combination of indexes could be found

    Returns:
        EventData: Decoded data

        Will also add/remove indexes in `abi`
    """
    log_topics = log["topics"][1:]
    log_topics_abi = get_indexed_event_inputs(abi)
    log_topic_normalized_inputs = normalize_event_input_types(log_topics_abi)
    log_topic_types = get_event_abi_types_for_decoding(log_topic_normalized_inputs)

    if len(log_topics) != len(log_topic_types):
        # we have incorrect information on topic indexes in abi so we'll recursively try to discover the right combination
        logger.warning(f"""
        abi {abi['name']} does not contain correct index information. expected {len(log_topics)}, got {len(log_topic_types)}. Will scan recursively to recover logs information
        """)
        for indexed_inputs in itertools.combinations(abi["inputs"], len(log_topics)):
            for input_ in abi["inputs"]:
                input_["indexed"] = False
            for input_ in indexed_inputs:
                input_["indexed"] = True

            try:
                # codec detects the incorrect padding, for example it does not allow any other byte to be set for uint8, just the LSB
                rv: EventData = get_event_data(codec, abi, log)
                return rv
            except DecodingError:
                pass
        logger.error(f"Correct index information could not be recovered for {abi['name']}. No combination of indexes allows decoding against provided log data.")
        raise DecodingError("None of the indexed topic combinations decoded correctly")

    return cast(EventData, get_event_data(codec, abi, log))


def fetch_sig(sig_type: str, selector: HexStr) -> Sequence[EthSigItem]:
    r = requests.get(f"https://sig.eth.samczsun.com/api/v1/signatures?{sig_type}={selector}", timeout=(10, 5))
    if r.status_code >= 300:
        r.raise_for_status()
    resp = r.json()
    if not resp["ok"]:
        raise ValueError("sig.eth.samczsun.com response is not ok")

    return resp["result"][sig_type][selector]  # type: ignore


def fetch_sig_and_decode_log(codec: ABIDecoder, log: LogReceipt) -> Tuple[str, EventData, ABIEvent]:
    topic = log["topic"]

    for sig in fetch_sig("event", HexStr(topic.hex())):
        sig_name: str = sig["name"]
        abi = cast(ABIEvent, signature_to_abi("event", sig_name))
        assert abi_to_selector(abi) == topic
        abi["anonymous"] = False
        for input_ in abi["inputs"]:
            input_.setdefault("indexed", False)

        try:
            return sig_name, decode_log(codec, abi, log), abi
        except DecodingError:
            continue

    # no known signatures or nothing could be decoded
    return None, None, None


def fetch_sig_and_decode_tx(codec: ABIDecoder, tx_input: HexBytes) -> Tuple[str, str, DictStrAny, ABIFunction]:
    selector, params = tx_input[:4], tx_input[4:]

    for sig in fetch_sig("function", HexStr(selector.hex())):
        sig_name: str = sig["name"]
        abi = cast(ABIFunction, signature_to_abi("function", sig_name))
        assert abi_to_selector(abi) == selector
        try:
            return sig_name, abi["name"], decode_tx(codec, abi, params), abi
        except DecodingError:
            continue

    # no known signatures or nothing could be decoded
    return None, None, None, None


def prettify_decoded(contract: TABIInfo, decoded: DictStrAny, abi: ABIElement, selector: HexBytes) -> DictStrAny:
    # this gets rid of tuples from decoded and must always go first
    recode_tuples(decoded, abi)
    uint_to_wei(contract, decoded, abi["inputs"], selector)
    flatten_batches(decoded, abi)
    return decoded


def uint_to_wei(contract: TABIInfo, decoded: DictStrAny, inputs: Union[Sequence[ABIFunctionParams], Sequence[ABIEventParams]], selector: HexBytes) -> None:
    # converts all integer types > 2**64 into Wei type
    for input_idx, input_ in enumerate(inputs):

        def uint_list_to_wei(list_v: List[Any], decimals: int = 0) -> None:
            for jdx, l_v in enumerate(list_v):
                if isinstance(l_v, int):
                    list_v[jdx] = Wei.from_int256(l_v, decimals=decimals)
                if isinstance(l_v, List):
                    uint_list_to_wei(l_v, decimals)

        parsed_type = parse_abi_type(input_["type"])
        val = decoded[input_["name"]]
        if isinstance(val, tuple):
            raise ValueError("Tuple found in decoded data: " + str(val))
        # dicts are results of recoding tuples by recode_tuples so `components` must be present
        if isinstance(val, dict):
            # convert recursively for tuples
            uint_to_wei(contract, val, input_["components"], selector)  # type: ignore
        else:
            # one of the basic types
            bit_size = 0
            if parsed_type.base in ["uint", "int"]:
                bit_size = int(parsed_type.sub)
            elif parsed_type.base in ["ufixed", "fixed"]:
                bit_size = int(parsed_type[0])
            # bigint is signed so we must have 63 bit integer to fit (one bit is sign). in case of signed integers they fit in bigint 1:1
            if bit_size > 63 and parsed_type.base[0] == "u" or bit_size > 64 and parsed_type.base[0] != "u":
                # not fitting in int -> convert to wei
                decimals = _infer_decimals(contract, inputs, selector, input_idx)
                if parsed_type.is_array:
                    assert isinstance(val, list)
                    uint_list_to_wei(val, decimals)
                else:
                    decoded[input_["name"]] = Wei.from_int256(val, decimals=decimals)


def flatten_batches(decoded: DictStrAny, abi: ABIElement) -> None:
    batch = []
    for input_ in abi["inputs"]:
        prev_len: int = None
        decoded_val = decoded.get(input_["name"])
        if decoded_val is not None:
            if isinstance(decoded_val, Sequence):
                if prev_len is None or prev_len == len(decoded_val):
                    batch.append(input_["name"])
                    prev_len = len(decoded_val)
                else:
                    # list length not equal so this is not a batch
                    return
            else:
                # not all elements are lists so this is not a batch
                return

    decoded["batch"] = [{n:decoded[n][i] for n in batch} for i in range(prev_len)]
    for n in batch:
        del decoded[n]


def recode_tuples(decoded: DictStrAny, abi: ABIElement) -> None:
    # replaces tuples with dicts representing named tuples
    def _replace_component(decoded_component: Iterable[Any], inputs: Sequence[ABIFunctionComponents]) -> Dict[str, Any]:
        # convert tuple to dict
        recoded_dict = {input_["name"]:item for item, input_ in zip(decoded_component, inputs)}
        for key, item, input_ in zip(recoded_dict.keys(), recoded_dict.values(), inputs):
            if input_["type"] == "tuple" and isinstance(item, Sequence):
                recoded = _replace_component(item, input_["components"])
                recoded_dict[key] = recoded
        return recoded_dict

    input_: ABIFunctionParams = None
    for input_ in abi["inputs"]:  # type: ignore
        decoded_val = decoded.get(input_["name"])
        if input_["type"] == "tuple" and isinstance(decoded_val, Iterable):
            decoded[input_["name"]] = _replace_component(decoded_val, input_["components"])


KNOWN_SELECTORS_DECIMALS = {
    # Transfer
    (HexBytes("0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"), 2, 2): 18,
    # Approval
    (HexBytes("0x8c5be1e5ebec7d5bd14f71427d1e84f3dd0314c0f7b2291e5b200ac8c7c3b925"), 2, 2): 18,
    # approve
    (HexBytes("0x095ea7b3"), 1, 0): 18,
    # transfer
    (HexBytes("0xa9059cbb"), 1, 0): 18
}


def _infer_decimals(contract: TABIInfo, inputs: Union[Sequence[ABIFunctionParams], Sequence[ABIEventParams]], selector: HexBytes, input_idx: int) -> int:
    # try to infer decimals from known selectors (ERC20 functions and events) and from known abis
    index_count = 0
    if len(selector) == 32:
        index_count = len([arg for arg in inputs if arg.get("indexed") is True])
    decimals = KNOWN_SELECTORS_DECIMALS.get((selector, input_idx, index_count), 0)
    if decimals > 0:
        # if ERC20 transfer/log is detected try to get correct decimal value from abi
        decimals = contract.get("decimals", None)
        if decimals is None:
            decimals = 18
            logger.warning(f"Detected ERC20 transfer/approve but contract {contract['name']} ABI has no decimal property specified, using 18 decimals")
        logger.debug(f"Got decimals {decimals} for token {contract['name']} at {contract['address']}")
    return decimals
