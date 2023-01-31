from dlt.common import logger

from dlt.pipeline import Schema, Pipeline, CannotRestorePipelineException

from ethereum import get_blocks
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


pipeline = Pipeline("axies")
# create new pipeline with basic Ethereum schema
pipeline.create_pipeline(
    credentials,
    working_dir=config["working_dir"],
    import_schema_path=import_schema_path,
    export_schema_path=export_schema_path
)
logger.info("Pipeline created")
    


def extract(from_block, to_block) -> None:
    # normalize the JSON data into tables and prepare load packages
    pipeline.normalize()

    # if you want to run the whole pipeline in single script just uncomment this line
    pipeline.load()

    # get iterator with blocks, transactions and decoded transactions and logs
    i = get_blocks(rpc_url, last_block=to_block, max_blocks=to_block-from_block+1, abi_dir=abi_dir, is_poa=True, supports_batching=False)
    # read the data from iterator
    pipeline.extract(i, table_name="blocks")

missing_blocks = """
WITH block_pairs AS (
  SELECT block_number, LAG(block_number,1) OVER (ORDER BY block_number) as prev_block  FROM blocks
)
SELECT prev_block + 1 as start_block,
      block_number - 1 as end_block,
      block_number - prev_block as gap
FROM block_pairs WHERE block_number - prev_block > 1
ORDER BY start_block
"""

with pipeline.sql_client() as c:
    print(c.fully_qualified_dataset_name())
    with c.execute_query(missing_blocks) as recs:
        for row in recs:
            extract(row[0], row[1])


# normalize the JSON data into tables and prepare load packages
pipeline.normalize()

# if you want to run the whole pipeline in single script just uncomment this line
pipeline.load()