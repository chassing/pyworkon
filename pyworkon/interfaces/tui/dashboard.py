"""Dashboard app — full-detail monitoring of all open sessions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pyworkon.interfaces.tui.base import BaseApp
from pyworkon.interfaces.tui.widgets import SessionCard, SidebarItem

if TYPE_CHECKING:
    from pyworkon.daemon.project_mgr import Project
    from pyworkon.interfaces.tui.models import SessionInfo


class DashboardApp(BaseApp):
    """Full-detail monitoring dashboard. Shows sessions only, no filtering."""

    def _build_items(
        self,
        sessions: list[SessionInfo],
        projects: list[Project],
        plain_names: list[str],
    ) -> list[SidebarItem]:
        return list(sessions)

    def _on_select(self, item: SidebarItem) -> bool:
        return False

    def _create_session_card(self, session: SessionInfo, **kwargs: Any) -> SessionCard:
        return SessionCard(session, show_ci_checks=True, **kwargs)
