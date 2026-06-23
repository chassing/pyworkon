"""Agent list widget: dynamic rows showing AI agent names and status."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Label

from pyworkon.interfaces.tui import icons

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from pyworkon.interfaces.tui.models import AgentInfo

_AGENT_STATUS_ICONS: dict[str, str] = {
    "idle": f"[dim]{icons.AGENT_IDLE}[/]",
    "working": f"[green]{icons.AGENT_WORKING}[/]",
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
    """

    agent_data: reactive[tuple[tuple[str, str], ...]] = reactive(())

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

    def update(self, agents: list[AgentInfo]) -> None:
        """Update with new agent data."""
        self.agent_data = tuple(
            (a.name, _AGENT_STATUS_ICONS.get(a.status, a.status)) for a in agents
        )
        self.display = bool(self.agent_data)

    def compose(self) -> ComposeResult:
        for name, status in self.agent_data:
            yield Horizontal(
                Label(icons.ICON_AGENT, classes="detail-icon"),
                Label(name, classes="detail-left"),
                Label(status, classes="detail-right", markup=True),
                classes="detail-row --agent-row",
            )

    async def watch_agent_data(self, value: tuple[tuple[str, str], ...]) -> None:
        if not self.is_mounted:
            return
        await self.recompose()
