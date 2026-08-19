"""Icon glyphs for the relay dashboard — sourced from the Textual TUI's icon set.

`interfaces.tui.icons` is a dependency-free leaf module (no `pyworkon.config`
import chain), so it's safe to import here despite the relay's isolation
requirement (see `relay/schema.py`). Some TUI constants wrap the glyph in Rich
color markup (e.g. `"[yellow][/]"`); the dashboard applies its own CSS color
classes instead, so that markup is stripped here.
"""

from __future__ import annotations

import re

from pyworkon.interfaces.tui import icons as tui_icons

_RICH_MARKUP = re.compile(r"\[[^\]]*\]")


def _glyph(value: str) -> str:
    return _RICH_MARKUP.sub("", value)


DASHBOARD_ICONS: dict[str, str] = {
    "branch": tui_icons.ICON_BRANCH,
    "pr": tui_icons.ICON_PR,
    "agent": tui_icons.ICON_AGENT,
    "github": tui_icons.ICON_GITHUB,
    "gitlab": tui_icons.ICON_GITLAB,
    "agentIdle": tui_icons.AGENT_IDLE,
    "agentWaiting": tui_icons.AGENT_WAITING,
    "reviewRequest": tui_icons.ICON_REVIEW_REQUEST,
    "dirty": _glyph(tui_icons.BRANCH_DIRTY),
    "ciSuccess": _glyph(tui_icons.PR_CI_SUCCESS),
    "ciFailure": _glyph(tui_icons.PR_CI_FAILURE),
    "ciPending": _glyph(tui_icons.PR_CI_PENDING),
    "stateOpen": _glyph(tui_icons.PR_STATE_OPEN),
    "stateClosed": _glyph(tui_icons.PR_STATE_CLOSED),
    "stateMerged": _glyph(tui_icons.PR_STATE_MERGED),
    "stateDraft": _glyph(tui_icons.PR_STATE_DRAFT),
    "reviewApproved": _glyph(tui_icons.PR_REVIEW_APPROVED),
    "reviewChangesRequested": _glyph(tui_icons.PR_REVIEW_CHANGES_REQUESTED),
    "reviewPending": _glyph(tui_icons.PR_REVIEW_PENDING),
}
