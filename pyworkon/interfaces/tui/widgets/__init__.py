"""Sidebar widgets — reusable Textual components."""

from __future__ import annotations

from pyworkon.daemon.project_mgr import Project
from pyworkon.interfaces.tui.models import PlainSession, SessionInfo
from pyworkon.interfaces.tui.widgets.plain_session_row import PlainSessionRow
from pyworkon.interfaces.tui.widgets.project_row import ProjectRow
from pyworkon.interfaces.tui.widgets.review_request_list import ReviewRequestList
from pyworkon.interfaces.tui.widgets.session_card import SessionCard

SidebarItem = SessionInfo | Project | PlainSession


def matches_filter(item: SidebarItem, filter_text: str) -> bool:
    """Case-insensitive substring match on display name."""
    text = filter_text.lower()
    if isinstance(item, SessionInfo):
        return text in item.session_name.lower() or text in item.project.name.lower()
    if isinstance(item, PlainSession):
        return text in item.name.lower()
    return text in item.name.lower()


__all__ = [
    "PlainSessionRow",
    "ProjectRow",
    "ReviewRequestList",
    "SessionCard",
    "SidebarItem",
    "matches_filter",
]
