"""Daemon-internal data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentInfo:
    name: str
    status: str


@dataclass
class OpenProject:
    project_id: str
    pane_id: str | None
    session: str | None
    branch: str | None = None
    is_dirty: bool = False
    pr_data: dict[str, Any] | None = None
    pr_fetched_at: float = 0.0
    agents: list[AgentInfo] = field(default_factory=list)
