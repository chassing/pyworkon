# ruff: noqa: S607
import contextlib
import os
import subprocess
from pathlib import Path

from pyworkon.project import Project, project_manager

_DEFAULT_TMUXP_CONFIG = Path(__file__).parent / "defaults" / "tmuxp.yml"


class TmuxManager:
    """Tmux integration for pyworkon."""

    def __init__(self) -> None:
        pass

    def list_sessions(self) -> list[str]:
        """List all tmux sessions."""
        with contextlib.suppress(subprocess.CalledProcessError):
            result = subprocess.run(
                ["tmux", "list-sessions", "-F", "#{session_name}"],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.splitlines()

        return []

    def attach_session(self, session_name: str) -> None:
        """Switch to a tmux session (from within tmux)."""
        subprocess.run(
            ["tmux", "switch-client", "-t", session_name],
            check=True,
        )

    def create_session(self, session_name: str, project: Project) -> None:
        """Create a new detached tmux session with tmuxp layout."""
        project_config = project.project_home / ".tmuxp.yml"
        config_path = (
            project_config if project_config.exists() else _DEFAULT_TMUXP_CONFIG
        )

        subprocess.run(
            ["tmuxp", "load", "-d", "-s", session_name, str(config_path)],
            check=True,
            cwd=project.project_home,
            env={**os.environ, **project.env_vars},
        )

    def list_sessions_with_project_id(self) -> list[tuple[str, str | None]]:
        """List all tmux sessions with their pyworkon project ID (if set)."""
        sessions: list[tuple[str, str | None]] = []
        for name in self.list_sessions():
            project_id = None
            with contextlib.suppress(subprocess.CalledProcessError):
                result = subprocess.run(
                    ["tmux", "show-environment", "-t", name, "PYWORKON_PROJECT_ID"],
                    capture_output=True,
                    text=True,
                    check=True,
                )

                _, _, project_id = result.stdout.strip().partition("=")
            sessions.append((name, project_id or None))
        return sessions

    def kill_session(self, session_name: str) -> None:
        """Kill a tmux session."""
        subprocess.run(
            ["tmux", "kill-session", "-t", session_name],
            check=True,
        )

    def enter(self, project_id: str) -> None:
        """Enter a project in a tmux session."""
        project = project_manager.get(project_id=project_id)
        session_name = project.name

        if session_name in self.list_sessions():
            self.attach_session(session_name)
        else:
            self.create_session(session_name, project)
            self.attach_session(session_name)


tmux_manager = TmuxManager()
