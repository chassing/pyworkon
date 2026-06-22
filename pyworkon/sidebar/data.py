"""Sidebar data parsing — converts daemon state dicts to sidebar models."""

from __future__ import annotations

import logging
from typing import Any

from pyworkon.daemon.project_mgr import Project
from pyworkon.sidebar.models import AgentInfo, PRInfo, SessionInfo

SessionInfo.model_rebuild(_types_namespace={"Project": Project})

log = logging.getLogger(__name__)


def parse_sidebar_state(
    state: dict[str, Any],
) -> tuple[list[SessionInfo], list[Project], list[str]]:
    """Parse daemon sidebar state into typed models."""
    sessions: list[SessionInfo] = []
    for s in state.get("sessions", []):
        project_data = s.get("project", {})
        try:
            project = Project(**project_data)
        except (ValueError, KeyError):
            continue
        pr = None
        if pr_data := s.get("pr"):
            pr = PRInfo(**pr_data)
        agents = [AgentInfo(**a) for a in s.get("agents", [])]
        sessions.append(
            SessionInfo(
                session_name=s.get("session_name", ""),
                project=project,
                branch=s.get("branch"),
                is_dirty=s.get("is_dirty", False),
                pr=pr,
                agents=agents,
                is_current=False,
                pane_id=s.get("pane_id"),
            )
        )

    projects: list[Project] = []
    for p in state.get("projects", []):
        try:
            projects.append(Project(**p))
        except (ValueError, KeyError):
            continue

    plain_sessions: list[str] = state.get("plain_sessions", [])
    return sessions, projects, plain_sessions
