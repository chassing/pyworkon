"""Session header widget: indicator + name + provider icon."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Label

from pyworkon.config import ProviderType
from pyworkon.interfaces.tui import icons

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from pyworkon.interfaces.tui.models import SessionInfo

_PROVIDER_ICONS: dict[ProviderType, str] = {
    ProviderType.github: icons.ICON_GITHUB,
    ProviderType.gitlab: icons.ICON_GITLAB,
}


class SessionHeader(Widget):
    """Displays session indicator, name, and provider icon."""

    DEFAULT_CSS = """
    SessionHeader {
        height: 1;
    }
    SessionHeader .session-name {
        width: 1fr;
        text-style: bold;
    }
    SessionHeader .session-name.--current {
        color: $success;
    }
    SessionHeader .session-name.--other {
        color: $text-muted;
    }
    SessionHeader .provider-icon {
        width: auto;
        color: $text-muted;
    }
    SessionHeader .detail-icon {
        width: 2;
        color: $primary;
    }
    """

    name_text: reactive[str] = reactive("")
    provider_icon_text: reactive[str] = reactive("")

    def __init__(self, session: SessionInfo, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._sync(session)

    def update(self, session: SessionInfo) -> None:
        """Update with new session data."""
        self._sync(session)

    def _sync(self, session: SessionInfo) -> None:
        self.name_text = session.project.name
        provider_type = (
            session.project.provider.type if session.project.provider else None
        )
        self.provider_icon_text = (
            _PROVIDER_ICONS.get(provider_type, "") if provider_type else ""
        )

    def compose(self) -> ComposeResult:
        yield Horizontal(
            Label(icons.SESSION_INDICATOR, classes="detail-icon"),
            Label(self.name_text, id="sname", classes="session-name --other"),
            Label(self.provider_icon_text, id="sprovider", classes="provider-icon"),
        )

    def watch_name_text(self, value: str) -> None:
        with contextlib.suppress(Exception):
            self.query_one("#sname", Label).update(value)

    def watch_provider_icon_text(self, value: str) -> None:
        with contextlib.suppress(Exception):
            self.query_one("#sprovider", Label).update(value)
