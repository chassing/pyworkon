import re
import sys

from iterfzf import iterfzf

from pyworkon.interfaces.shell import cli
from pyworkon.project import project_manager
from pyworkon.tmux_mgr import tmux_manager

_CYAN = "\033[36m"
_RESET = "\033[0m"
_ANSI_RE = re.compile(r"\033\[[0-9;]*m")


def _build_fzf_items() -> list[str]:
    """Build unified fzf item list: sessions first (cyan), then projects."""
    sessions = tmux_manager.list_sessions_with_project_id()
    session_project_ids = {project_id for _, project_id in sessions if project_id}

    items: list[str] = []
    for name, _ in sessions:
        items.append(f"{_CYAN}[session] {name}{_RESET}")

    items.extend(
        f"[project] {project.id}"
        for project in project_manager.list(local=True)
        if project.id not in session_project_ids
    )

    return items


def _parse_selection(selection: str) -> tuple[str, str]:
    """Parse fzf selection into (kind, value)."""
    clean = _ANSI_RE.sub("", selection)
    if clean.startswith("[session] "):
        return ("session", clean.removeprefix("[session] "))
    return ("project", clean.removeprefix("[project] "))


@cli.command()
def tmux() -> None:
    """Tmux integration for pyworkon."""
    while items := _build_fzf_items():
        result = iterfzf(
            items,
            ansi=True,
            exact=True,
            multi=True,
            __extra__=[
                "--expect=ctrl-x",
                "--border",
                "--border-label= ctrl-x: kill session ",
                "--border-label-pos=2:bottom",
            ],
        )

        if not result:
            sys.exit(0)

        key, *selections = result
        if not selections:
            sys.exit(0)

        kind, value = _parse_selection(selections[0])

        if key == "ctrl-x":
            if kind == "session":
                tmux_manager.kill_session(value)
            continue

        match kind:
            case "session":
                tmux_manager.attach_session(value)
            case "project":
                tmux_manager.enter(value)
        break
