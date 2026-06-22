"""pyworkon daemon — fully async Unix socket server with polling."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import operator
import os
import time
from collections.abc import AsyncGenerator
from typing import ClassVar

from pyworkon.config import config, user_cache_dir
from pyworkon.daemon.models import AgentInfo, OpenProject
from pyworkon.daemon.protocol import (
    Command,
    CommandType,
    Response,
    ResponseType,
    error,
    ok,
    progress,
)

log = logging.getLogger(__name__)

AsyncResponseIterator = AsyncGenerator[Response, None]

SOCKET_PATH = user_cache_dir / "daemon.sock"
PID_FILE = user_cache_dir / "daemon.pid"
PR_CACHE_TTL = 60.0
PROVIDER_SYNC_INTERVAL = 86400


class Daemon:
    """Central pyworkon daemon — fully async."""

    def __init__(self) -> None:
        from pyworkon.daemon.project_mgr import ProjectManager

        self._project_mgr = ProjectManager()
        self._open_projects: dict[str, OpenProject] = {}
        self._tmux_sessions: list[tuple[str, str | None]] = []
        self._plain_sessions: list[str] = []
        self._last_provider_sync: float = time.monotonic()
        self._running = True

    async def start(self) -> None:
        """Start the daemon server."""
        SOCKET_PATH.parent.mkdir(parents=True, exist_ok=True)
        if SOCKET_PATH.exists():
            SOCKET_PATH.unlink()

        await self._poll_tmux()

        server = await asyncio.start_unix_server(
            self._handle_client, path=str(SOCKET_PATH)
        )
        PID_FILE.write_text(str(os.getpid()))
        log.info("Daemon started. Socket: %s, PID: %s", SOCKET_PATH, os.getpid())

        try:
            async with server:
                poll_task = asyncio.create_task(self._polling_loop())
                await asyncio.gather(server.serve_forever(), poll_task)
        except SystemExit:
            log.info("Shutdown requested.")
        finally:
            poll_task.cancel()
            self._cleanup()

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        log.debug("Client connected")
        try:
            await self._process_client(reader, writer)
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        except SystemExit:
            raise
        finally:
            log.debug("Client disconnected")
            with contextlib.suppress(Exception):
                writer.close()
                await writer.wait_closed()

    async def _process_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        while data := await reader.readline():
            line = data.decode().strip()
            if not line:
                continue
            try:
                cmd = Command(**json.loads(line))
            except (json.JSONDecodeError, ValueError):
                await self._send(writer, error("Invalid command"))
                continue

            log.debug("Command: %s", cmd.cmd)
            gen = self._dispatch(cmd)
            try:
                async for resp in gen:
                    await self._send(writer, resp)
                    if resp.type in {ResponseType.OK, ResponseType.ERROR}:
                        break
            finally:
                await gen.aclose()

            if cmd.cmd == CommandType.SHUTDOWN:
                self._running = False
                raise SystemExit

    _HANDLERS: ClassVar[dict[CommandType, str]] = {
        CommandType.LIST_PROJECTS: "_cmd_list_projects",
        CommandType.GET_PROJECT: "_cmd_get_project",
        CommandType.OPEN_PROJECT: "_cmd_open_project",
        CommandType.CLOSE_PROJECT: "_cmd_close_project",
        CommandType.CLONE_PROJECT: "_cmd_clone_project",
        CommandType.SYNC_PROVIDERS: "_cmd_sync_providers",
        CommandType.GET_SIDEBAR_STATE: "_cmd_get_sidebar_state",
        CommandType.AGENT_STATUS: "_cmd_agent_status",
        CommandType.AGENT_CLEAR: "_cmd_agent_clear",
        CommandType.STATUS: "_cmd_status",
        CommandType.SHUTDOWN: "_cmd_shutdown",
    }

    async def _dispatch(self, cmd: Command) -> AsyncResponseIterator:
        if handler_name := self._HANDLERS.get(cmd.cmd):
            handler = getattr(self, handler_name)
            async for resp in handler(cmd):
                yield resp
            return
        yield error(f"Unknown command: {cmd.cmd}")

    async def _cmd_shutdown(self, cmd: Command) -> AsyncResponseIterator:
        yield ok()

    async def _cmd_list_projects(self, cmd: Command) -> AsyncResponseIterator:
        local = cmd.local if cmd.local is not None else True
        projects = self._project_mgr.list(local=local)
        yield Response(
            type=ResponseType.PROJECTS,
            data={"projects": [p.model_dump() for p in projects]},
        )

    async def _cmd_get_project(self, cmd: Command) -> AsyncResponseIterator:
        if not cmd.project_id:
            yield error("project_id required")
            return
        try:
            project = self._project_mgr.get(cmd.project_id)
            yield Response(
                type=ResponseType.PROJECT, data={"project": project.model_dump()}
            )
        except KeyError:
            yield error(f"Project not found: {cmd.project_id}")

    async def _cmd_open_project(self, cmd: Command) -> AsyncResponseIterator:
        if not cmd.project_id:
            yield error("project_id required")
            return
        # Remove existing entry for this project (e.g. tmux-discovered)
        stale = [
            k for k, v in self._open_projects.items() if v.project_id == cmd.project_id
        ]
        for k in stale:
            del self._open_projects[k]
        session = (
            cmd.session
            or self._find_session_for_project(cmd.project_id)
            or await self._find_session_for_pane(cmd.pane_id)
        )
        key = f"{cmd.project_id}|{cmd.pane_id or 'default'}"
        self._open_projects[key] = OpenProject(
            project_id=cmd.project_id,
            pane_id=cmd.pane_id,
            session=session,
        )
        log.info(
            "Project opened: %s (pane=%s, session=%s)",
            cmd.project_id,
            cmd.pane_id,
            session,
        )
        yield ok()

    def _find_session_for_project(self, project_id: str) -> str | None:
        """Find tmux session name for a project ID from polled data."""
        return next(
            (name for name, pid in self._tmux_sessions if pid == project_id),
            None,
        )

    @staticmethod
    async def _find_session_for_pane(pane_id: str | None) -> str | None:
        """Resolve tmux session name from a pane ID."""
        if not pane_id:
            return None
        from pyworkon.tmux_mgr import tmux_manager

        return await tmux_manager.get_pane_session(pane_id)

    async def _cmd_close_project(self, cmd: Command) -> AsyncResponseIterator:
        if not cmd.project_id:
            yield error("project_id required")
            return
        key = f"{cmd.project_id}|{cmd.pane_id or 'default'}"
        if self._open_projects.pop(key, None):
            log.info("Project closed: %s (pane=%s)", cmd.project_id, cmd.pane_id)
        yield ok()

    async def _cmd_clone_project(self, cmd: Command) -> AsyncResponseIterator:
        if not cmd.project_id:
            yield error("project_id required")
            return
        try:
            project = self._project_mgr.get(cmd.project_id)
        except KeyError:
            yield error(f"Project not found: {cmd.project_id}")
            return
        yield progress(f"Cloning {cmd.project_id}...")
        await project.clone()
        yield ok()

    async def _cmd_sync_providers(self, cmd: Command) -> AsyncResponseIterator:
        for provider in config.providers:
            yield progress(f"Fetching projects from {provider.name}...")
        await self._project_mgr.sync(force=True)
        self._last_provider_sync = time.monotonic()
        yield ok()

    async def _cmd_get_sidebar_state(self, cmd: Command) -> AsyncResponseIterator:
        sessions = []
        for op in self._open_projects.values():
            try:
                project = self._project_mgr.get(op.project_id)
            except KeyError:
                continue
            sessions.append({
                "session_name": op.session or project.name,
                "project": project.model_dump(),
                "branch": op.branch,
                "pr": op.pr_data,
                "agents": [{"name": a.name, "status": a.status} for a in op.agents],
                "pane_id": op.pane_id,
            })
        sessions.sort(key=operator.itemgetter("session_name"))
        yield Response(
            type=ResponseType.SIDEBAR_STATE,
            data={
                "sessions": sessions,
                "plain_sessions": sorted(self._plain_sessions),
                "projects": [
                    p.model_dump()
                    for p in self._project_mgr.list(local=True)
                    if not any(
                        op.project_id == p.id for op in self._open_projects.values()
                    )
                ],
            },
        )

    async def _cmd_agent_status(self, cmd: Command) -> AsyncResponseIterator:
        if not cmd.session or not cmd.name:
            yield error("session and name required")
            return
        new_status = cmd.status or ""
        for op in self._open_projects.values():
            if op.session == cmd.session:
                existing = next((a for a in op.agents if a.name == cmd.name), None)
                if existing:
                    if existing.status == new_status:
                        yield ok()
                        return
                    existing.status = new_status
                else:
                    op.agents.append(AgentInfo(name=cmd.name, status=new_status))
                log.info("Agent %s in %s: %s", cmd.name, cmd.session, new_status)
                yield ok()
                return
        yield error(f"No open project for session: {cmd.session}")

    async def _cmd_agent_clear(self, cmd: Command) -> AsyncResponseIterator:
        if not cmd.session or not cmd.name:
            yield error("session and name required")
            return
        for op in self._open_projects.values():
            if op.session == cmd.session:
                op.agents = [a for a in op.agents if a.name != cmd.name]
                yield ok()
                return
        yield ok()

    async def _cmd_status(self, cmd: Command) -> AsyncResponseIterator:
        yield Response(
            type=ResponseType.STATUS,
            data={
                "open_projects": len(self._open_projects),
                "total_projects": len(self._project_mgr.list(local=True)),
                "pid": os.getpid(),
            },
        )

    async def _polling_loop(self) -> None:
        while self._running:
            try:
                await self._poll_tmux()
                await asyncio.gather(
                    self._poll_git_branches(),
                    self._poll_pr_data(),
                )
                await self._maybe_sync_providers()
            except Exception:
                log.exception("Error in polling loop")
            await asyncio.sleep(config.sidebar_refresh_interval)

    async def _poll_tmux(self) -> None:
        from pyworkon.tmux_mgr import tmux_manager

        self._tmux_sessions = await tmux_manager.list_sessions_with_project_id()
        self._plain_sessions = [name for name, pid in self._tmux_sessions if not pid]

        tmux_project_ids = {pid for _, pid in self._tmux_sessions if pid}
        tracked_by_project = {op.project_id: op for op in self._open_projects.values()}
        for pid in tmux_project_ids:
            session_name = next(
                (name for name, p in self._tmux_sessions if p == pid), None
            )
            if existing := tracked_by_project.get(pid):
                if not existing.session and session_name:
                    existing.session = session_name
                continue
            key = f"{pid}|tmux"
            self._open_projects[key] = OpenProject(
                project_id=pid, pane_id=None, session=session_name
            )
            log.info("Discovered tmux session: %s (%s)", session_name, pid)

        active_sessions = set(await tmux_manager.list_sessions())
        stale = [
            k
            for k, v in self._open_projects.items()
            if (k.endswith("|tmux") and v.project_id not in tmux_project_ids)
            or (
                not k.endswith("|tmux")
                and v.session
                and v.session not in active_sessions
            )
        ]
        for k in stale:
            log.info("Removed stale project: %s", k)
            del self._open_projects[k]

    async def _poll_git_branches(self) -> None:
        async def _poll_one(op: OpenProject) -> None:
            with contextlib.suppress(KeyError):
                project = self._project_mgr.get(op.project_id)
                op.branch = await project.get_current_branch()

        await asyncio.gather(*(_poll_one(op) for op in self._open_projects.values()))

    async def _poll_pr_data(self) -> None:
        now = time.monotonic()
        tasks: list[asyncio.Task[None]] = []
        for op in list(self._open_projects.values()):
            if now - op.pr_fetched_at < PR_CACHE_TTL or not op.branch:
                continue
            tasks.append(asyncio.create_task(self._fetch_pr_for_project(op, now)))
        if tasks:
            await asyncio.gather(*tasks)

    async def _fetch_pr_for_project(self, op: OpenProject, now: float) -> None:
        project = self._project_mgr.get(op.project_id)
        pr = await project.get_pr_info(op.branch or "")
        op.pr_data = pr.model_dump() if pr else None
        op.pr_fetched_at = now
        if pr:
            log.info("PR data: %s #%s (%s)", op.project_id, pr.number, pr.state)

    async def _maybe_sync_providers(self) -> None:
        if time.monotonic() - self._last_provider_sync > PROVIDER_SYNC_INTERVAL:
            log.info("Auto-syncing providers...")
            await self._project_mgr.sync()
            self._last_provider_sync = time.monotonic()

    @staticmethod
    async def _send(writer: asyncio.StreamWriter, response: Response) -> None:
        writer.write(response.model_dump_json().encode() + b"\n")
        await writer.drain()

    @staticmethod
    def _cleanup() -> None:
        with contextlib.suppress(FileNotFoundError):
            SOCKET_PATH.unlink()
        with contextlib.suppress(FileNotFoundError):
            PID_FILE.unlink()
        log.info("Daemon stopped.")


def run_daemon(*, debug: bool = False) -> None:
    """Entry point for running the daemon."""
    if debug:
        logging.basicConfig(
            level="INFO",
            format="%(asctime)s %(name)s %(levelname)s: %(message)s",
            force=True,
        )
        logging.getLogger("pyworkon").setLevel("DEBUG")
    else:
        log_file = user_cache_dir / "daemon.log"
        log_handle = log_file.open("a")
        logging.basicConfig(
            level="INFO",
            format="%(asctime)s %(name)s %(levelname)s: %(message)s",
            handlers=[logging.FileHandler(log_file)],
            force=True,
        )
        import sys

        sys.stdout = log_handle
        sys.stderr = log_handle

    daemon = Daemon()
    with contextlib.suppress(KeyboardInterrupt, SystemExit):
        asyncio.run(daemon.start())
