from hexbytes import HexBytes
from dlt.common import Decimal
from dlt.common.time import sleep
from dlt.common.typing import DictStrAny
from dlt.pipeline import Pipeline, GCPPipelineCredentials
from dlt.common.arithmetics import numeric_default_context, numeric_default_quantize

from examples.schemas.ethereum import discover_schema
from examples.sources.eth_source_utils import recode_tuples, flatten_batches, abi_to_selector, signature_to_abi, recode_tuples
from examples.sources.ethereum import get_source, get_deferred_source, get_abi_contracts

pipeline = Pipeline("ethereum")

credentials = GCPPipelineCredentials.from_services_file("_secrets/project1234_service.json", "ronin_10")
# credentials = PostgresPipelineCredentials("redshift", "chat_analytics_rasa", "mainnet_6", "loader", "3.73.90.3")

# print(pipeline.root_path)


# "https://mainnet.infura.io/v3/9aa3d95b3bc440fa88ea12eaa4456161"
rpc_url = "https://api.roninchain.com/rpc"
working_dir = "experiments/data/pipelines/ronin"
abi_dir="experiments/data/ronin/abi_target"
pipeline.create_pipeline(credentials, schema=discover_schema(), working_dir=working_dir)
# 16406389
i = get_source(rpc_url, last_block = None, max_blocks = 1, abi_dir=abi_dir, is_poa=True, supports_batching=False, state=pipeline.state)

# extract data from the source. operation is atomic and like all atomic operations in pipeline, it does not raise but returns
# execution status
# map(from_wei_to_eth, i)
pipeline.extract(i, table_name="blocks")
pipeline.extract(get_abi_contracts(abi_dir), table_name="known_contracts")
pipeline.normalize()
# exit(-1)
# pipeline.load()
# print(pipeline.state)

# wait for ethereum network to produce some more blocks
# sleep(20)

# restore the pipeline from the working directory (simulate continuation from the saved state)
pipeline.restore_pipeline(credentials, working_dir)
while True:
    # obtain new iterator (the old one is expired), this time use deferred iterator to allow parallel block reading
    i = get_source(rpc_url, abi_dir=abi_dir, is_poa=True, supports_batching=False, state=pipeline.state)
    pipeline.extract(i, table_name="blocks")
    pipeline.normalize()
    # pipeline.load()
    sleep(5)
# print(pipeline.state)

# this will unpack and load all extracted data
# pipeline.normalize()
# pipeline.flush()
