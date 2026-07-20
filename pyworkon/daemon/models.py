"""Daemon data models.

`OpenProject` is daemon-internal-only runtime state (plain dataclass, never
serialized directly). The rest are pydantic domain models shared with the wire
protocol (`daemon/protocol.py`) and consumed by the TUI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from pydantic import BaseModel


class PRStatus(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    PENDING = "pending"
    NONE = "none"


class PRState(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    MERGED = "merged"


class PRReviewStatus(StrEnum):
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    PENDING = "pending"
    NONE = "none"


class CICheck(BaseModel):
    name: str
    status: PRStatus
    url: str | None = None


class PRInfo(BaseModel):
    number: int
    title: str
    status: PRStatus
    state: PRState = PRState.OPEN
    url: str | None = None
    review_status: PRReviewStatus = PRReviewStatus.NONE
    is_draft: bool = False
    ci_checks: list[CICheck] = []


class ReviewPR(BaseModel):
    number: int
    title: str
    url: str
    author: str
    is_draft: bool = False


class AgentInfo(BaseModel):
    pid: int
    name: str
    status: str


@dataclass
class OpenProject:
    project_id: str
    pane_id: str | None
    session: str | None
    branch: str | None = None
    is_dirty: bool = False
    pr_data: PRInfo | None = None
    pr_fetched_at: float = 0.0
    agents: list[AgentInfo] = field(default_factory=list)
