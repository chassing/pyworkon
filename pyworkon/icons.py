"""Shared icon glyphs -- single source of truth for the TUI, relay dashboard, and strip.

A dependency-free leaf module (no imports besides stdlib `re`): the relay's
isolation requirement (see `interfaces/relay/schema.py`) means nothing that
reaches it transitively may import `pyworkon.config`, and the strip must not
depend on `interfaces/relay` at all -- so these glyphs live here, outside
every `interfaces/*` subpackage, rather than in `interfaces/tui/icons.py`
with the relay and strip importing from the TUI (or from each other) to get
at them. `interfaces/tui/icons.py` and `interfaces/relay/icons.py` are now
thin re-export shims over this module, kept so existing import sites in
those packages don't need to change -- see AGENTS.md's "Strip" section for
why the TUI package in particular is expected to go away eventually, which
is exactly why nothing outside it should depend on it for shared constants.
"""

from __future__ import annotations

import re

# Nerd Font / Unicode icons used in the sidebar TUI.
# Defined as constants with explicit Unicode escapes to survive formatters and editors.

# Session indicators
SESSION_INDICATOR = "●"

# Git / PR detail icons
ICON_BRANCH = ""  # (nf-pl-branchadfadfadfadf)
ICON_PR = ""  # (nf-dev-git_pull_request)
ICON_AGENT = ""  # (nf-fa-cog)
ICON_FOLDER = ""  # (nf-fa-folder_open)
ICON_PLAIN_SESSION = "▸"  # ▸
# Plain Unicode (not a Nerd Font PUA glyph) -- the strip's embedded webfont is
# a hand-picked subset (see relay/static/fonts/NERD_FONTS_LICENSE.txt) that
# doesn't include a "link" glyph, and adding one means downloading the real
# Nerd Font source + fonttools to regenerate it. A plain arrow renders fine
# via the default system font without touching the embedded font at all.
ICON_EXTERNAL_LINK = "↗"  # external link (e.g. to a repository)

# Provider icons
ICON_GITHUB = ""  # (nf-fa-github)
ICON_GITLAB = ""  # (nf-fa-gitlab)

# Agent status icons (single-width Nerd Font)
AGENT_IDLE = ""  #  (nf-fa-moon_o)
AGENT_WORKING_SPINNER = "dots"
AGENT_WAITING = ""  #  (nf-fa-question_circle_o)

# Branch status icons (with Rich markup)
BRANCH_DIRTY = "[yellow][/]"  #  (nf-fa-pencil)

# PR status icons (with Rich markup)
PR_CI_SUCCESS = "[green]✓[/]"
PR_CI_FAILURE = "[red]✗[/]"
PR_CI_PENDING = "[yellow][/]"
PR_CI_PENDING_SPINNER = "dots"

# PR state icons (with Rich markup)
PR_STATE_OPEN = "[green]●[/]"
PR_STATE_CLOSED = "[red]●[/]"
PR_STATE_MERGED = "[purple]●[/]"
PR_STATE_DRAFT = "[dim]●[/]"

# PR review icons (with Rich markup)
PR_REVIEW_APPROVED = "[green]✓[/]"
PR_REVIEW_CHANGES_REQUESTED = "[red]✗[/]"
PR_REVIEW_PENDING = "[yellow]○[/]"

# Review request icon
ICON_REVIEW_REQUEST = ""  # (nf-fa-eye)

_RICH_MARKUP = re.compile(r"\[[^\]]*\]")


def _glyph(value: str) -> str:
    return _RICH_MARKUP.sub("", value)


# Icons shared by every non-terminal UI surface (the strip's chip row/popup/
# picker, and the relay web dashboard) -- Rich color markup is stripped since
# those surfaces color via their own CSS classes instead.
DASHBOARD_ICONS: dict[str, str] = {
    "branch": ICON_BRANCH,
    "pr": ICON_PR,
    "agent": ICON_AGENT,
    "github": ICON_GITHUB,
    "gitlab": ICON_GITLAB,
    "externalLink": ICON_EXTERNAL_LINK,
    "plainSession": ICON_PLAIN_SESSION,
    "agentIdle": AGENT_IDLE,
    "agentWaiting": AGENT_WAITING,
    "reviewRequest": ICON_REVIEW_REQUEST,
    "dirty": _glyph(BRANCH_DIRTY),
    "ciSuccess": _glyph(PR_CI_SUCCESS),
    "ciFailure": _glyph(PR_CI_FAILURE),
    "ciPending": _glyph(PR_CI_PENDING),
    "stateOpen": _glyph(PR_STATE_OPEN),
    "stateClosed": _glyph(PR_STATE_CLOSED),
    "stateMerged": _glyph(PR_STATE_MERGED),
    "stateDraft": _glyph(PR_STATE_DRAFT),
    "reviewApproved": _glyph(PR_REVIEW_APPROVED),
    "reviewChangesRequested": _glyph(PR_REVIEW_CHANGES_REQUESTED),
    "reviewPending": _glyph(PR_REVIEW_PENDING),
}
