from copy import deepcopy
import pytest
from web3 import Web3
from eth_typing.evm import ChecksumAddress
from hexbytes import HexBytes
from typing import cast, List

from dlt.common import Wei
from dlt.common.typing import StrAny

from ethereum.eth_source_utils import uint_to_wei, _infer_decimals, maybe_load_abis, decode_tx, ABIFunction, ABIElement, DecodingError, TABIInfo, flatten_batches


def test_uint_to_wei_tuples() -> None:
    # below the tuple is already converted to dict by recode_tuples prettifier
    decoded = {
        '_pool': '0x05B0BB3c1c320b280501B86706C3551995BC8571', '_user': '0xD2919efDE964a36D16B728f8929ebD45D23bEf1d',
        '_rewardInfo': {
            'debitedRewards': 0, 'creditedRewards': 754473549839630794493, 'lastClaimedBlock': 16445977
        },
        '_stakeInfo': {
            'debitedRewards': 0, 'creditedRewards': 754473549839630794493, 'lastClaimedBlock': 16445977
        },
        'blockNumber': 16445977, 'blockTimestamp': 1660942919,
        'transactionHash': HexBytes('0x4115ff4b5d58b5af0bb7221493a31d692d5a2e7ae378622f1bd7688d37973721'),
        'transactionIndex': 1, '_tx_address': '0x05B0BB3c1c320b280501B86706C3551995BC8571', '_tx_status': 1, 'logIndex': 3
    }
    abi = {
        'anonymous': False,
        'inputs': [
            {'indexed': False, 'internalType': 'contract IERC20StakingPool', 'name': '_pool', 'type': 'address'},
            {'indexed': False, 'internalType': 'address', 'name': '_user', 'type': 'address'},
            {'components': 
                [
                    {'internalType': 'uint256', 'name': 'debitedRewards', 'type': 'uint256'},
                    {'internalType': 'uint256', 'name': 'creditedRewards', 'type': 'uint256'},
                    {'internalType': 'uint256', 'name': 'lastClaimedBlock', 'type': 'uint256'}
                ],
                'indexed': False, 'internalType': 'struct IERC20StakingManager.UserReward', 'name': '_rewardInfo', 'type': 'tuple'
            },
            {'components': 
                [
                    {'internalType': 'uint256', 'name': 'debitedRewards', 'type': 'uint256'},
                    {'internalType': 'uint256', 'name': 'creditedRewards', 'type': 'uint256'},
                    {'internalType': 'uint256', 'name': 'lastClaimedBlock', 'type': 'uint256'}
                ],
                'indexed': False, 'internalType': 'struct IERC20StakingManager.UserReward', 'name': '_stakeInfo', 'type': 'tuple'
            }
            ],
        'name': 'UserRewardUpdated',
        'type': 'event'
        }
    uint_to_wei({}, decoded, abi["inputs"], HexBytes("0x027f73145bb86dfcdffa5fae931b3cab5ab93c376099cc84b6d2e4985f10e14b"))  # type: ignore
    # all elements in _rewardInfo are Wei
    rewardInfo: StrAny = decoded['_rewardInfo']  # type: ignore
    for v in rewardInfo.values():
        assert isinstance(v, Wei)
    # same for stake info
    _stakeInfo: StrAny = decoded['_stakeInfo']  # type: ignore
    for v in _stakeInfo.values():
        assert isinstance(v, Wei)

    # and values are wei
    assert rewardInfo["debitedRewards"] == Wei(0)
    assert rewardInfo["creditedRewards"] == Wei(754473549839630794493)
    assert rewardInfo["lastClaimedBlock"] == Wei(16445977)


