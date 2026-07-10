"""Sidebar data parsing — converts a typed daemon sidebar payload to sidebar models."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pyworkon.interfaces.tui.models import ReviewPR, SessionInfo

if TYPE_CHECKING:
    from pyworkon.daemon.project_mgr import Project
    from pyworkon.daemon.protocol import SidebarStatePayload


def parse_sidebar_state(
    state: SidebarStatePayload,
) -> tuple[list[SessionInfo], list[Project], list[str], dict[str, list[ReviewPR]]]:
    """Convert a daemon sidebar payload into typed sidebar models."""
    sessions = [
        SessionInfo(
            session_name=s.session_name,
            project=s.project,
            branch=s.branch,
            is_dirty=s.is_dirty,
            pr=s.pr,
            agents=s.agents,
            is_current=False,
            pane_id=s.pane_id,
        )
        for s in state.sessions
    ]
    return sessions, state.projects, state.plain_sessions, state.review_prs
