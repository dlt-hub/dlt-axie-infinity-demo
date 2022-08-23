from dlt.common import logger

from dlt.pipeline import Pipeline, CannotRestorePipelineException

from helpers import config, secrets, get_credentials


credentials = get_credentials("bigquery", "axies_2", secrets.get("gcp_credentials", {}))

pipeline = Pipeline("axies")

# create or restore pipeline. this pipeline requires persistent state that is kept in working dir.
logger.info(f"Restoring pipeline {pipeline.pipeline_name} in {config['working_dir']} with destination {credentials.CLIENT_TYPE}")
try:
    pipeline.restore_pipeline(credentials, config["working_dir"])
except CannotRestorePipelineException:
    logger.warning("Pipeline could not be restored. Waiting for first extraction....")
else:
    pipeline.load()
    pipeline.sleep()
