"""Sidebar data collector — reads from daemon socket."""

from __future__ import annotations

import logging

from pyworkon.daemon.client import DaemonClient, DaemonNotRunningError
from pyworkon.daemon.project_mgr import Project
from pyworkon.sidebar.models import AgentInfo, PRInfo, SessionInfo

SessionInfo.model_rebuild(_types_namespace={"Project": Project})

log = logging.getLogger(__name__)


class SessionDataCollector:
    """Collects sidebar data from the daemon."""

    def __init__(self) -> None:
        self._client: DaemonClient | None = None

    def _get_client(self) -> DaemonClient | None:
        try:
            if self._client is None:
                self._client = DaemonClient()
                self._client.connect()
            return self._client
        except DaemonNotRunningError:
            self._client = None
            return None

    def collect(self) -> list[SessionInfo]:
        """Get open sessions from daemon."""
        client = self._get_client()
        if not client:
            return []
        state = client.get_sidebar_state()
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
        return sessions

    def collect_plain_sessions(self) -> list[str]:
        """Get plain tmux sessions from daemon."""
        client = self._get_client()
        if not client:
            return []
        state = client.get_sidebar_state()
        return state.get("plain_sessions", [])

    def collect_projects(self) -> list[Project]:
        """Get local projects without open sessions from daemon."""
        client = self._get_client()
        if not client:
            return []
        state = client.get_sidebar_state()
        projects: list[Project] = []
        for p in state.get("projects", []):
            try:
                projects.append(Project(**p))
            except (ValueError, KeyError):
                continue
        return projects

    def close_project(self, project_id: str) -> None:
        """Tell daemon to remove a project."""
        if client := self._get_client():
            client.close_project(project_id)
