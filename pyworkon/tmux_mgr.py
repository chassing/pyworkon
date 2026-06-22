import asyncio
import contextlib
import os
import subprocess
from pathlib import Path

from pyworkon.daemon.project_mgr import Project
from pyworkon.utils import run_cmd

_DEFAULT_TMUXP_CONFIG = Path(__file__).parent / "defaults" / "tmuxp.yml"


class TmuxManager:
    """Tmux integration for pyworkon."""

    def __init__(self) -> None:
        pass

    async def list_sessions(self) -> list[str]:
        """List all tmux sessions."""
        with contextlib.suppress(subprocess.CalledProcessError):
            result = await run_cmd(
                "tmux",
                "list-sessions",
                "-F",
                "#{session_name}",
            )
            return result.stdout.splitlines()

        return []

    async def attach_session(self, session_name: str) -> None:
        """Switch to a tmux session (from within tmux)."""
        await run_cmd("tmux", "switch-client", "-t", session_name)

    async def select_pane(self, session_name: str, pane_id: str) -> None:
        """Switch to a session and select a specific pane."""
        await self.attach_session(session_name)
        await run_cmd("tmux", "select-pane", "-t", pane_id)

    async def get_pane_session(self, pane_id: str) -> str | None:
        """Get the tmux session name that contains a pane."""
        with contextlib.suppress(subprocess.CalledProcessError):
            result = await run_cmd(
                "tmux",
                "display-message",
                "-t",
                pane_id,
                "-p",
                "#{session_name}",
            )
            return result.stdout.strip() or None
        return None

    async def create_session(self, session_name: str, project: Project) -> None:
        """Create a new detached tmux session with tmuxp layout."""
        project_config = project.project_home / ".tmuxp.yml"
        config_path = (
            project_config if project_config.exists() else _DEFAULT_TMUXP_CONFIG
        )

        await run_cmd(
            "tmuxp",
            "load",
            "-d",
            "-s",
            session_name,
            str(config_path),
            cwd=project.project_home,
            env={**os.environ, **project.env_vars},
        )

    async def list_sessions_with_project_id(self) -> list[tuple[str, str | None]]:
        """List all tmux sessions with their pyworkon project ID (if set)."""
        sessions = await self.list_sessions()

        async def _get_project_id(name: str) -> tuple[str, str | None]:
            project_id = None
            with contextlib.suppress(subprocess.CalledProcessError):
                result = await run_cmd(
                    "tmux",
                    "show-environment",
                    "-t",
                    name,
                    "PYWORKON_PROJECT_ID",
                )
                _, _, project_id = result.stdout.strip().partition("=")
            return (name, project_id or None)

        return list(await asyncio.gather(*(_get_project_id(n) for n in sessions)))

    async def kill_session(self, session_name: str) -> None:
        """Kill a tmux session."""
        await run_cmd("tmux", "kill-session", "-t", session_name)

    async def get_current_session(self) -> str | None:
        """Get the name of the current tmux session."""
        with contextlib.suppress(subprocess.CalledProcessError):
            result = await run_cmd(
                "tmux",
                "display-message",
                "-p",
                "#{session_name}",
            )
            return result.stdout.strip() or None
        return None

    async def set_pane_variable(self, pane_id: str, variable: str, value: str) -> None:
        """Set a user-defined pane option."""
        await run_cmd(
            "tmux",
            "set-option",
            "-p",
            "-t",
            pane_id,
            variable,
            value,
        )

    async def set_window_variable(
        self, window_id: str, variable: str, value: str
    ) -> None:
        """Set a user-defined window option."""
        await run_cmd(
            "tmux",
            "set-option",
            "-w",
            "-t",
            window_id,
            variable,
            value,
        )

    async def unset_window_variable(self, window_id: str, variable: str) -> None:
        """Unset a user-defined window option."""
        with contextlib.suppress(subprocess.CalledProcessError):
            await run_cmd(
                "tmux",
                "set-option",
                "-wu",
                "-t",
                window_id,
                variable,
            )

    async def set_session_variable(
        self, session_name: str, variable: str, value: str
    ) -> None:
        """Set a user-defined session option."""
        await run_cmd(
            "tmux",
            "set-option",
            "-t",
            session_name,
            variable,
            value,
        )

    async def find_sidebar_pane(self) -> str | None:
        """Find the sidebar pane in the current window (if any)."""
        with contextlib.suppress(subprocess.CalledProcessError):
            result = await run_cmd(
                "tmux",
                "list-panes",
                "-F",
                "#{pane_id}|#{@pyworkon_sidebar}",
            )
            for line in result.stdout.splitlines():
                pane_id, _, marker = line.partition("|")
                if marker:
                    return pane_id
        return None

    async def split_window(
        self,
        cmd: str,
        width: int,
        *,
        title: str | None = None,
        no_focus: bool = False,
    ) -> str | None:
        """Split the current window to create a sidebar pane on the left."""
        with contextlib.suppress(subprocess.CalledProcessError):
            window_result = await run_cmd(
                "tmux",
                "display-message",
                "-p",
                "#{window_name}",
            )
            window_name = window_result.stdout.strip()

            flags = "-hbdf" if no_focus else "-hbf"
            result = await run_cmd(
                "tmux",
                "split-window",
                flags,
                "-l",
                str(width),
                "-P",
                "-F",
                "#{pane_id}",
                cmd,
            )
            pane_id = result.stdout.strip()
            if pane_id and title:
                await run_cmd(
                    "tmux",
                    "select-pane",
                    "-t",
                    pane_id,
                    "-T",
                    title,
                    check=False,
                )
            if window_name:
                await run_cmd("tmux", "rename-window", window_name, check=False)
            return pane_id or None
        return None

    async def kill_pane(self, pane_id: str) -> None:
        """Kill a tmux pane."""
        await run_cmd("tmux", "kill-pane", "-t", pane_id)

    async def set_hook(self, session_name: str, hook_name: str, command: str) -> None:
        """Set a tmux hook on a session."""
        await run_cmd(
            "tmux",
            "set-hook",
            "-t",
            session_name,
            hook_name,
            command,
        )

    async def unset_hook(self, session_name: str, hook_name: str) -> None:
        """Remove a tmux hook from a session."""
        with contextlib.suppress(subprocess.CalledProcessError):
            await run_cmd(
                "tmux",
                "set-hook",
                "-u",
                "-t",
                session_name,
                hook_name,
            )

    async def batch_collect_agents(self) -> dict[str, list[tuple[str, str]]]:
        """Collect agent info for all sessions in one tmux call."""
        agents: dict[str, list[tuple[str, str]]] = {}
        with contextlib.suppress(subprocess.CalledProcessError):
            result = await run_cmd(
                "tmux",
                "list-windows",
                "-a",
                "-F",
                "#{session_name}|#{@pyworkon_agent_name}|#{@pyworkon_agent_status}",
            )
            expected_parts = 3
            for line in result.stdout.splitlines():
                parts = line.split("|", 2)
                if len(parts) < expected_parts or not parts[1]:
                    continue
                session_name, agent_name, agent_status = parts
                agents.setdefault(session_name, []).append((agent_name, agent_status))
        return agents

    async def enter(self, project: Project) -> None:
        """Enter a project in a tmux session."""
        session_name = project.name

        if session_name in await self.list_sessions():
            await self.attach_session(session_name)
        else:
            await self.create_session(session_name, project)
            await self.attach_session(session_name)


tmux_manager = TmuxManager()
