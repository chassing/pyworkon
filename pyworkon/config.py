import getpass
import json
import pwd
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from appdirs import AppDirs
from pydantic import (
    BaseModel,
    BaseSettings,
    HttpUrl,
)

appdirs = AppDirs("pyworkon", "ca-net")

user_config_dir = Path(appdirs.user_config_dir)
user_config_dir.mkdir(parents=True, exist_ok=True)
user_config_file = user_config_dir / "config.yaml"

user_cache_dir = Path(appdirs.user_cache_dir)
user_cache_dir.mkdir(parents=True, exist_ok=True)


def yaml_config_settings_source(settings: BaseSettings) -> dict[str, Any]:
    encoding = settings.__config__.env_file_encoding
    if user_config_file.exists():
        cfg = yaml.safe_load(user_config_file.read_text(encoding))
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
    db: Path = user_cache_dir / "db"
    workspace_dir: Path = Path.home() / "workspace"
    workon_command: str = pwd.getpwnam(getpass.getuser()).pw_shell
    workon_pre_command: str = ""
    providers: list[Provider] = []
    debug: bool = False

    class Config:
        extra = "ignore"
        env_file_encoding = "utf-8"
        env_prefix = "pyworkon_"

        @classmethod
        def customise_sources(cls, init_settings, env_settings, file_secret_settings):
            return (init_settings, env_settings, yaml_config_settings_source)

    def save(self):
        user_config_file.write_text(yaml.dump(json.loads(self.json())), encoding=self.__config__.env_file_encoding)


config = Config()
