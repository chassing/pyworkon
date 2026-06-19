from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any, ClassVar

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.widget import Widget
from textual.widgets import Label, Rule, Static

from pyworkon.config import config
from pyworkon.project import Project
from pyworkon.sidebar import icons
from pyworkon.sidebar.data import SessionDataCollector
from pyworkon.sidebar.models import PlainSession, PRInfo, PRState, PRStatus, SessionInfo
from pyworkon.tmux_mgr import tmux_manager

if TYPE_CHECKING:
    from textual.events import Key

_PR_STATUS_ICONS: dict[PRStatus, str] = {
    PRStatus.SUCCESS: icons.PR_CI_SUCCESS,
    PRStatus.FAILURE: icons.PR_CI_FAILURE,
    PRStatus.PENDING: icons.PR_CI_PENDING,
    PRStatus.NONE: "",
}

_PR_STATE_ICONS: dict[PRState, str] = {
    PRState.OPEN: icons.PR_STATE_OPEN,
    PRState.CLOSED: icons.PR_STATE_CLOSED,
    PRState.MERGED: icons.PR_STATE_MERGED,
}


SidebarItem = SessionInfo | Project | PlainSession


def _matches_filter(item: SidebarItem, filter_text: str) -> bool:
    """Case-insensitive substring match on display name."""
    text = filter_text.lower()
    if isinstance(item, SessionInfo):
        return text in item.session_name.lower()
    if isinstance(item, PlainSession):
        return text in item.name.lower()
    return text in item.name.lower()


class PRLink(Static):
    """Clickable PR/MR number that opens the URL in the browser."""

    def __init__(self, number: int, url: str | None, **kwargs: Any) -> None:
        super().__init__(f"[underline]#{number}[/underline]", markup=True, **kwargs)
        self._url = url

    def on_click(self) -> None:
        if self._url:
            import webbrowser

            webbrowser.open(self._url)


