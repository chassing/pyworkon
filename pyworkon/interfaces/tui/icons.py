# Nerd Font / Unicode icons used in the sidebar TUI.
# Defined as constants with explicit Unicode escapes to survive formatters and editors.

# Session indicators
INDICATOR_CURRENT = "●"
INDICATOR_OTHER = "○"

# Git / PR detail icons
ICON_BRANCH = ""  # (nf-pl-branchadfadfadfadf)
ICON_PR = ""  # (nf-dev-git_pull_request)
ICON_AGENT = ""  # (nf-fa-cog)
ICON_FOLDER = ""  # (nf-fa-folder_open)
ICON_PLAIN_SESSION = "▸"  # ▸

# Provider icons
ICON_GITHUB = ""  # (nf-fa-github)
ICON_GITLAB = ""  # (nf-fa-gitlab)

# Agent status icons (single-width Nerd Font)
AGENT_IDLE = ""  #  (nf-fa-moon_o)
AGENT_WORKING = ""  #  (nf-fa-cog)
AGENT_WAITING = ""  #  (nf-fa-clock_o)

# Branch status icons (with Rich markup)
BRANCH_DIRTY = "[yellow][/]"  #  (nf-fa-pencil)

# PR status icons (with Rich markup)
PR_CI_SUCCESS = "[green]✓[/]"
PR_CI_FAILURE = "[red]✗[/]"
PR_CI_PENDING = "[yellow][/]"

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
