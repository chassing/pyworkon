from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from pyworkon.daemon.project_mgr import Project


class PRStatus(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    PENDING = "pending"
    NONE = "none"


class PRState(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    MERGED = "merged"


class PRInfo(BaseModel):
    number: int
    title: str
    status: PRStatus
    state: PRState = PRState.OPEN
    url: str | None = None


class AgentInfo(BaseModel):
    name: str
    status: str


class SessionInfo(BaseModel):
    session_name: str
    project: Project
    branch: str | None = None
    pr: PRInfo | None = None
    agents: list[AgentInfo] = []
    is_current: bool = False
    pane_id: str | None = None

    model_config = {"arbitrary_types_allowed": True}


@dataclass
class PlainSession:
    """A tmux session without a pyworkon project."""

    name: str
