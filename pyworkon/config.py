import getpass
import json
import pwd
from enum import Enum
from pathlib import Path

import yaml
from appdirs import AppDirs
from pydantic import BaseModel, HttpUrl
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

appdirs = AppDirs("pyworkon", "ca-net")

user_config_dir = Path(appdirs.user_config_dir)
user_config_dir.mkdir(parents=True, exist_ok=True)
user_config_file = user_config_dir / "config.yaml"

user_cache_dir = Path(appdirs.user_cache_dir)
user_cache_dir.mkdir(parents=True, exist_ok=True)


class ProviderType(Enum):
    github = "github"
    gitlab = "gitlab"


class Provider(BaseModel):
    name: str
    type: ProviderType = ProviderType.github
    api_url: HttpUrl
    username: str
    password: str


# ruff: noqa: ARG003
class Config(BaseSettings):
    prompt_sign: str = "🖖🏻"
    project_cache: Path = user_cache_dir / "project_cache"
    workspace_dir: Path = Path.home() / "workspace"
    workon_command: str = pwd.getpwnam(getpass.getuser()).pw_shell
    workon_pre_command: str = ""
    providers: list[Provider] = []
    debug: bool = False
    history_file: Path = user_cache_dir / "history"

    model_config = SettingsConfigDict(
        yaml_file=user_config_file,
        yaml_file_encoding="utf-8",
        extra="ignore",
        env_prefix="pyworkon_",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (YamlConfigSettingsSource(settings_cls),)

    def save(self) -> None:
        user_config_file.write_text(
            yaml.dump(json.loads(self.model_dump_json())), encoding="utf-8"
        )


config = Config()
