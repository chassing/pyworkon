from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any, ClassVar

from rich.table import Table
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Footer, Label, Rule, Static

from pyworkon.config import ProviderType, config
from pyworkon.daemon.project_mgr import Project
from pyworkon.sidebar import icons
from pyworkon.sidebar.data import SessionDataCollector
from pyworkon.sidebar.models import PlainSession, PRState, PRStatus, SessionInfo
from pyworkon.tmux_mgr import tmux_manager

_PROVIDER_ICONS: dict[ProviderType, str] = {
    ProviderType.github: icons.ICON_GITHUB,
    ProviderType.gitlab: icons.ICON_GITLAB,
}

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
        return text in item.session_name.lower() or text in item.project.name.lower()
    if isinstance(item, PlainSession):
        return text in item.name.lower()
    return text in item.name.lower()


class SessionRow(Widget):
    """Displays a single session's info with reactive updates."""

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
    SessionRow .name-row {
        height: 1;
    }
    SessionRow .session-name {
        width: 1fr;
        text-style: bold;
    }
    SessionRow .session-name.--current {
        color: $success;
    }
    SessionRow .session-name.--other {
        color: $text-muted;
    }
    SessionRow .provider-icon {
        width: auto;
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
    SessionRow .detail-row.--ci-failure {
        background: $error 15%;
    }
    SessionRow .detail-icon.--agent {
        color: ansi_bright_magenta;
    }
    SessionRow .agent-lines {
        padding-left: 2;
        height: auto;
        color: $text-muted;
    }
    SessionRow .detail-left {
        width: 1fr;
        color: $text-muted;
        overflow: hidden;
    }
    SessionRow .detail-left.--pr-link {
        color: $accent;
        text-style: underline;
    }
    SessionRow .detail-right {
        width: auto;
        color: $text;
    }
    """

    name_text: reactive[str] = reactive("")
    provider_icon_text: reactive[str] = reactive("")
    branch_text: reactive[str] = reactive("")
    pr_number_text: reactive[str] = reactive("")
    pr_icons_text: reactive[str] = reactive("")
    pr_ci_failure: reactive[bool] = reactive(default=False)
    agent_data: reactive[tuple[tuple[str, str], ...]] = reactive(())

    def __init__(self, session: SessionInfo, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.session = session
        self._sync_reactive()

    def _sync_reactive(self) -> None:
        s = self.session
        indicator = icons.INDICATOR_CURRENT if s.is_current else icons.INDICATOR_OTHER
        self.name_text = f"{indicator} {s.project.name}"
        provider_type = s.project.provider.type if s.project.provider else None
        self.provider_icon_text = (
            _PROVIDER_ICONS.get(provider_type, "") if provider_type else ""
        )
        self.branch_text = s.branch or ""
        if s.pr:
            state_icon = _PR_STATE_ICONS.get(s.pr.state, "")
            ci_icon = _PR_STATUS_ICONS.get(s.pr.status, "")
            self.pr_number_text = f"#{s.pr.number}"
            self.pr_icons_text = f"{state_icon} {ci_icon}".rstrip()
            self.pr_ci_failure = s.pr.status == PRStatus.FAILURE
        else:
            self.pr_number_text = ""
            self.pr_icons_text = ""
            self.pr_ci_failure = False
        self.agent_data = tuple((a.name, a.status) for a in s.agents)

    def update_session(self, session: SessionInfo) -> None:
        self.session = session
        if session.is_current:
            self.add_class("--current-session")
        else:
            self.remove_class("--current-session")
        self._sync_reactive()

    def compose(self) -> ComposeResult:
        if self.session.is_current:
            self.add_class("--current-session")
        current_cls = "--current" if self.session.is_current else "--other"
        yield Horizontal(
            Label(self.name_text, id="sname", classes=f"session-name {current_cls}"),
            Label(self.provider_icon_text, id="sprovider", classes="provider-icon"),
            classes="name-row",
        )

        branch_row = Horizontal(
            Label(icons.ICON_BRANCH, classes="detail-icon --branch"),
            Label(self.branch_text, id="sbranch", classes="detail-left"),
            id="row-branch",
            classes="detail-row",
        )
        branch_row.display = bool(self.branch_text)
        yield branch_row

        pr_row = Horizontal(
            Label(icons.ICON_PR, classes="detail-icon --pr"),
            Label(self.pr_number_text, id="spr", classes="detail-left --pr-link"),
            Label(
                self.pr_icons_text, id="spricons", classes="detail-right", markup=True
            ),
            id="row-pr",
            classes="detail-row",
        )
        pr_row.display = bool(self.pr_number_text)
        yield pr_row

        agents = Static(self._render_agents(), id="sagents", classes="agent-lines")
        agents.display = bool(self.agent_data)
        yield agents

    def _toggle_row(self, row_id: str, *, visible: bool) -> None:
        with contextlib.suppress(Exception):
            self.query_one(f"#{row_id}").display = visible

    def watch_name_text(self, value: str) -> None:
        with contextlib.suppress(Exception):
            self.query_one("#sname", Label).update(value)

    def watch_provider_icon_text(self, value: str) -> None:
        with contextlib.suppress(Exception):
            self.query_one("#sprovider", Label).update(value)

    def watch_branch_text(self, value: str) -> None:
        with contextlib.suppress(Exception):
            self.query_one("#sbranch", Label).update(value)
        self._toggle_row("row-branch", visible=bool(value))

    def watch_pr_number_text(self, value: str) -> None:
        with contextlib.suppress(Exception):
            self.query_one("#spr", Label).update(value)
        self._toggle_row("row-pr", visible=bool(value))

    def watch_pr_icons_text(self, value: str) -> None:
        with contextlib.suppress(Exception):
            self.query_one("#spricons", Label).update(value)

    def watch_pr_ci_failure(self, value: bool) -> None:  # noqa: FBT001
        with contextlib.suppress(Exception):
            row = self.query_one("#row-pr")
            row.set_class(value, "--ci-failure")

    def _render_agents(self) -> Table | str:
        if not self.agent_data:
            return ""
        table = Table(
            show_header=False,
            show_edge=False,
            show_lines=False,
            box=None,
            padding=0,
            expand=True,
        )
        table.add_column(width=3, style="bright_magenta")
        table.add_column(ratio=1)
        table.add_column(justify="right")
        for name, status in self.agent_data:
            table.add_row(icons.ICON_AGENT, name, status)
        return table

    def watch_agent_data(self, value: tuple[tuple[str, str], ...]) -> None:
        with contextlib.suppress(Exception):
            self.query_one("#sagents", Static).update(self._render_agents())
            self.query_one("#sagents").display = bool(value)


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
    ProjectRow .provider-icon {
        width: auto;
        color: $text-muted;
    }
    """

    def __init__(self, project: Project, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.project = project

    def compose(self) -> ComposeResult:
        provider_type = self.project.provider.type if self.project.provider else None
        provider_icon = _PROVIDER_ICONS.get(provider_type, "") if provider_type else ""
        yield Horizontal(
            Label(icons.ICON_FOLDER, classes="detail-icon"),
            Label(self.project.id, classes="detail-left"),
            Label(provider_icon, classes="provider-icon"),
            classes="detail-row",
        )


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
            Label(icons.ICON_PLAIN_SESSION, classes="detail-icon"),
            Label(self.plain_session.name, classes="detail-left"),
            classes="detail-row",
        )


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
    """

    BINDINGS: ClassVar = [
        Binding("down", "move_down", show=False),
        Binding("up", "move_up", show=False),
        Binding("enter", "select", description="Select"),
        Binding("escape", "escape_key", description="Close"),
        Binding("ctrl+x", "kill_session", description="Kill"),
        Binding("ctrl+q", "quit", description="Quit"),
        Binding("backspace", "backspace_key", show=False),
        Binding("pagedown", "page_down", show=False),
        Binding("pageup", "page_up", show=False),
    ]

    def __init__(
        self, *, popup: bool = False, dashboard: bool = False, **kwargs: Any
    ) -> None:
        super().__init__(**kwargs)
        self._collector = SessionDataCollector()
        self._all_items: list[SidebarItem] = []
        self._filtered_items: list[SidebarItem] = []
        self._selected_index = 0
        self._render_generation = 0
        self._filter_text = ""
        self._popup = popup
        self._dashboard = dashboard

    def compose(self) -> ComposeResult:
        yield Label("", id="filter-bar")
        yield VerticalScroll(id="item-list", can_focus=False)
        if self._popup or self._dashboard:
            yield Footer()

    def on_mount(self) -> None:
        self._poll_daemon()
        if not self._popup:
            self.set_interval(config.sidebar_refresh_interval, self._poll_daemon)

    async def on_key(self, event: Key) -> None:
        if self._dashboard:
            return
        if event.character and event.is_printable:
            self._filter_text += event.character
            self._apply_filter()
            event.prevent_default()

    async def action_kill_session(self) -> None:
        await self._do_kill_session()

    def action_escape_key(self) -> None:
        if self._dashboard:
            self.exit()
            return
        if self._filter_text:
            self._filter_text = ""
            self._apply_filter()
        elif self._popup:
            self.exit()

    def action_backspace_key(self) -> None:
        if self._filter_text:
            self._filter_text = self._filter_text[:-1]
            self._apply_filter()

    @work(thread=True, group="poll")
    def _poll_daemon(self) -> None:
        """Fetch data from daemon in background thread."""
        sessions = self._collector.collect()
        if self._dashboard:
            new_items: list[SidebarItem] = list(sessions)
        else:
            projects = self._collector.collect_projects()
            plain = (
                [
                    PlainSession(name)
                    for name in self._collector.collect_plain_sessions()
                ]
                if self._popup
                else []
            )
            new_items = [*plain, *sessions, *projects]
        self.call_from_thread(self._apply_new_items, new_items)

    def _apply_new_items(self, new_items: list[SidebarItem]) -> None:
        """Apply new items — full rebuild on structure change, reactive update otherwise."""
        if self._structure_changed(new_items):
            self._all_items = new_items
            self._apply_filter()
            return
        self._all_items = new_items
        self._filtered_items = (
            list(new_items)
            if not self._filter_text
            else [
                item for item in new_items if _matches_filter(item, self._filter_text)
            ]
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
                    self.query_one(f"#row-{gen}-{i}", SessionRow).update_session(item)

    def _apply_filter(self) -> None:
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

    async def action_select(self) -> None:
        if not self._filtered_items:
            return
        item = self._filtered_items[self._selected_index]
        if isinstance(item, SessionInfo):
            if item.pane_id:
                await tmux_manager.select_pane(item.session_name, item.pane_id)
            else:
                await tmux_manager.attach_session(item.session_name)
        elif isinstance(item, PlainSession):
            await tmux_manager.attach_session(item.name)
        elif isinstance(item, Project):
            await tmux_manager.enter(item)
        if self._popup:
            self.exit()

    async def _do_kill_session(self) -> None:
        if not self._filtered_items:
            return
        item = self._filtered_items[self._selected_index]
        if isinstance(item, SessionInfo):
            await tmux_manager.kill_session(item.session_name)
            self._collector.close_project(item.project.id)
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
