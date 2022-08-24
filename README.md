# Axie Infinity On-Chain Data Scraper
This project uses DLT to get block data from Ronin Network where the Axie activity takes place and decodes transactions and logs of several Axie smart contracts for easier reporting. The data is taken using Ethereum source extractor (which is, temporarily, a part of this project) that is general purpose and can be used for any other network and smart contract group.

## Axie Pipeline
There are two Python scripts that implement the pipeline:
1. `axies.py` is responsible for getting block data from Ethereum extractor and normalizing it.
2. `axies_load.py` is responsible for restoring pipeline and loading the normalized data.

The intention behind splitting pipeline in two scripts is to let them run in parallel in production deployment. It is however trivial to add loading step to `axies.py`. Just uncomment one line there.

ABIs for smart contract that should be decoded are in `abi/abis` folder. See there for a full list but among others we decode main Axie contract (with NFTs, Axie breeding etc), AXS, SLP and USDC tokens, Katana swap and Roning Bridge.

The pipeline uses state to provide incremental loading as described in **Ethereum Source Extractor** chapter. Specifically, it stores the next block to be processed and reads that data on subsequent runts to get only new blocks.

### Configuration & Credentials
*warning: we are still experimenting with the best way to configure pipelines, the procedure below is about to be changed*

Configuration is provides via `.dlt/config.toml` file and environment variables. Credentials are provided via `.dlt/secrets.toml` file and environment variables.

In `config.toml` you can change:

* type of the destination to which data is loaded. default is `bigquery`
* name of dataset/schema where tables will be created. default is `axies_1_local`
* number of past blocks to get when pipeline is run for a first time. default is 10
* maximum number of past blocks to get. default is 300.
* the pipeline working directory and schema export directory but there's no need to change them.

In `secrets.toml` you should provide BigQuery or Redshift credentials, depending on your configuration. For BigQuery take the following from `services.json`
```toml
[credentials]
client_email = <client_email from services.json>
private_key = <private_key from services.json>
project_id = <project_id from services json>
```

For Redshift provide details from your connection string
```toml
[credentials]
dbname=<database name>
host=<ip or host name>
user=<database user name>
password=<password>
```

### Running locally
Just run the scripts with Python. `axies.py` goes first ;> It will take first 10 blocks from the Ronin Network, decode them and prepare load packages. Then use `axies_load.py` to load them into your warehouse.

### Deployment
You can run the pipeline with Docker Composer or on Kubernetes with Helm. Please take a look into `deploy` folder.

Pipeline is configured via production `config.toml` and environment vars (which override any hardcoded and config values.). Credentials from `secrets.toml` are not deployed. A native way using docker/kube secrets is used.

Both deployments will run `axies.py` and `axies_load.py` continuously. You can configure the run sleep (which is quite short as Ronin is producing a block every few seconds)



For Docker Composer
* in `env` set your environment variables
* in `secrets` set private key (bigquery) or password (redshift)
* build the docker image `make build-image`
* run with composer `docker-compose -f deploy/docker-compose.yml up`

For Helm:
Use `values.yaml` to configure Helm. Example for BigQuery:
```yaml
envs:
  bigqueryCredentialsEnv:
    gcpClientEmail: loader@.....
    gcpProjectId: xxxxx-317513
  commonEnv:
    clientType: bigquery
    defaultDataset: axies_1
    sentryDsn: https://......ingest.sentry.io/6672711
secrets:
  gcpPrivateKey: |
    -----BEGIN PRIVATE KEY-----
    MIIEuwIBADANBgkqhkiG9w0BAQEFAASCBKUwggShAgEAAoIBAQCNEN0bL39HmD+S
    ....
    zbGHLwZj0HXqLFXhbAv/0xZPXlZ71NWpi2BpCJRnzU65ftsjePfydfvN6g4mPQ28
    kHQsYKUZk5HPC8FlPvQe
    -----END PRIVATE KEY-----
volumes:
  accessModes:
  - ReadWriteMany
  pipelineVolume:
    storage: 1Gi
  storageClassName: nfs-local

```
Default storage class is `gp2` (AWS). You also need to provide the docker image via docker or similar. See `make build-image` and `make push-image`. Helm chart as for now will use Scalevector public image. 

Then install with Helm:
```
helm install axies deploy/helm-axies/ --namespace axies --create-namespace --values deploy/local/values.yaml --atomic
```

Or Upgrade
```
helm install deploy/helm-axies/ --namespace axies --create-namespace --values deploy/local/values.yaml --atomic
```

### Monitoring
Pipeline provides basic monitoring.

1. Logging can be configured for JSON format and sent to log aggregators.
2. You can configure Sentry for exceptions and tracing.
3. Pipeline scripts expose detailed Prometheus metrics. We'll document that later. (we do not push metrics, they can only be observed)
4. Containers are tagged with DLT and Pipeline versions, commit hash and kubernetes deployment details.

## Ethereum Source Extractor

### Data Store Schema
The data store schema corresponds to the structure of the Ethereum blockchain data. Each X seconds a new **block** is created which contains a list of **transactions**. Transactions may succeed or revert. If transaction succeeds it may generate a list of **logs** which are a kind of programmable execution trace. Transactions are executed by an **account** (which is just a long number) against other **account**. Accounts may belong to people or smart contracts.

* `blocks` table keep information on blocks. `block_number` is a natural primary key. `block_timestamp` tells when block was created. `block_hash` is another unique block id.
* `block_transactions` keeps information on transactions in a block. (`block_number`, `transaction_index`) is a natural primary key. `status` tells if tx succeeded (`1`) or reverted (`2`). There also information on participating accounts and ETH value sent (which is often 0).
* `blocks__transactions__logs` is a trace of each transaction.

the other tables in `blocks` hierarchy are important to experts only.

#### Decoded Data
Ethereum Extractor may also **decode** the logs and the transaction input. Decoding is possible only when we known the ABI (signature) that such data corresponds to. The result of the decoding is a nested and typed dictionary.

Extractor creates the decoded tables as follows:
1. decoded tables for particular contract start with the smart contract name.
2. if table contains decoded transaction input, the `_call_` follows. if logs then `_logs_`
3. name of the function (for call) or event (for log) follows.
4. fields in the table correspond to values in decoded dict.
5. child tables will be created to accommodate nesting
6. every such table contains data that allow to link it to corresponding `block_transactions` or `blocks__transactions__logs` via PKs.

#### Propagated Hints

* `block_timestamp` is propagated to **all** the tables and used to create daily partitions (if warehouse supports that). It is also used to create sorting (or non-unique indexes)
* `block_number` is propagated as above and used for clustering or distribution.


### Using the extractor

### Decoding and ABIs

### Non-Suitability for financial reporting