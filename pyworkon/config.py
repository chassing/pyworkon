import getpass
import pwd
from enum import Enum
from pathlib import Path
from typing import Any, Dict

import yaml
from pydantic import BaseModel, BaseSettings, HttpUrl

from .isit import XDG_CACHE_HOME, XDG_CONFIG_HOME

CONFIG_HOME = XDG_CONFIG_HOME / "pyworkon"
CONFIG_HOME.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = CONFIG_HOME / "config.yaml"

CACHE_HOME = XDG_CACHE_HOME / "pyworkon"
CACHE_HOME.mkdir(parents=True, exist_ok=True)


def yaml_config_settings_source(settings: BaseSettings) -> Dict[str, Any]:
    encoding = settings.__config__.env_file_encoding
    if CONFIG_FILE.exists():
        cfg = yaml.safe_load(CONFIG_FILE.read_text(encoding))
        return cfg if cfg else {}
    return {}


class ProviderType(Enum):
    github = "github"
    gitlab = "gitlab"
    bitbucket = "bitbucket"


class Provider(BaseModel):
    name: str
    type: ProviderType = ProviderType.github
    api_url: HttpUrl
    username: str
    password: str


class Config(BaseSettings):
    prompt_sign: str = "🖖🏻"
    history_file: Path = CACHE_HOME / "history"
    workspace_dir: Path = Path.home() / "workspace"
    workon_command: str = pwd.getpwnam(getpass.getuser()).pw_shell
    workon_pre_command: str = ""
    providers: list[Provider] = []

    class Config:
        extra = "ignore"
        env_file_encoding = "utf-8"
        env_prefix = "pyworkon_"

        @classmethod
        def customise_sources(cls, init_settings, env_settings, file_secret_settings):
            return (init_settings, env_settings, yaml_config_settings_source)


config = Config()
