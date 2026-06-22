# Nerd Font / Unicode icons used in the sidebar TUI.
# Defined as constants with explicit Unicode escapes to survive formatters and editors.

# Session indicators
INDICATOR_CURRENT = "●"
INDICATOR_OTHER = "○"

# Git / PR detail icons
ICON_BRANCH = ""  # (nf-pl-branch)
ICON_PR = ""  # (nf-dev-git_pull_request)
ICON_AGENT = "\U000f167a"  # 󱙺 (nf-md-robot_outline)
ICON_FOLDER = ""  # (nf-fa-folder_open)
ICON_PLAIN_SESSION = "▸"  # ▸

# Provider icons
ICON_GITHUB = ""  # (nf-fa-github)
ICON_GITLAB = ""  # (nf-fa-gitlab)

# PR status icons (with Rich markup)
PR_CI_SUCCESS = "[green]✓[/]"
PR_CI_FAILURE = "[red]✗[/]"
PR_CI_PENDING = "[yellow]◷[/]"

# PR state icons (with Rich markup)
PR_STATE_OPEN = "[green]●[/]"
PR_STATE_CLOSED = "[red]●[/]"
PR_STATE_MERGED = "[purple]●[/]"
