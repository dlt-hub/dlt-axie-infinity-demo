from dlt.common import logger

from dlt.pipeline import Schema, Pipeline, CannotRestorePipelineException

from ethereum import get_blocks, get_known_contracts
from helpers import config, secrets, get_credentials

# get the configuration from config and secret files or environment variables 
# here you can also change the destination (ie. to Redshift) and dataset/schema name we load data into
credentials = get_credentials(config.get("client_type"), config.get("default_dataset"), secrets.get("credentials", {}))

# here we keep the ABIs of the contracts to decode
abi_dir = "abi/abis"
# where the initial Axies schema resides
import_schema_path = config.get("import_schema_path")
# all changes to Ethereum schema are exported here
export_schema_path = config.get("export_schema_path")
# that's Ronin Network JSON RPC node
rpc_url = "https://api.roninchain.com/rpc"

# number of past blocks to get when pipeline is run for a first time
max_initial_blocks = config["ethereum"]["max_initial_blocks"]
# max blocks to get on subsequent runs
max_blocks = config["ethereum"]["max_blocks"]

pipeline = Pipeline("axies")
# create or restore pipeline. this pipeline requires persistent state that is kept in working dir.
logger.info(f"Running pipeline {pipeline.pipeline_name} in {config['working_dir']} with destination {credentials.CLIENT_TYPE}")
try:
    pipeline.restore_pipeline(
        credentials,
        config["working_dir"],
        export_schema_path=export_schema_path
    )
    logger.info("Pipeline restored")
except CannotRestorePipelineException:
    # create new pipeline with basic Ethereum schema
    pipeline.create_pipeline(
        credentials,
        working_dir=config["working_dir"],
        import_schema_path=import_schema_path,
        export_schema_path=export_schema_path
    )
    logger.info("Pipeline created")


def extract() -> None:
    # get iterator with blocks, transactions and decoded transactions and logs
    i = get_blocks(rpc_url, max_blocks=max_blocks, max_initial_blocks=max_initial_blocks, abi_dir=abi_dir, is_poa=True, supports_batching=False, state=pipeline.state)
    # i = get_blocks(rpc_url, max_blocks=1, last_block=16553617, abi_dir=abi_dir, is_poa=True, supports_batching=False, state=None)

    # read the data from iterator
    pipeline.extract(i, table_name="blocks")
    # read the known contracts
    pipeline.extract(get_known_contracts(abi_dir), table_name="known_contracts")
    # normalize the JSON data into tables and prepare load packages
    pipeline.normalize()

    # if you want to run the whole pipeline in single script just uncomment this line
    # pipeline.load()

# this will run the "extract" function once or in a loop if so configured
exit(pipeline.run_in_pool(extract))