def test_uint_to_wei_bigint_fitting() -> None:
    decoded = {
        "fit_1": 2**63,
        "fit_2": -2**63,
        "not_fit_1": 2**63 + 1,
        "not_fit_2": -2**63 + 1
    }
    inputs = [
        {'name': 'fit_1', 'type': 'uint63'},
        {'name': 'fit_2', 'type': 'int64'},
        {'name': 'not_fit_1', 'type': 'uint64'},
        {'name': 'not_fit_2', 'type': 'int65'}
    ]
    uint_to_wei({}, decoded, inputs, HexBytes("0x00"))  # type: ignore
    expected_types = {
        "fit_1": int,
        "fit_2": int,
        "not_fit_1": Wei,
        "not_fit_2": Wei
    }
    for v, exp_t in zip(decoded.values(), expected_types.values()):
        assert isinstance(v, exp_t)


def test_infer_decimals() -> None:
    erc20: List[ABIElement] = [{
      "inputs": [
        {
          "name": "_spender",
          "type": "address"
        },
        {
          "name": "_value",
          "type": "uint256"
        }
      ],
      "name": "approve",
      "outputs": [
        {
          "name": "",
          "type": "bool"
        }
      ],
      "type": "function"
        },
    {
      "anonymous": False,
      "inputs": [
        {
          "indexed": True,
          "name": "from",
          "type": "address"
        },
        {
          "indexed": True,
          "name": "to",
          "type": "address"
        },
        {
          "indexed": False,
          "name": "value",
          "type": "uint256"
        }
      ],
      "name": "Transfer",
      "type": "event"
    }
    ]

    contract: TABIInfo = {  # type: ignore
        "name": "ERC20",
        "decimals": 6,
        "address": "0x8Bd81a19420bAd681B7bfc20E703EBd8e253782D"
    }

    # test approve
    assert _infer_decimals(contract, erc20[0]["inputs"], HexBytes("0x095ea7b3"), 1) == 6
    # not the right input index or selector
    assert _infer_decimals(contract, erc20[0]["inputs"], HexBytes("0x095ea7b3"), 0) == 0
    assert _infer_decimals(contract, erc20[0]["inputs"], HexBytes("0x095ea7b3"), 2) == 0
    assert _infer_decimals(contract, erc20[0]["inputs"], HexBytes("0x095ea7b4"), 2) == 0

    # test Transfer event
    assert _infer_decimals(contract, erc20[1]["inputs"], HexBytes("0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"), 2) == 6
    # not right input index
    assert _infer_decimals(contract, erc20[1]["inputs"], HexBytes("0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"), 300) == 0

    # no decimals in contract
    contract["decimals"] = None
    assert _infer_decimals(contract, erc20[0]["inputs"], HexBytes("0x095ea7b3"), 1) == 18
    assert _infer_decimals(contract, erc20[1]["inputs"], HexBytes("0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"), 2) == 18
    del contract["decimals"]   # type: ignore
    assert _infer_decimals(contract, erc20[1]["inputs"], HexBytes("0x095ea7b3"), 1) == 18
    assert _infer_decimals(contract, erc20[1]["inputs"], HexBytes("0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"), 2) == 18

    # number of indexes do not match
    contract["decimals"] = 7
    assert _infer_decimals(contract, erc20[1]["inputs"], HexBytes("0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"), 2) == 7
    erc20[1]["inputs"][2]["indexed"] = True  # type: ignore
    assert _infer_decimals(contract, erc20[1]["inputs"], HexBytes("0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"), 2) == 0


def test_spoofed_tx_decode() -> None:
    w3 = Web3()
    contracts = maybe_load_abis("abi/abis", only_for_decode=True)
    # axie = contracts["0x32950db2a7164aE833121501C797D79E7B79d74C"]
    usdc = contracts[cast(ChecksumAddress, "0x0B7007c13325C48911F73A2daD5FA5dCBf808aDc")]
    # fallback tx without selector
    sel = HexBytes("0x")
    tx_abi = cast(ABIFunction, usdc["selectors"].get(sel))
    # we do not decode fallback functions
    assert tx_abi is None

    # invalid tx input data
    sel = HexBytes("0xa9059cbb")
    tx_abi = cast(ABIFunction, usdc["selectors"].get(sel))
    with pytest.raises(DecodingError):
        decode_tx(w3.codec, tx_abi, sel)
    # tx_input too long
    tx_i = HexBytes("0x000000000000000000000000a1ff30a2448536712c68fea0d74198ac13f7d2900000000000000000000000000000000000000000000000000000000000000003F")
    with pytest.raises(DecodingError):
        decode_tx(w3.codec, tx_abi, tx_i)

  
