from __future__ import annotations

import contextlib
import subprocess
from typing import Any, ClassVar

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Label, Rule, Static

from pyworkon.config import config
from pyworkon.sidebar.data import SessionDataCollector
from pyworkon.sidebar.models import PRInfo, PRState, PRStatus, SessionInfo
from pyworkon.tmux_mgr import tmux_manager

_PR_STATUS_ICONS: dict[PRStatus, str] = {
    PRStatus.SUCCESS: "[green]✓[/]",
    PRStatus.FAILURE: "[red]✗[/]",
    PRStatus.PENDING: "[yellow]◷[/]",
    PRStatus.NONE: "",
}

_PR_STATE_ICONS: dict[PRState, str] = {
    PRState.OPEN: "[green]●[/]",
    PRState.CLOSED: "[red]●[/]",
    PRState.MERGED: "[purple]●[/]",
}


def _truncate(text: str, max_width: int) -> str:
    if len(text) <= max_width:
        return text
    return text[: max_width - 1] + "…"


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
        width: 2;
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
    SessionRow .separator {
        margin: 0;
        color: $surface-lighten-2;
    }
    """

    def __init__(self, session: SessionInfo, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.session = session

    def compose(self) -> ComposeResult:
        max_width = config.sidebar_width - 4

        if self.session.is_current:
            self.add_class("--current-session")

        indicator = "●" if self.session.is_current else "○"
        current_cls = "--current" if self.session.is_current else "--other"
        yield Label(
            f"{indicator} {_truncate(self.session.project.name, max_width - 2)}",
            classes=f"session-name {current_cls}",
        )

        if self.session.branch:
            yield Horizontal(
                Label("", classes="detail-icon --branch"),
                Label(
                    _truncate(self.session.branch, max_width - 2), classes="detail-left"
                ),
                classes="detail-row",
            )

        if self.session.pr:
            pr = self.session.pr
            state_icon = _PR_STATE_ICONS.get(pr.state, "")
            ci_icon = _PR_STATUS_ICONS.get(pr.status, "")
            icons = f"{state_icon} {ci_icon}".rstrip()
            dimmed = "--dimmed" if pr.state != PRState.OPEN else ""
            yield Horizontal(
                Label("", classes="detail-icon --pr"),
                PRLink(pr.number, pr.url, classes=f"detail-left {dimmed}"),
                Label(icons, classes="detail-right"),
                classes="detail-row",
            )

        for agent in self.session.agents:
            yield Horizontal(
                Label("󱙺", classes="detail-icon --agent"),
                Label(agent.name, classes="detail-left"),
                Label(agent.status, classes="detail-right"),
                classes="detail-row",
            )


class ConfirmKillScreen(ModalScreen[bool]):
    """Confirmation dialog for killing a session."""

    DEFAULT_CSS = """
    ConfirmKillScreen {
        align: center middle;
    }
    ConfirmKillScreen > Static {
        width: auto;
        height: auto;
        padding: 1 2;
        background: $surface;
        border: thick $error;
    }
    """

    BINDINGS: ClassVar = [
        Binding("y", "confirm", "Yes"),
        Binding("n,escape", "cancel", "No"),
    ]

    def __init__(self, session_name: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._session_name = session_name

    def compose(self) -> ComposeResult:
        yield Static(f"Kill session '{self._session_name}'? (y/n)")

    def action_confirm(self) -> None:
        self.dismiss(result=True)

    def action_cancel(self) -> None:
        self.dismiss(result=False)


class SidebarApp(App[None]):
    """Pyworkon sidebar TUI."""

    DEFAULT_CSS = """
    Screen {
        background: $surface;
    }
    #session-list {
        width: 1fr;
        height: 1fr;
    }
    """

    BINDINGS: ClassVar = [
        Binding("q", "quit", "Quit"),
        Binding("j,down", "move_down", "Down", show=False),
        Binding("k,up", "move_up", "Up", show=False),
        Binding("enter", "select", "Switch", show=False),
        Binding("d", "kill_session", "Kill", show=False),
    ]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._collector = SessionDataCollector()
        self._sessions: list[SessionInfo] = []
        self._selected_index = 0
        self._render_generation = 0

    def compose(self) -> ComposeResult:
        yield VerticalScroll(id="session-list")

    def on_mount(self) -> None:
        self._refresh_sessions()
        self.set_interval(config.sidebar_refresh_interval, self._refresh_sessions)

    def _refresh_sessions(self) -> None:
        """Poll tmux for session data and update the UI."""
        new_sessions = self._collector.collect()
        for session in new_sessions:
            if session.branch:
                session.pr = self._collector.get_cached_pr(
                    session.project.id, session.branch
                )
        changed = self._has_changed(new_sessions)
        self._sessions = new_sessions
        self._selected_index = min(
            self._selected_index, max(0, len(self._sessions) - 1)
        )
        if changed:
            self._render_sessions()
        self._fetch_pr_data()

    def _has_changed(self, new_sessions: list[SessionInfo]) -> bool:
        """Check if session data differs from what's currently displayed."""
        if len(new_sessions) != len(self._sessions):
            return True
        return any(
            (
                n.session_name != o.session_name
                or n.branch != o.branch
                or n.pr != o.pr
                or n.agents != o.agents
                or n.is_current != o.is_current
            )
            for n, o in zip(new_sessions, self._sessions, strict=True)
        )

    def _rebuild_sessions(self) -> None:
        """Full rebuild of all session rows (only when structure changes)."""
        self._render_generation += 1
        gen = self._render_generation
        container = self.query_one("#session-list", VerticalScroll)
        container.remove_children()
        for i, session in enumerate(self._sessions):
            if i > 0:
                container.mount(Rule(classes="separator"))
            row = SessionRow(session, id=f"session-{gen}-{i}")
            if i == self._selected_index:
                row.add_class("--highlight")
            container.mount(row)

    def _render_sessions(self) -> None:
        """Update existing rows in-place, or rebuild if structure changed."""
        gen = self._render_generation
        rows = self.query(SessionRow)
        if len(rows) != len(self._sessions):
            self._rebuild_sessions()
            return
        for i, session in enumerate(self._sessions):
            try:
                row = self.query_one(f"#session-{gen}-{i}", SessionRow)
                row.session = session
                row.remove_children()
                row.mount_all(list(row.compose()))
            except Exception:  # noqa: BLE001
                self._rebuild_sessions()
                return

    @work(thread=True, group="pr-fetch")
    def _fetch_pr_data(self) -> None:
        """Fetch PR data in background for sessions with stale cache."""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        stale = [
            s
            for s in self._sessions
            if s.branch
            and s.project.provider
            and not self._collector.is_pr_fresh(s.project.id, s.branch)
        ]
        if not stale:
            return

        def _fetch(session: SessionInfo) -> tuple[SessionInfo, PRInfo | None]:
            return session, session.project.get_pr_info(session.branch or "")

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(_fetch, s): s for s in stale}
            for future in as_completed(futures):
                session, pr_info = future.result()
                self._collector.update_pr_cache(
                    session.project.id, session.branch or "", pr_info
                )
                session.pr = pr_info
                self.call_from_thread(self._render_sessions)

    def _update_highlight(self, old_index: int, new_index: int) -> None:
        """Move the highlight class without re-rendering."""
        gen = self._render_generation
        with contextlib.suppress(Exception):
            old_row = self.query_one(f"#session-{gen}-{old_index}", SessionRow)
            old_row.remove_class("--highlight")
        with contextlib.suppress(Exception):
            new_row = self.query_one(f"#session-{gen}-{new_index}", SessionRow)
            new_row.add_class("--highlight")
            new_row.scroll_visible()

    def action_move_down(self) -> None:
        if self._sessions:
            old = self._selected_index
            self._selected_index = min(old + 1, len(self._sessions) - 1)
            self._update_highlight(old, self._selected_index)

    def action_move_up(self) -> None:
        if self._sessions:
            old = self._selected_index
            self._selected_index = max(old - 1, 0)
            self._update_highlight(old, self._selected_index)

    def action_select(self) -> None:
        if not self._sessions:
            return
        session = self._sessions[self._selected_index]
        subprocess.run(
            ["tmux", "switch-client", "-t", session.session_name],  # noqa: S607
            check=False,
        )

    def action_kill_session(self) -> None:
        if not self._sessions:
            return
        session = self._sessions[self._selected_index]

        def _on_confirm(confirmed: bool | None) -> None:  # noqa: FBT001
            if confirmed:
                tmux_manager.kill_session(session.session_name)
                self._refresh_sessions()

        self.push_screen(ConfirmKillScreen(session.session_name), _on_confirm)
