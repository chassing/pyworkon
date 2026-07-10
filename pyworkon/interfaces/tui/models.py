from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

from pyworkon.daemon.models import AgentInfo, PRInfo, ReviewPR
from pyworkon.daemon.project_mgr import Project


class SessionInfo(BaseModel):
    session_name: str
    project: Project
    branch: str | None = None
    is_dirty: bool = False
    pr: PRInfo | None = None
    review_prs: list[ReviewPR] = []
    agents: list[AgentInfo] = []
    is_current: bool = False
    pane_id: str | None = None


@dataclass
class PlainSession:
    """A tmux session without a pyworkon project."""

    name: str
