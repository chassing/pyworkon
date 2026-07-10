"""Branch row widget: branch icon + name + dirty indicator."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Label

from pyworkon.interfaces.tui import icons

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from pyworkon.interfaces.tui.models import SessionInfo


class BranchRow(Widget):
    """Displays current git branch and dirty state."""

    DEFAULT_CSS = """
    BranchRow {
        height: auto;
    }
    BranchRow .detail-row {
        padding-left: 2;
        height: 1;
    }
    BranchRow .detail-icon {
        width: 2;
        color: cyan;
    }
    BranchRow .detail-left {
        width: 1fr;
        color: $text-muted;
        overflow: hidden;
    }
    BranchRow .detail-right {
        width: auto;
        color: $text;
    }
    """

    branch_text: reactive[str] = reactive("")
    dirty_text: reactive[str] = reactive("")

    def __init__(self, session: SessionInfo, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._sync(session)

    def update(self, session: SessionInfo) -> None:
        """Update with new session data."""
        self._sync(session)

    def _sync(self, session: SessionInfo) -> None:
        self.branch_text = session.branch or ""
        self.dirty_text = icons.BRANCH_DIRTY if session.is_dirty else ""
        self.display = bool(self.branch_text)

    def compose(self) -> ComposeResult:
        yield Horizontal(
            Label(icons.ICON_BRANCH, classes="detail-icon"),
            Label(self.branch_text, id="sbranch", classes="detail-left"),
            Label(
                self.dirty_text, id="sbranch-dirty", classes="detail-right", markup=True
            ),
            classes="detail-row",
        )

    def watch_branch_text(self, value: str) -> None:
        with contextlib.suppress(Exception):
            self.query_one("#sbranch", Label).update(value)
        self.display = bool(value)

    def watch_dirty_text(self, value: str) -> None:
        with contextlib.suppress(Exception):
            self.query_one("#sbranch-dirty", Label).update(value)
