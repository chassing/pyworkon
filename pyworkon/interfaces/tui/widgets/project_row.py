"""Project row widget: displays a local project without an open session."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from textual.containers import Horizontal
from textual.widget import Widget
from textual.widgets import Label

from pyworkon.config import ProviderType
from pyworkon.interfaces.tui import icons

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from pyworkon.daemon.project_mgr import Project

_PROVIDER_ICONS: dict[ProviderType, str] = {
    ProviderType.github: icons.ICON_GITHUB,
    ProviderType.gitlab: icons.ICON_GITLAB,
}


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