def test_flatten_batches() -> None:
  decoded = {
    "_dlt_meta": {
    "table_name": 'Axie Contract_call_batchMintAxies'
    }, 
    "_tx_address": '0x32950db2a7164aE833121501C797D79E7B79d74C', 
    "_tx_status": 1, 
    "blockNumber": 17084641, 
    "blockTimestamp": 1662878449, 
    "param_0": [
      Wei('19208'), 
      Wei('96566'), 
      Wei('147036')
    ], 
    "param_1": [
      b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00:<\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x003m\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\\ (\xd3\x00\x00\x00\x00\x00\x00\x01\x00\x01\xc0\x80\xd0\xc2\x10\x00\x00\x00\x01\x00\x08\x10\x80\x83\x02\x00\x01\x00\x00\x10 \x82\x04\x00\x01\x00\x0c', 
      b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01\t\x89\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01\\\xe9\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00]\x95s\x93\x00\x00\x00\x00\x00\x00\x01\x00\x02\xc1\xc0\x80\x82\x04\x00\x00\x00\x01\x00\x10 \x01E\x04\x00\x01\x00\x14\x08A\x05\n\x00\x01\x00\x08', 
      b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x02\x16\xad\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x01\xcf\x87\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00^\x9f\x9c\xaf\x00\x00\x00\x00\x00\x00\x01\x00\x00\x81\x00\x00\x83\x10\x00\x00\x00\x01\x00\x14\x10!\x01\x08\x00\x01\x00\x0c\x08\x80\x83\x08'
    ], 
    "param_2": '0xb0aa40093B8994cFCd1d425e85C7484eDdbd0F63', 
    "transactionHash": HexBytes('0x4fcc884b8182c159328043e4dd0dcbe1ed4a44cfcdacd54369b8e0396d40f66c'), 
    "transactionIndex": 4
  }
  abi = {
    "_dlt_meta": {
    "block": 17084641, 
    "selector": '0x5b43cfca'
    }, 
    "inputs": [
      {
      "name": 'param_0', 
      "type": 'uint256[]'
      }, 
      {
      "name": 'param_1', 
      "type": 'bytes[]'
      }, 
      {
      "name": 'param_2', 
      type: 'address'
      }
    ], 
    "name": 'batchMintAxies', 
    "outputs": [], 
    "type": 'function'
  }

  batch_decoded = deepcopy(decoded)
  flatten_batches(batch_decoded, abi)
  # could not be converted to batch (param_2 not a list)
  assert batch_decoded == decoded

  # mod so can be flattened
  mod_decoded = deepcopy(decoded)
  mod_decoded["param_2"] = ["a", "b", "c"]
  batch_decoded = deepcopy(mod_decoded)
  flatten_batches(batch_decoded, abi)
  assert "batch" in batch_decoded
  for i, batch in enumerate(batch_decoded["batch"]):
    assert batch["param_0"] == mod_decoded["param_0"][i]
    assert batch["param_1"] == mod_decoded["param_1"][i]
    assert batch["param_2"] == mod_decoded["param_2"][i]

  # if batch is present, do not overwrite
  batch_decoded = deepcopy(mod_decoded)
  batch_decoded["batch"] = ["a", "b", "c"]
  flatten_batches(batch_decoded, abi)
  assert batch_decoded["batch"] == ["a", "b", "c"]

  # mod so cannot be flattened due to not equal length
  batch_decoded = deepcopy(mod_decoded)
  batch_decoded["param_1"].pop()
  flatten_batches(batch_decoded, abi)
  assert "batch" not in batch_decoded

  # if param_3 is string but same length as param_0 list, then it could be decoded into batch but should not
  batch_decoded = deepcopy(decoded)
  batch_decoded["param_2"] = "abc"
  flatten_batches(batch_decoded, abi)
  assert "batch" not in batch_decoded