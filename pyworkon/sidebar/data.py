from __future__ import annotations

import json
import logging
import time

from diskcache import Cache

from pyworkon.config import config
from pyworkon.project import Project, project_manager
from pyworkon.sidebar.models import AgentInfo, PRInfo, SessionInfo
from pyworkon.tmux_mgr import tmux_manager

SessionInfo.model_rebuild(_types_namespace={"Project": Project})

log = logging.getLogger(__name__)

_PR_CACHE_TTL = 60.0
_PR_DISK_CACHE_DIR = str(config.project_cache) + "_pr"


class SessionDataCollector:
    """Collects session data from tmux, git, and provider APIs."""

    def __init__(self) -> None:
        self._pr_memory: dict[tuple[str, str], tuple[PRInfo | None, float]] = {}
        self._pr_disk = Cache(directory=_PR_DISK_CACHE_DIR)
        self._cached_session_names: set[str] = set()
        self._cached_sessions: list[tuple[str, str | None]] = []
        self._load_disk_cache()

    def _load_disk_cache(self) -> None:
        """Load all PR data from disk cache into memory."""
        for key in self._pr_disk:
            if not isinstance(key, str):
                continue
            raw = self._pr_disk.get(key)
            if not raw:
                continue
            project_id, branch = key.split("|", 1)
            pr_info = PRInfo(**json.loads(raw)) if raw != "null" else None
            self._pr_memory[project_id, branch] = (pr_info, time.monotonic())

    def collect(self) -> list[SessionInfo]:
        """Build a list of SessionInfo from all pyworkon tmux sessions."""
        current_session = tmux_manager.get_current_session()
        session_list = self._get_sessions()
        all_agents = tmux_manager.batch_collect_agents()
        sessions: list[SessionInfo] = []

        for session_name, project_id in session_list:
            if not project_id:
                continue

            try:
                project = project_manager.get(project_id)
            except KeyError:
                continue

            branch = project.get_current_branch()
            agents = [
                AgentInfo(name=name, status=status)
                for name, status in all_agents.get(session_name, [])
            ]

            sessions.append(
                SessionInfo(
                    session_name=session_name,
                    project=project,
                    branch=branch,
                    agents=agents,
                    is_current=session_name == current_session,
                )
            )

        return sessions

    def _get_sessions(self) -> list[tuple[str, str | None]]:
        """Get sessions with caching — only re-fetch project IDs when session list changes."""
        current_sessions = set(tmux_manager.list_sessions())
        if current_sessions != self._cached_session_names:
            self._cached_session_names = current_sessions
            self._cached_sessions = tmux_manager.list_sessions_with_project_id()
        return self._cached_sessions

    def get_cached_pr(self, project_id: str, branch: str) -> PRInfo | None:
        """Get PR info from cache."""
        cache_key = (project_id, branch)
        if cache_key in self._pr_memory:
            pr_info, _ = self._pr_memory[cache_key]
            return pr_info
        return None

    def is_pr_fresh(self, project_id: str, branch: str) -> bool:
        """Check if PR info is in cache and still within TTL."""
        cache_key = (project_id, branch)
        if cache_key in self._pr_memory:
            _, timestamp = self._pr_memory[cache_key]
            return time.monotonic() - timestamp < _PR_CACHE_TTL
        return False

    def collect_plain_sessions(self) -> list[str]:
        """Get tmux sessions without a pyworkon project ID."""
        return [name for name, pid in self._get_sessions() if not pid]

    def collect_projects(self) -> list[Project]:
        """Get local projects that don't have an open tmux session."""
        session_project_ids = {pid for _, pid in self._get_sessions() if pid}
        return [
            p
            for p in project_manager.list(local=True)
            if p.id not in session_project_ids
        ]

    def update_pr_cache(
        self, project_id: str, branch: str, pr_info: PRInfo | None
    ) -> None:
        """Store PR info in memory and disk cache."""
        self._pr_memory[project_id, branch] = (pr_info, time.monotonic())
        disk_key = f"{project_id}|{branch}"
        self._pr_disk.set(disk_key, pr_info.model_dump_json() if pr_info else "null")
