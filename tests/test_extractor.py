from web3 import Web3

from ethereum.ethereum import HTTP_PROVIDER_HEADERS, REQUESTS_TIMEOUT, _get_block_range

def test_get_block_range() -> None:
    w3 = Web3(Web3.HTTPProvider("https://api.roninchain.com/rpc", request_kwargs={"headers": HTTP_PROVIDER_HEADERS, "timeout": REQUESTS_TIMEOUT}))

    # lag is ignored when specific block range is used range
    assert _get_block_range(w3, None, 1200000, None, 100, 10) == (1200000 - 100 + 1, 1200000)
    # max_blocks none -> takes all
    assert _get_block_range(w3, {}, 1200000, None, None, 10) == (0, 1200000)
    # or from previous state
    assert _get_block_range(w3, {"ethereum_current_block": 100000}, 1200000, None, None, 10) == (100000, 1200000)
    # max initial blocks are ignored when we have state
    assert _get_block_range(w3, {"ethereum_current_block": 100000}, 1200000, None, 999, 10) == (100000, 1200000)
    assert _get_block_range(w3, {"ethereum_current_block": 100000}, 1200000, 999998, None, 10) == (1200000 - 999998 + 1, 1200000)
    # get last block from chain
    on_chain_r = _get_block_range(w3, {"ethereum_current_block": 100000}, None, 999998, None, 10)
    assert on_chain_r[1] > 16382237
    assert on_chain_r[0] == on_chain_r[1] - 999998 + 1
