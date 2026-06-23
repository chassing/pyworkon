"""Dashboard app — full-detail monitoring of all open sessions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pyworkon.interfaces.tui.base import BaseApp
from pyworkon.interfaces.tui.models import ReviewPR, SessionInfo
from pyworkon.interfaces.tui.widgets import SessionCard, SidebarItem

if TYPE_CHECKING:
    from pyworkon.daemon.project_mgr import Project


class DashboardApp(BaseApp):
    """Full-detail monitoring dashboard. Shows sessions and review-requested PRs."""

    def _build_items(
        self,
        sessions: list[SessionInfo],
        projects: list[Project],
        plain_names: list[str],
        review_prs: dict[str, list[ReviewPR]],
    ) -> list[SidebarItem]:
        open_project_ids: set[str] = set()
        for session in sessions:
            pid = session.project.id
            open_project_ids.add(pid)
            if prs := review_prs.get(pid):
                session.review_prs = prs

        virtual: list[SidebarItem] = []
        projects_by_id = {p.id: p for p in projects}
        for pid, prs in review_prs.items():
            if pid in open_project_ids:
                continue
            if project := projects_by_id.get(pid):
                virtual.append(
                    SessionInfo(
                        session_name=project.name,
                        project=project,
                        review_prs=prs,
                    )
                )

        all_sessions = [*sessions, *virtual]
        all_sessions.sort(
            key=lambda s: s.project.name.lower() if isinstance(s, SessionInfo) else ""
        )
        return list(all_sessions)

    def _on_select(self, item: SidebarItem) -> bool:
        return False

    def _create_session_card(self, session: SessionInfo, **kwargs: Any) -> SessionCard:
        return SessionCard(session, show_ci_checks=True, **kwargs)
