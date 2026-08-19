"""Relay process settings — sourced from real environment variables.

Unlike `pyworkon.config.Config` (YAML-only, no writable `~/.config` in a
container), the relay always runs as a standalone service, so plain env vars
are the natural configuration source.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class RelaySettings(BaseSettings):
    token: str
    host: str = "127.0.0.1"
    port: int = 8080

    model_config = SettingsConfigDict(env_prefix="relay_")
