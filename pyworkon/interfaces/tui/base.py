"""Base app — shared daemon subscription, item management, and navigation."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any, ClassVar

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widgets import Footer, Label, Rule

from pyworkon.daemon.client import DaemonClient, DaemonNotRunningError
from pyworkon.daemon.project_mgr import Project
from pyworkon.interfaces.tui.data import parse_sidebar_state
from pyworkon.interfaces.tui.models import PlainSession, ReviewPR, SessionInfo
from pyworkon.interfaces.tui.widgets import (
    PlainSessionRow,
    ProjectRow,
    SessionCard,
    SidebarItem,
    matches_filter,
)

if TYPE_CHECKING:
    from textual.widget import Widget


class BaseApp(App[None]):
    """Shared app logic for dashboard and popup."""

    DEFAULT_CSS = """
    Screen {
        background: $surface;
    }
    #filter-bar {
        height: 1;
        padding: 0 1;
        color: $accent;
        display: none;
    }
    #filter-bar.--visible {
        display: block;
    }
    #item-list {
        scrollbar-size: 0 0;
        width: 1fr;
        height: 1fr;
    }
    """

    BINDINGS: ClassVar = [
        Binding("down", "move_down", show=False),
        Binding("up", "move_up", show=False),
        Binding("enter", "select", description="Select"),
        Binding("escape", "escape_key", description="Close"),
        Binding("ctrl+q", "quit", description="Quit"),
        Binding("pagedown", "page_down", show=False),
        Binding("pageup", "page_up", show=False),
    ]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._all_items: list[SidebarItem] = []
        self._filtered_items: list[SidebarItem] = []
        self._selected_index = 0
        self._render_generation = 0
        self._filter_text = ""
        self._notification_client: DaemonClient | None = None

    def compose(self) -> ComposeResult:
        yield Label("", id="filter-bar")
        yield VerticalScroll(id="item-list", can_focus=False)
        yield Footer()

    def on_mount(self) -> None:
        self._listen_daemon()

    def on_unmount(self) -> None:
        if self._notification_client:
            self._notification_client.close()

    # --- Subclass hooks ---

    def _build_items(
        self,
        sessions: list[SessionInfo],
        projects: list[Project],
        plain_names: list[str],
        review_prs: dict[str, list[ReviewPR]],
    ) -> list[SidebarItem]:
        """Subclass decides which item types to include."""
        raise NotImplementedError

    def _on_select(self, item: SidebarItem) -> bool:
        """Handle item selection. Return True to exit after select."""
        return False

    def _create_session_card(self, session: SessionInfo, **kwargs: Any) -> SessionCard:
        """Subclass controls show_ci_checks and other card options."""
        return SessionCard(session, **kwargs)

    # --- Daemon subscription ---

    @staticmethod
    def _close_project(project_id: str) -> None:
        with (
            contextlib.suppress(DaemonNotRunningError, ConnectionError, OSError),
            DaemonClient() as client,
        ):
            client.close_project(project_id)

    @staticmethod
    def _kill_session(session_name: str) -> None:
        with (
            contextlib.suppress(DaemonNotRunningError, ConnectionError, OSError),
            DaemonClient() as client,
        ):
            client.kill_session(session_name)

    @staticmethod
    def _switch_session(session_name: str, pane_id: str | None = None) -> None:
        with (
            contextlib.suppress(DaemonNotRunningError, ConnectionError, OSError),
            DaemonClient() as client,
        ):
            client.switch_session(session_name, pane_id=pane_id)

    @staticmethod
    def _enter_project(project_id: str) -> None:
        with (
            contextlib.suppress(DaemonNotRunningError, ConnectionError, OSError),
            DaemonClient() as client,
        ):
            client.enter_project(project_id)

    @work(thread=True, group="daemon", exclusive=True)
    def _listen_daemon(self) -> None:
        """Subscribe to daemon events in background thread."""
        client = DaemonClient()
        try:
            client.connect()
        except (DaemonNotRunningError, ConnectionError, OSError):
            return
        self._notification_client = client
        try:
            self._consume_events(client)
        except (ConnectionError, OSError):
            pass
        finally:
            self._notification_client = None
            client.close()

    def _consume_events(self, client: DaemonClient) -> None:
        severity_map: dict[str, str] = {"warning": "warning", "error": "error"}
        for resp in client.subscribe(["state", "notification"], full=True):
            match resp.event:
                case "state":
                    self._handle_state_event(resp.data or {})
                case "notification":
                    data = resp.data or {}
                    level = data.get("level", "information")
                    message = data.get("message", "")
                    severity = severity_map.get(level, "information")
                    self.call_from_thread(self.notify, message, severity=severity)

    def _handle_state_event(self, state: dict[str, Any]) -> None:
        sessions, projects, plain_names, review_prs = parse_sidebar_state(state)
        new_items = self._build_items(sessions, projects, plain_names, review_prs)
        self.call_from_thread(self._apply_new_items, new_items)

    # --- Item management ---

    def _apply_new_items(self, new_items: list[SidebarItem]) -> None:
        if self._structure_changed(new_items):
            self._all_items = new_items
            self._apply_filter()
            return
        self._all_items = new_items
        self._filtered_items = (
            list(new_items)
            if not self._filter_text
            else [item for item in new_items if matches_filter(item, self._filter_text)]
        )
        self._update_existing_rows()

    def _structure_changed(self, new_items: list[SidebarItem]) -> bool:
        if len(new_items) != len(self._all_items):
            return True
        return any(
            type(n) is not type(o)
            or (
                isinstance(n, SessionInfo)
                and isinstance(o, SessionInfo)
                and n.session_name != o.session_name
            )
            or (isinstance(n, Project) and isinstance(o, Project) and n.id != o.id)
            or (
                isinstance(n, PlainSession)
                and isinstance(o, PlainSession)
                and n.name != o.name
            )
            for n, o in zip(new_items, self._all_items, strict=True)
        )

    def _update_existing_rows(self) -> None:
        gen = self._render_generation
        for i, item in enumerate(self._filtered_items):
            if isinstance(item, SessionInfo):
                with contextlib.suppress(Exception):
                    self.query_one(f"#row-{gen}-{i}", SessionCard).update_session(item)

    def _apply_filter(self) -> None:
        if self._filter_text:
            self._filtered_items = [
                item
                for item in self._all_items
                if matches_filter(item, self._filter_text)
            ]
        else:
            self._filtered_items = list(self._all_items)
        self._selected_index = min(
            self._selected_index, max(0, len(self._filtered_items) - 1)
        )
        self._render_items()
        self._update_filter_bar()

    def _update_filter_bar(self) -> None:
        bar = self.query_one("#filter-bar", Label)
        if self._filter_text:
            bar.update(f"> {self._filter_text}_")
            bar.add_class("--visible")
        else:
            bar.remove_class("--visible")

    # --- Rendering ---

    def _render_items(self) -> None:
        self._render_generation += 1
        gen = self._render_generation
        container = self.query_one("#item-list", VerticalScroll)
        container.remove_children()

        plain: list[SidebarItem] = [
            i for i in self._filtered_items if isinstance(i, PlainSession)
        ]
        sessions: list[SidebarItem] = [
            i for i in self._filtered_items if isinstance(i, SessionInfo)
        ]
        projects: list[SidebarItem] = [
            i for i in self._filtered_items if isinstance(i, Project)
        ]
        sections = [s for s in [plain, sessions, projects] if s]

        idx = 0
        for section_idx, section in enumerate(sections):
            if section_idx > 0:
                container.mount(Rule(line_style="double"))
            for i, item in enumerate(section):
                if i > 0 and isinstance(item, SessionInfo):
                    container.mount(Rule())
                widget: Widget
                if isinstance(item, PlainSession):
                    widget = PlainSessionRow(item, id=f"row-{gen}-{idx}")
                elif isinstance(item, SessionInfo):
                    widget = self._create_session_card(item, id=f"row-{gen}-{idx}")
                else:
                    widget = ProjectRow(item, id=f"row-{gen}-{idx}")
                if idx == self._selected_index:
                    widget.add_class("--highlight")
                container.mount(widget)
                idx += 1

    # --- Navigation ---

    def _update_highlight(self, old_index: int, new_index: int) -> None:
        gen = self._render_generation
        with contextlib.suppress(Exception):
            self.query_one(f"#row-{gen}-{old_index}").remove_class("--highlight")
        with contextlib.suppress(Exception):
            row = self.query_one(f"#row-{gen}-{new_index}")
            row.add_class("--highlight")
            row.scroll_visible()

    def action_move_down(self) -> None:
        if self._filtered_items:
            old = self._selected_index
            self._selected_index = min(old + 1, len(self._filtered_items) - 1)
            self._update_highlight(old, self._selected_index)

    def action_move_up(self) -> None:
        if self._filtered_items:
            old = self._selected_index
            self._selected_index = max(old - 1, 0)
            self._update_highlight(old, self._selected_index)

    def action_page_down(self) -> None:
        if self._filtered_items:
            old = self._selected_index
            page = self.size.height // 2
            self._selected_index = min(old + page, len(self._filtered_items) - 1)
            self._update_highlight(old, self._selected_index)

    def action_page_up(self) -> None:
        if self._filtered_items:
            old = self._selected_index
            page = self.size.height // 2
            self._selected_index = max(old - page, 0)
            self._update_highlight(old, self._selected_index)

    # --- Actions ---

    async def action_select(self) -> None:
        if not self._filtered_items:
            return
        item = self._filtered_items[self._selected_index]
        if isinstance(item, SessionInfo):
            self._switch_session(item.session_name, pane_id=item.pane_id)
        elif isinstance(item, PlainSession):
            self._switch_session(item.name)
        elif isinstance(item, Project):
            self._enter_project(item.id)
        if self._on_select(item):
            self.exit()

    def action_escape_key(self) -> None:
        if self._filter_text:
            self._filter_text = ""
            self._apply_filter()
        else:
            self.exit()
