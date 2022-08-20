from hexbytes import HexBytes

from dlt.common import Wei
from dlt.common.typing import StrAny

from ethereum.eth_source_utils import uint_to_wei


def test_uint_to_wei_tuples() -> None:
    # below the tuple is already converted to dict by recode_tuples prettifier
    decoded = {
        '_pool': '0x05B0BB3c1c320b280501B86706C3551995BC8571', '_user': '0xD2919efDE964a36D16B728f8929ebD45D23bEf1d',
        '_rewardInfo': {
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
                'indexed': False, 'internalType': 'struct IERC20StakingManager.UserReward', 'name': '_rewardInfo', 'type': 'tuple'}
                ],
        'name': 'UserRewardUpdated',
        'type': 'event'
        }
    uint_to_wei({}, decoded, abi["inputs"], HexBytes("0x027f73145bb86dfcdffa5fae931b3cab5ab93c376099cc84b6d2e4985f10e14b"))  # type: ignore
    # all elements in _rewardInfo are Wei
    rewardInfo: StrAny = decoded['_rewardInfo']  # type: ignore
    for v in rewardInfo.values():
        assert isinstance(v, Wei)
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
        print(v)
        assert isinstance(v, exp_t)
