from dlt.common import logger

from dlt.pipeline import Pipeline, CannotRestorePipelineException

from helpers import config, secrets, get_credentials


# get the configuration from config and secret files or environment variables 
# here you can also change the destination (ie. to Redshift) and dataset/schema name we load data into
credentials = get_credentials(config.get("client_type"), config.get("default_dataset"), secrets.get("credentials", {}))

pipeline = Pipeline("axies")

# restore the pipeline.
logger.info(f"Restoring pipeline {pipeline.pipeline_name} in {config['working_dir']} with destination {credentials.CLIENT_TYPE}")
try:
    pipeline.restore_pipeline(credentials, config["working_dir"])
except CannotRestorePipelineException:
    logger.warning("Pipeline could not be restored. Waiting for some data to be extracted")
else:
    exit(pipeline.load(max_parallel_loads=60))
