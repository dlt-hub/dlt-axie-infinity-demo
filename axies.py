from dlt.common import logger

from dlt.pipeline import Pipeline, CannotRestorePipelineException

from ethereum import get_schema,get_blocks, get_known_contracts
from helpers import config, secrets, get_credentials


credentials = get_credentials(config.get("client_type"), config.get("default_dataset"), secrets.get("credentials", {}))

abi_dir = "abi/abis"
export_schema_path = config.get("export_schema_path")
rpc_url = "https://api.roninchain.com/rpc"

# number of past blocks to get when pipeline is run for a first time
max_blocks = config["ethereum"]["max_blocks"]
max_initial_blocks = config["ethereum"]["max_initial_blocks"]

pipeline = Pipeline("axies")
# create or restore pipeline. this pipeline requires persistent state that is kept in working dir.
logger.info(f"Running pipeline {pipeline.pipeline_name} in {config['working_dir']} with destination {credentials.CLIENT_TYPE}")
try:
    pipeline.restore_pipeline(credentials, config["working_dir"], export_schema_path=export_schema_path)
    logger.info("Pipeline restored")
except CannotRestorePipelineException:
    pipeline.create_pipeline(credentials, schema=get_schema(), working_dir=config["working_dir"], export_schema_path=export_schema_path)
    logger.info("Pipeline created")
    max_blocks = max_initial_blocks

i = get_blocks(rpc_url, max_blocks=max_blocks, max_initial_blocks=10, abi_dir=abi_dir, is_poa=True, supports_batching=False, state=pipeline.state)
# i = get_blocks(rpc_url, max_blocks=1, last_block=16553617, abi_dir=abi_dir, is_poa=True, supports_batching=False, state=None)
pipeline.extract(i, table_name="blocks")
pipeline.extract(get_known_contracts(abi_dir), table_name="known_contracts")
pipeline.normalize()

# if you want to run the whole pipeline in single script just uncomment this line
# pipeline.load()

pipeline.sleep()
