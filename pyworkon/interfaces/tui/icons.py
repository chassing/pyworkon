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
AGENT_WAITING = ""  #  (nf-fa-clock_o)

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
