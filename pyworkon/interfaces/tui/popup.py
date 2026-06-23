"""Popup app — quick project/session switcher with filtering."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from textual.binding import Binding

from pyworkon.interfaces.tui.base import BaseApp
from pyworkon.interfaces.tui.models import PlainSession, ReviewPR, SessionInfo
from pyworkon.interfaces.tui.widgets import SessionCard, SidebarItem

if TYPE_CHECKING:
    from textual.events import Key

    from pyworkon.daemon.project_mgr import Project


class PopupApp(BaseApp):
    """Quick project/session switcher. Filter, select, exit."""

    BINDINGS: ClassVar = [
        *BaseApp.BINDINGS,
        Binding("backspace", "backspace_key", show=False),
    ]

    def _build_items(
        self,
        sessions: list[SessionInfo],
        projects: list[Project],
        plain_names: list[str],
        review_prs: dict[str, list[ReviewPR]],
    ) -> list[SidebarItem]:
        plain = [PlainSession(name) for name in plain_names]
        return [*plain, *sessions, *projects]

    def _on_select(self, item: SidebarItem) -> bool:
        return True

    def _create_session_card(self, session: SessionInfo, **kwargs: Any) -> SessionCard:
        return SessionCard(session, show_ci_checks=False, **kwargs)

    async def on_key(self, event: Key) -> None:
        """Capture printable keys for filtering."""
        if event.character and event.is_printable:
            self._filter_text += event.character
            self._apply_filter()
            event.prevent_default()

    def action_backspace_key(self) -> None:
        if self._filter_text:
            self._filter_text = self._filter_text[:-1]
            self._apply_filter()
