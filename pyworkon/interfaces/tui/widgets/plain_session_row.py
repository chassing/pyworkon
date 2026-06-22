"""Plain session row widget: displays a tmux session without a pyworkon project."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from textual.containers import Horizontal
from textual.widget import Widget
from textual.widgets import Label

from pyworkon.interfaces.tui import icons

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from pyworkon.interfaces.tui.models import PlainSession


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
