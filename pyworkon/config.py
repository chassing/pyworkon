from __future__ import annotations

import getpass
import pwd
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Literal
lazy import json
lazy import shlex

from appdirs import AppDirs
from pydantic import BaseModel, HttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict, YamlConfigSettingsSource
lazy import yaml

if TYPE_CHECKING:
    from pydantic_settings import PydanticBaseSettingsSource

appdirs = AppDirs("pyworkon", "ca-net")

user_config_dir = Path(appdirs.user_config_dir)
user_config_dir.mkdir(parents=True, exist_ok=True)
user_config_file = user_config_dir / "config.yaml"

user_cache_dir = Path(appdirs.user_cache_dir)
user_cache_dir.mkdir(parents=True, exist_ok=True)


class ProviderType(StrEnum):
    github = "github"
    gitlab = "gitlab"


class IgnoredReviewRequests(BaseModel, frozen=True):
    """PR authors whose review requests are hidden for one repository."""

    repository: str
    authors: list[str]


class Provider(BaseModel):
    name: str
    type: ProviderType = ProviderType.github
    api_url: HttpUrl
    username: str
    password: str
    ignored_review_requests: list[IgnoredReviewRequests] = []


# ruff: file-ignore[unused-class-method-argument]
class Config(BaseSettings):
    prompt_sign: str = "🖖🏻"
    project_cache: Path = user_cache_dir / "project_cache"
    workspace_dir: Path = Path.home() / "workspace"
    workon_command: str = pwd.getpwnam(getpass.getuser()).pw_shell
    workon_pre_command: str = ""
    ai_agent_command: str = "opencode"
    providers: list[Provider] = []
    debug: bool = False
    history_file: Path = user_cache_dir / "history"
    sidebar_refresh_interval: int = 5
    relay_url: HttpUrl | None = None
    relay_token: str | None = None
    strip_hotkey: str = "ctrl+option+space"
    # The strip's layout mode -- a plain, user-controlled setting, changed
    # only via its right-click "Switch mode" menu item
    # (`StripBridge.toggle_mode()`) and persisted here. Deliberately *not*
    # auto-detected/re-evaluated: an earlier design tried to automatically
    # decide and continuously re-verify this against the real macOS Dock's
    # Accessibility/auto-hide state, and that proved impossible to make
    # reliable across sleep/wake and monitor hotplug.
    strip_mode: Literal["full_width", "beside_dock"] = "full_width"

    model_config = SettingsConfigDict(
        yaml_file=user_config_file,
        yaml_file_encoding="utf-8",
        extra="ignore",
        env_prefix="pyworkon_",
        case_sensitive=False,
    )

    @field_validator("ai_agent_command")
    @classmethod
    def validate_ai_agent_command(cls, value: str) -> str:
        """Require an executable and balanced shell quoting."""
        if (parts := shlex.split(value)) and parts[0]:
            return value
        raise ValueError("AI agent command must contain an executable")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (YamlConfigSettingsSource(settings_cls), env_settings)

    def save(self) -> None:
        """Write this instance back to the YAML file it was loaded from.

        Reads the target path from `self.model_config["yaml_file"]` rather
        than the module-level `user_config_file` -- the two are only ever
        the same value in production (`model_config` is defined using that
        global directly), but a test redirecting `Config.model_config[
        "yaml_file"]` to a temp path (the established pattern in
        `tests/test_ai_agent_command.py`'s `settings_file` fixture, used for
        *reading*) would otherwise have `save()` silently write to the real
        `user_config_file` regardless -- confirmed the hard way: a test that
        called `.save()` through that redirect overwrote the real on-disk
        config with a mostly-default instance.
        """
        yaml_file = self.model_config["yaml_file"]
        if not isinstance(yaml_file, Path):
            msg = f"Config.model_config['yaml_file'] must be a single Path, got {yaml_file!r}"
            raise TypeError(msg)
        yaml_file.write_text(
            yaml.dump(json.loads(self.model_dump_json())), encoding="utf-8"
        )


config = Config()
