"""Agent list widget: dynamic rows showing AI agent names and status."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

from rich.spinner import Spinner
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Label

from pyworkon.interfaces.tui import icons

if TYPE_CHECKING:
    from textual.app import ComposeResult
    from textual.timer import Timer

    from pyworkon.interfaces.tui.models import AgentInfo

_AGENT_STATUS_ICONS: dict[str, str] = {
    "idle": f"[dim]{icons.AGENT_IDLE}[/]",
    "waiting": f"[yellow]{icons.AGENT_WAITING}[/]",
}


class AgentList(Widget):
    """Displays AI agent rows with status icons."""

    DEFAULT_CSS = """
    AgentList {
        height: auto;
    }
    AgentList .detail-row {
        padding-left: 2;
        height: 1;
    }
    AgentList .detail-icon {
        width: 3;
        color: ansi_bright_magenta;
    }
    AgentList .detail-left {
        width: 1fr;
        color: $text-muted;
        overflow: hidden;
    }
    AgentList .detail-right {
        width: auto;
        color: $text;
    }
    AgentList .--agent-working {
        background: $success 10%;
    }
    """

    agent_data: reactive[tuple[tuple[str, str], ...]] = reactive(())

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._spinner = Spinner(icons.AGENT_WORKING_SPINNER, style="green")
        self._spinner_timer: Timer | None = None

    def update(self, agents: list[AgentInfo]) -> None:
        """Update with new agent data."""
        self.agent_data = tuple((a.name, a.status) for a in agents)
        self.display = bool(self.agent_data)

    def compose(self) -> ComposeResult:
        for name, status in self.agent_data:
            classes = "detail-right"
            if status == "working":
                classes += " --working"
                status_display: str | Spinner = self._spinner
            else:
                status_display = _AGENT_STATUS_ICONS.get(status, status)
            row_classes = "detail-row --agent-row"
            if status == "working":
                row_classes += " --agent-working"
            yield Horizontal(
                Label(icons.ICON_AGENT, classes="detail-icon"),
                Label(name, classes="detail-left"),
                Label(status_display, classes=classes, markup=True),
                classes=row_classes,
            )

    async def watch_agent_data(self, value: tuple[tuple[str, str], ...]) -> None:
        if not self.is_mounted:
            return
        self._manage_spinner()
        await self.recompose()

    def _manage_spinner(self) -> None:
        """Start or stop the spinner timer based on working agents."""
        has_working = any(status == "working" for _, status in self.agent_data)
        if has_working and self._spinner_timer is None:
            self._spinner_timer = self.set_interval(1 / 12, self._tick_spinner)
        elif not has_working and self._spinner_timer is not None:
            self._spinner_timer.stop()
            self._spinner_timer = None

    def _tick_spinner(self) -> None:
        """Update all working agent labels with the current spinner frame."""
        with contextlib.suppress(Exception):
            for label in self.query(Label).filter(".--working"):
                label.update(self._spinner)