class SessionRow(Widget):
    """Displays a single session's info."""

    DEFAULT_CSS = """
    SessionRow {
        height: auto;
        padding: 0 1 0 2;
    }
    SessionRow.--highlight {
        background: $surface-lighten-1;
    }
    SessionRow.--current-session {
        border-left: tall $success;
        padding-left: 1;
    }
    SessionRow .session-name {
        text-style: bold;
    }
    SessionRow .session-name.--current {
        color: $success;
    }
    SessionRow .session-name.--other {
        color: $text-muted;
    }
    SessionRow .detail-row {
        padding-left: 2;
        height: 1;
    }
    SessionRow .detail-icon {
        width: 3;
    }
    SessionRow .detail-icon.--branch {
        color: cyan;
    }
    SessionRow .detail-icon.--pr {
        color: $accent;
    }
    SessionRow .detail-icon.--agent {
        color: ansi_bright_magenta;
    }
    SessionRow .detail-left {
        width: 1fr;
        color: $text-muted;
        overflow: hidden;
    }
    SessionRow PRLink {
        width: 1fr;
        color: $accent;
    }
    SessionRow PRLink.--dimmed {
        color: $text-muted;
    }
    SessionRow PRLink:hover {
        color: $accent-lighten-2;
    }
    SessionRow .detail-right {
        width: auto;
        color: $text;
    }
    """

    def __init__(self, session: SessionInfo, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.session = session

    def compose(self) -> ComposeResult:
        if self.session.is_current:
            self.add_class("--current-session")

        indicator = (
            icons.INDICATOR_CURRENT
            if self.session.is_current
            else icons.INDICATOR_OTHER
        )
        current_cls = "--current" if self.session.is_current else "--other"
        yield Label(
            f"{indicator} {self.session.project.name}",
            classes=f"session-name {current_cls}",
        )

        if self.session.branch:
            yield Horizontal(
                Label(icons.ICON_BRANCH, classes="detail-icon --branch"),
                Label(
                    self.session.branch,
                    classes="detail-left",
                ),
                classes="detail-row",
            )

        if self.session.pr:
            pr = self.session.pr
            state_icon = _PR_STATE_ICONS.get(pr.state, "")
            ci_icon = _PR_STATUS_ICONS.get(pr.status, "")
            status_text = f"{state_icon} {ci_icon}".rstrip()
            dimmed = "--dimmed" if pr.state != PRState.OPEN else ""
            yield Horizontal(
                Label(icons.ICON_PR, classes="detail-icon --pr"),
                PRLink(pr.number, pr.url, classes=f"detail-left {dimmed}"),
                Label(status_text, classes="detail-right"),
                classes="detail-row",
            )

        for agent in self.session.agents:
            yield Horizontal(
                Label(icons.ICON_AGENT, classes="detail-icon --agent"),
                Label(agent.name, classes="detail-left"),
                Label(agent.status, classes="detail-right"),
                classes="detail-row",
            )


class ProjectRow(Widget):
    """Displays a local project (no open session)."""

    DEFAULT_CSS = """
    ProjectRow {
        height: auto;
        padding: 0 1;
    }
    ProjectRow.--highlight {
        background: $surface-lighten-1;
    }
    ProjectRow .detail-row {
        height: 1;
    }
    ProjectRow .detail-icon {
        width: 3;
        color: $warning;
    }
    ProjectRow .detail-left {
        width: 1fr;
        color: $text-muted;
        overflow: hidden;
    }
    """

    def __init__(self, project: Project, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.project = project

    def compose(self) -> ComposeResult:
        yield Horizontal(
            Label(self._icon(), classes="detail-icon"),
            Label(self.project.id, classes="detail-left"),
            classes="detail-row",
        )

    @staticmethod
    def _icon() -> str:
        return icons.ICON_FOLDER


class PlainSessionRow(Widget):
    """Displays a plain tmux session (no pyworkon project)."""

    DEFAULT_CSS = """
    PlainSessionRow {
        height: auto;
        padding: 0 1 0 2;
    }
    PlainSessionRow.--highlight {
        background: $surface-lighten-1;
    }
    PlainSessionRow .detail-row {
        height: 1;
    }
    PlainSessionRow .detail-icon {
        width: 2;
        color: $primary;
    }
    PlainSessionRow .detail-left {
        width: 1fr;
        color: $text-muted;
        text-style: italic;
    }
    """

    def __init__(self, session: PlainSession, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.plain_session = session

    def compose(self) -> ComposeResult:
        yield Horizontal(
            Label(self._icon(), classes="detail-icon"),
            Label(self.plain_session.name, classes="detail-left"),
            classes="detail-row",
        )

    @staticmethod
    def _icon() -> str:
        return icons.ICON_PLAIN_SESSION


class SidebarApp(App[None]):
    """Pyworkon sidebar TUI."""

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
    .section-header {
        padding: 0 1;
        color: $text-muted;
        text-style: dim;
    }
    """

    BINDINGS: ClassVar = [
        Binding("down", "move_down", show=False),
        Binding("up", "move_up", show=False),
        Binding("enter", "select", show=False),
        Binding("escape", "escape_key", show=False),
        Binding("backspace", "backspace_key", show=False),
        Binding("pagedown", "page_down", show=False),
        Binding("pageup", "page_up", show=False),
    ]

    def __init__(self, *, popup: bool = False, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._collector = SessionDataCollector()
        self._all_items: list[SidebarItem] = []
        self._filtered_items: list[SidebarItem] = []
        self._selected_index = 0
        self._render_generation = 0
        self._filter_text = ""
        self._popup = popup

    def compose(self) -> ComposeResult:
        yield Label("", id="filter-bar")
        yield VerticalScroll(id="item-list", can_focus=False)

    def on_mount(self) -> None:
        self._refresh_data()
        if not self._popup:
            self.set_interval(config.sidebar_refresh_interval, self._refresh_data)

    def on_key(self, event: Key) -> None:
        if event.key == "ctrl+x":
            self._do_kill_session()
            event.prevent_default()
        elif event.character and event.is_printable:
            self._filter_text += event.character
            self._apply_filter()
            event.prevent_default()

    def action_escape_key(self) -> None:
        if self._filter_text:
            self._filter_text = ""
            self._apply_filter()
        elif self._popup:
            self.exit()

    def action_backspace_key(self) -> None:
        if self._filter_text:
            self._filter_text = self._filter_text[:-1]
            self._apply_filter()

    def _refresh_data(self) -> None:
        """Poll tmux for session and project data."""
        sessions = self._collector.collect()
        for session in sessions:
            if session.branch:
                session.pr = self._collector.get_cached_pr(
                    session.project.id, session.branch
                )
        projects = self._collector.collect_projects()
        plain = (
            [PlainSession(name) for name in self._collector.collect_plain_sessions()]
            if self._popup
            else []
        )
        new_items: list[SidebarItem] = [*plain, *sessions, *projects]

        if self._items_changed(new_items):
            self._all_items = new_items
            self._apply_filter()
        self._fetch_pr_data()

    def _items_changed(self, new_items: list[SidebarItem]) -> bool:
        if len(new_items) != len(self._all_items):
            return True
        for new, old in zip(new_items, self._all_items, strict=True):
            if type(new) is not type(old):
                return True
            if isinstance(new, SessionInfo) and isinstance(old, SessionInfo):
                if (
                    new.session_name != old.session_name
                    or new.branch != old.branch
                    or new.pr != old.pr
                    or new.agents != old.agents
                    or new.is_current != old.is_current
                ):
                    return True
            elif (
                isinstance(new, Project)
                and isinstance(old, Project)
                and new.id != old.id
            ):
                return True
        return False

    def _apply_filter(self) -> None:
        """Filter items and re-render."""
        if self._filter_text:
            self._filtered_items = [
                item
                for item in self._all_items
                if _matches_filter(item, self._filter_text)
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

    def _render_items(self) -> None:
        """Full rebuild of the item list."""
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
                    widget = SessionRow(item, id=f"row-{gen}-{idx}")
                else:
                    widget = ProjectRow(item, id=f"row-{gen}-{idx}")
                if idx == self._selected_index:
                    widget.add_class("--highlight")
                container.mount(widget)
                idx += 1

    @work(thread=True, group="pr-fetch")
    def _fetch_pr_data(self) -> None:
        """Fetch PR data in background for sessions with stale cache."""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        stale = [
            s
            for s in self._all_items
            if isinstance(s, SessionInfo)
            and s.branch
            and s.project.provider
            and not self._collector.is_pr_fresh(s.project.id, s.branch)
        ]
        if not stale:
            return

        def _fetch(session: SessionInfo) -> tuple[SessionInfo, PRInfo | None]:
            return session, session.project.get_pr_info(session.branch or "")

        changed = False
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(_fetch, s): s for s in stale}
            for future in as_completed(futures):
                session, pr_info = future.result()
                self._collector.update_pr_cache(
                    session.project.id, session.branch or "", pr_info
                )
                if session.pr != pr_info:
                    session.pr = pr_info
                    changed = True
        if changed:
            self.call_from_thread(self._render_items)

    def _update_highlight(self, old_index: int, new_index: int) -> None:
        gen = self._render_generation
        with contextlib.suppress(Exception):
            old_row = self.query_one(f"#row-{gen}-{old_index}")
            old_row.remove_class("--highlight")
        with contextlib.suppress(Exception):
            new_row = self.query_one(f"#row-{gen}-{new_index}")
            new_row.add_class("--highlight")
            new_row.scroll_visible()

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

    def action_select(self) -> None:
        if not self._filtered_items:
            return
        item = self._filtered_items[self._selected_index]
        if isinstance(item, SessionInfo):
            tmux_manager.attach_session(item.session_name)
        elif isinstance(item, PlainSession):
            tmux_manager.attach_session(item.name)
        elif isinstance(item, Project):
            tmux_manager.enter(item.id)
        if self._popup:
            self.exit()

    def _do_kill_session(self) -> None:
        if not self._filtered_items:
            return
        item = self._filtered_items[self._selected_index]
        if isinstance(item, SessionInfo):
            tmux_manager.kill_session(item.session_name)
        elif isinstance(item, PlainSession):
            tmux_manager.kill_session(item.name)
        else:
            return
        self._refresh_data()
