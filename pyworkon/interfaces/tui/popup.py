"""Popup app — quick project/session switcher with filtering."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from textual.binding import Binding

from pyworkon.interfaces.tui.base import BaseApp
from pyworkon.interfaces.tui.models import PlainSession, SessionInfo
from pyworkon.interfaces.tui.widgets import SessionCard, SidebarItem
from pyworkon.tmux_mgr import tmux_manager

if TYPE_CHECKING:
    from textual.events import Key

    from pyworkon.daemon.project_mgr import Project


class PopupApp(BaseApp):
    """Quick project/session switcher. Filter, select, exit."""

    BINDINGS: ClassVar = [
        *BaseApp.BINDINGS,
        Binding("ctrl+x", "kill_session", description="Kill"),
        Binding("backspace", "backspace_key", show=False),
    ]

    def _build_items(
        self,
        sessions: list[SessionInfo],
        projects: list[Project],
        plain_names: list[str],
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

    async def action_kill_session(self) -> None:
        if not self._filtered_items:
            return
        item = self._filtered_items[self._selected_index]
        if isinstance(item, SessionInfo):
            await tmux_manager.kill_session(item.session_name)
            self._close_project(item.project.id)
        elif isinstance(item, PlainSession):
            await tmux_manager.kill_session(item.name)
        else:
            return
        self._all_items = [i for i in self._all_items if i is not item]
        self._filtered_items = [i for i in self._filtered_items if i is not item]
        self._selected_index = min(
            self._selected_index, max(0, len(self._filtered_items) - 1)
        )
        self._render_items()
