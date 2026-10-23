"""Re-exports `pyworkon.icons` for the TUI's existing import sites.

The actual glyph definitions live in `pyworkon.icons` now, not here -- the
relay dashboard and the strip also need them and must not depend on this
package to get at them (see `pyworkon/icons.py`'s module docstring). Kept as
a thin shim purely so every existing TUI widget import (`from
pyworkon.interfaces.tui.icons import X` / `from pyworkon.interfaces.tui
import icons as tui_icons`) keeps working unchanged.
"""

from __future__ import annotations

from pyworkon.icons import (
    AGENT_IDLE,
    AGENT_WAITING,
    AGENT_WORKING_SPINNER,
    BRANCH_DIRTY,
    ICON_AGENT,
    ICON_BRANCH,
    ICON_EXTERNAL_LINK,
    ICON_FOLDER,
    ICON_GITHUB,
    ICON_GITLAB,
    ICON_PLAIN_SESSION,
    ICON_PR,
    ICON_REVIEW_REQUEST,
    PR_CI_FAILURE,
    PR_CI_PENDING,
    PR_CI_PENDING_SPINNER,
    PR_CI_SUCCESS,
    PR_REVIEW_APPROVED,
    PR_REVIEW_CHANGES_REQUESTED,
    PR_REVIEW_PENDING,
    PR_STATE_CLOSED,
    PR_STATE_DRAFT,
    PR_STATE_MERGED,
    PR_STATE_OPEN,
    SESSION_INDICATOR,
)

__all__ = [
    "AGENT_IDLE",
    "AGENT_WAITING",
    "AGENT_WORKING_SPINNER",
    "BRANCH_DIRTY",
    "ICON_AGENT",
    "ICON_BRANCH",
    "ICON_EXTERNAL_LINK",
    "ICON_FOLDER",
    "ICON_GITHUB",
    "ICON_GITLAB",
    "ICON_PLAIN_SESSION",
    "ICON_PR",
    "ICON_REVIEW_REQUEST",
    "PR_CI_FAILURE",
    "PR_CI_PENDING",
    "PR_CI_PENDING_SPINNER",
    "PR_CI_SUCCESS",
    "PR_REVIEW_APPROVED",
    "PR_REVIEW_CHANGES_REQUESTED",
    "PR_REVIEW_PENDING",
    "PR_STATE_CLOSED",
    "PR_STATE_DRAFT",
    "PR_STATE_MERGED",
    "PR_STATE_OPEN",
    "SESSION_INDICATOR",
]
