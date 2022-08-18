# Axie Infinity Contracts ABIs

Contract ABIs were created thanks to:

1. https://npm.io/package/axie which provided initial ABIs and addresses
2. Ronin block explorer (https://explorer.roninchain.com/verified-contracts) which provided list of verified contracts (here in `known_contract.json`)
3. Quick and dirty python script `known_contracts_to_abi.py` to merge both and format ABIs as required by Ethereum extractor
4. Ethereum extractor ability to recover signatures and ABIs for unknown selectors
