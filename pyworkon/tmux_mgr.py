# ruff: noqa: S607
import contextlib
import os
import subprocess
from pathlib import Path

from pyworkon.daemon.project_mgr import Project

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

    def select_pane(self, session_name: str, pane_id: str) -> None:
        """Switch to a session and select a specific pane."""
        self.attach_session(session_name)
        subprocess.run(
            ["tmux", "select-pane", "-t", pane_id],
            check=True,
        )

    def get_pane_session(self, pane_id: str) -> str | None:
        """Get the tmux session name that contains a pane."""
        with contextlib.suppress(subprocess.CalledProcessError):
            result = subprocess.run(
                ["tmux", "display-message", "-t", pane_id, "-p", "#{session_name}"],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip() or None
        return None

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

    def get_current_session(self) -> str | None:
        """Get the name of the current tmux session."""
        with contextlib.suppress(subprocess.CalledProcessError):
            result = subprocess.run(
                ["tmux", "display-message", "-p", "#{session_name}"],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip() or None
        return None

    def set_pane_variable(self, pane_id: str, variable: str, value: str) -> None:
        """Set a user-defined pane option."""
        subprocess.run(
            ["tmux", "set-option", "-p", "-t", pane_id, variable, value],
            check=True,
        )

    def set_window_variable(self, window_id: str, variable: str, value: str) -> None:
        """Set a user-defined window option."""
        subprocess.run(
            ["tmux", "set-option", "-w", "-t", window_id, variable, value],
            check=True,
        )

    def unset_window_variable(self, window_id: str, variable: str) -> None:
        """Unset a user-defined window option."""
        with contextlib.suppress(subprocess.CalledProcessError):
            subprocess.run(
                ["tmux", "set-option", "-wu", "-t", window_id, variable],
                check=True,
            )

    def set_session_variable(
        self, session_name: str, variable: str, value: str
    ) -> None:
        """Set a user-defined session option."""
        subprocess.run(
            ["tmux", "set-option", "-t", session_name, variable, value],
            check=True,
        )

    def find_sidebar_pane(self) -> str | None:
        """Find the sidebar pane in the current window (if any)."""
        with contextlib.suppress(subprocess.CalledProcessError):
            result = subprocess.run(
                ["tmux", "list-panes", "-F", "#{pane_id}|#{@pyworkon_sidebar}"],
                capture_output=True,
                text=True,
                check=True,
            )
            for line in result.stdout.splitlines():
                pane_id, _, marker = line.partition("|")
                if marker:
                    return pane_id
        return None

    def split_window(
        self,
        cmd: str,
        width: int,
        *,
        title: str | None = None,
        no_focus: bool = False,
    ) -> str | None:
        """Split the current window to create a sidebar pane on the left."""
        with contextlib.suppress(subprocess.CalledProcessError):
            window_name = subprocess.run(
                ["tmux", "display-message", "-p", "#{window_name}"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()

            flags = "-hbdf" if no_focus else "-hbf"
            result = subprocess.run(
                [
                    "tmux",
                    "split-window",
                    flags,
                    "-l",
                    str(width),
                    "-P",
                    "-F",
                    "#{pane_id}",
                    cmd,
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            pane_id = result.stdout.strip()
            if pane_id and title:
                subprocess.run(
                    ["tmux", "select-pane", "-t", pane_id, "-T", title],
                    check=False,
                )
            if window_name:
                subprocess.run(
                    ["tmux", "rename-window", window_name],
                    check=False,
                )
            return pane_id or None
        return None

    def kill_pane(self, pane_id: str) -> None:
        """Kill a tmux pane."""
        subprocess.run(
            ["tmux", "kill-pane", "-t", pane_id],
            check=True,
        )

    def set_hook(self, session_name: str, hook_name: str, command: str) -> None:
        """Set a tmux hook on a session."""
        subprocess.run(
            [
                "tmux",
                "set-hook",
                "-t",
                session_name,
                hook_name,
                command,
            ],
            check=True,
        )

    def unset_hook(self, session_name: str, hook_name: str) -> None:
        """Remove a tmux hook from a session."""
        with contextlib.suppress(subprocess.CalledProcessError):
            subprocess.run(
                ["tmux", "set-hook", "-u", "-t", session_name, hook_name],
                check=True,
            )

    def batch_collect_agents(self) -> dict[str, list[tuple[str, str]]]:
        """Collect agent info for all sessions in one tmux call."""
        agents: dict[str, list[tuple[str, str]]] = {}
        with contextlib.suppress(subprocess.CalledProcessError):
            result = subprocess.run(
                [
                    "tmux",
                    "list-windows",
                    "-a",
                    "-F",
                    "#{session_name}|#{@pyworkon_agent_name}|#{@pyworkon_agent_status}",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            expected_parts = 3
            for line in result.stdout.splitlines():
                parts = line.split("|", 2)
                if len(parts) < expected_parts or not parts[1]:
                    continue
                session_name, agent_name, agent_status = parts
                agents.setdefault(session_name, []).append((agent_name, agent_status))
        return agents

    def enter(self, project: Project) -> None:
        """Enter a project in a tmux session."""
        session_name = project.name

        if session_name in self.list_sessions():
            self.attach_session(session_name)
        else:
            self.create_session(session_name, project)
            self.attach_session(session_name)


tmux_manager = TmuxManager()
