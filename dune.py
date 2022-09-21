from dune_client.client import DuneClient
from dune_client.query import Query

from dlt.pipeline import Pipeline

from helpers import config, secrets, get_credentials

credentials = get_credentials(config.get("client_type"), config.get("default_dataset"), secrets.get("credentials", {}))


def query_dune_api(api_key, queries):
    """Yields results of dune queries

    Args:
        api_key (str): Dune API Key
        queries (Query): A Dune Query object

    Yields:
        Tuple(str, str, List[DuneRecord]): For each executed query yields a tuple with query id, query name and a list of rows as dictionaries
    """
    dune = DuneClient(api_key)
    for q in queries:
        yield q.query_id, q.name, dune.refresh(q)
    

# two example queries
q1 = Query("rudolfix_axie_evolved", 1283375)
q2 = Query("unionepro_Bridge_Across_Transfers", 522870)

pipeline = Pipeline("dune")
pipeline.create_pipeline(
        credentials,
        working_dir=config["working_dir"]
    )

for r in query_dune_api(str(secrets.get("dune_api_key")), [q1, q2]):
    pipeline.extract(r[2], table_name = r[1])

pipeline.flush()
    

