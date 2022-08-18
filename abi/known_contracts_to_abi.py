from eth_utils.address import to_checksum_address

from dlt.common import json
from examples.sources.eth_source_utils import maybe_load_abis, save_abis, TABIInfo

# load all abis
abi_dir = "abi/abis"
contracts = maybe_load_abis(abi_dir, only_for_decode=False)

# json from ronin block explorer
with open("abi/known_contracts.json", "r", encoding="utf-8") as f:
    ronin_known_contracts = json.load(f)

for r_c in ronin_known_contracts["pageProps"]["allVerifiedContracts"]:
    address = to_checksum_address(r_c["address"])
    if address in contracts:
        contract = contracts[address]
        print(f"contract {address} with name {contract['name']} already exists, modding")
        content = contract["file_content"]
    else:
        print(f"contract {address} with name {r_c['contractName']} is new, creating")
        content = {
            "should_decode": False
        }
        contract: TABIInfo = {
            "file_content": content
        }
        contracts[address] = contract
    # set props
    content["name"] = r_c["contractName"]
    if "type" in r_c:
        content["type"] = r_c["type"]
        # if no abi: set standard abi
        if "abi" not in content:
            with open(f"experiments/data/ronin/{r_c['type']}.json", "r", encoding="utf-8") as f:
                content["abi"] = json.load(f)
    if "decimals" in r_c:
        content["decimals"] = r_c["decimals"]
    if "tokenName" in r_c:
        content["token_name"] = r_c["tokenName"]
    if "tokenSymbol" in r_c:
        content["token_symbol"] = r_c["tokenSymbol"]
    if "nftUnit" in r_c:
        content["token_symbol"] = r_c["nftUnit"]

for address, contract in contracts.items():
    contract["abi_file"] = address + ".json"

save_abis(abi_dir + "_target", contracts.values())