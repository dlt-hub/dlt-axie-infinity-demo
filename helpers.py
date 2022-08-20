from genericpath import isfile
import os
import tomlkit

from dlt.common.typing import StrAny

from dlt.pipeline.typing import PipelineCredentials, TLoaderType, credentials_from_dict

"""Config and Secret Helpers

Before we have Pipeline v2 available this glue code is needed to handle credentials and configs via toml files.
"""

def _read_toml(file_name: str) -> StrAny:
    config_file_path = os.path.abspath(os.path.join(".", ".dlt", file_name))

    if os.path.isfile(config_file_path):
        with open(config_file_path, "r", encoding="utf-8") as f:
            # use whitespace preserving parser
            return tomlkit.load(f)
    else:
        return {}


secrets = _read_toml("secrets.toml")
config = _read_toml("config.toml")


def get_credentials(destination: TLoaderType, dataset: str, credentials: StrAny) -> PipelineCredentials:
    full_credentials = {k.upper():v for k,v in credentials.items()}
    full_credentials["CLIENT_TYPE"] = destination
    full_credentials["DEFAULT_DATASET"] = dataset
    return credentials_from_dict(full_credentials)
