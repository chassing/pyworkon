"""pyworkon daemon — fully async Unix socket server with event-based push."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import operator
import os
import subprocess
import sys
import time
from collections.abc import AsyncGenerator
from typing import Any, ClassVar

from pyworkon.config import Provider, ProviderType, config, user_cache_dir
from pyworkon.daemon.git_watcher import GitWatcher
from pyworkon.daemon.models import AgentInfo, OpenProject
from pyworkon.daemon.project_mgr import ProjectManager
from pyworkon.daemon.protocol import (
    Command,
    CommandType,
    Response,
    ResponseType,
    error,
    ok,
    progress,
)
from pyworkon.daemon.providers import get_provider
from pyworkon.daemon.providers.circuit_breaker import set_notification_callback
from pyworkon.daemon.providers.github import GitHubApi
from pyworkon.daemon.tmux_mgr import tmux_manager
from pyworkon.utils import run_cmd

log = logging.getLogger(__name__)

AsyncResponseIterator = AsyncGenerator[Response, None]

SOCKET_PATH = user_cache_dir / "daemon.sock"
PID_FILE = user_cache_dir / "daemon.pid"
PR_CACHE_TTL = 60.0
REVIEW_PR_CACHE_TTL = 60.0
PROVIDER_SYNC_INTERVAL = 86400


class Daemon:
    """Central pyworkon daemon — fully async."""

    def __init__(self) -> None:
        self._project_mgr = ProjectManager()
        self._open_projects: dict[str, OpenProject] = {}
        self._tmux_sessions: list[tuple[str, str | None]] = []
        self._plain_sessions: list[str] = []
        self._last_provider_sync: float = time.monotonic()
        self._review_prs: dict[str, list[dict[str, Any]]] = {}
        self._review_prs_fetched_at: float = 0.0
        self._running = True
        self._subscribers: dict[asyncio.StreamWriter, set[str]] = {}
        self._git_watcher = self._create_git_watcher()

    async def start(self) -> None:
        """Start the daemon server."""
        set_notification_callback(self._broadcast)

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
            await self._git_watcher.stop()
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
            self._subscribers.pop(writer, None)
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
            if cmd.cmd == CommandType.SUBSCRIBE:
                events = set(cmd.events or ["notification"])
                self._subscribers[writer] = events
                log.debug(
                    "Subscriber added (events=%s, %d total)",
                    events,
                    len(self._subscribers),
                )
                if cmd.full and "state" in events:
                    self._push_event(
                        "state", self._build_sidebar_state(), writer=writer
                    )

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
        CommandType.SUBSCRIBE: "_cmd_subscribe",
        CommandType.NOTIFY: "_cmd_notify",
        CommandType.KILL_SESSION: "_cmd_kill_session",
        CommandType.SWITCH_SESSION: "_cmd_switch_session",
        CommandType.ENTER_PROJECT: "_cmd_enter_project",
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

    async def _cmd_subscribe(self, cmd: Command) -> AsyncResponseIterator:
        yield ok()

    async def _cmd_notify(self, cmd: Command) -> AsyncResponseIterator:
        if not cmd.message:
            yield error("message required")
            return
        self._broadcast(cmd.level or "information", cmd.message)
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
        op = OpenProject(
            project_id=cmd.project_id,
            pane_id=cmd.pane_id,
            session=session,
        )
        self._open_projects[key] = op
        log.info(
            "Project opened: %s (pane=%s, session=%s)",
            cmd.project_id,
            cmd.pane_id,
            session,
        )
        with contextlib.suppress(KeyError):
            project = self._project_mgr.get(cmd.project_id)
            op.branch = await project.get_current_branch()
            op.is_dirty = await project.has_uncommitted_changes()
            await self._git_watcher.watch(cmd.project_id, project.project_home)
        self._push_event("state", self._build_sidebar_state())
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
        return await tmux_manager.get_pane_session(pane_id)

    async def _cmd_close_project(self, cmd: Command) -> AsyncResponseIterator:
        if not cmd.project_id:
            yield error("project_id required")
            return
        key = f"{cmd.project_id}|{cmd.pane_id or 'default'}"
        if self._open_projects.pop(key, None):
            log.info("Project closed: %s (pane=%s)", cmd.project_id, cmd.pane_id)
            remaining = any(
                op.project_id == cmd.project_id for op in self._open_projects.values()
            )
            if not remaining:
                await self._git_watcher.unwatch(cmd.project_id)
            self._push_event("state", self._build_sidebar_state())
        yield ok()

    async def _cmd_kill_session(self, cmd: Command) -> AsyncResponseIterator:
        if not cmd.session:
            yield error("session required")
            return
        session_name = cmd.session

        if not await self._is_pyworkon_session(session_name):
            self._broadcast(
                "warning",
                f"Session '{session_name}' was not created by pyworkon",
            )
            yield ok()
            return

        await tmux_manager.kill_session(session_name)

        removed_project_ids: list[str] = []
        stale = [k for k, v in self._open_projects.items() if v.session == session_name]
        for k in stale:
            op = self._open_projects.pop(k)
            removed_project_ids.append(op.project_id)
            log.info("Removed project for killed session: %s (%s)", k, session_name)

        for pid in set(removed_project_ids):
            remaining = any(op.project_id == pid for op in self._open_projects.values())
            if not remaining:
                await self._git_watcher.unwatch(pid)

        self._plain_sessions = [n for n in self._plain_sessions if n != session_name]
        self._push_event("state", self._build_sidebar_state())
        yield ok()

    @staticmethod
    async def _is_pyworkon_session(session_name: str) -> bool:
        """Check if a tmux session was created by pyworkon."""
        with contextlib.suppress(subprocess.CalledProcessError):
            result = await run_cmd(
                "tmux", "show-environment", "-t", session_name, "PYWORKON_PROJECT_ID"
            )
            return bool(result.stdout.strip())
        return False

    async def _cmd_switch_session(self, cmd: Command) -> AsyncResponseIterator:
        if not cmd.session:
            yield error("session required")
            return

        if cmd.pane_id:
            await tmux_manager.select_pane(cmd.session, cmd.pane_id)
        else:
            await tmux_manager.attach_session(cmd.session)
        yield ok()

    async def _cmd_enter_project(self, cmd: Command) -> AsyncResponseIterator:
        if not cmd.project_id:
            yield error("project_id required")
            return
        try:
            project = self._project_mgr.get(cmd.project_id)
        except KeyError:
            yield error(f"Project not found: {cmd.project_id}")
            return

        await tmux_manager.enter(project)
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

    def _build_sidebar_state(self) -> dict[str, Any]:
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
                "is_dirty": op.is_dirty,
                "pr": op.pr_data,
                "agents": [{"name": a.name, "status": a.status} for a in op.agents],
                "pane_id": op.pane_id,
            })
        sessions.sort(key=operator.itemgetter("session_name"))
        return {
            "sessions": sessions,
            "plain_sessions": sorted(self._plain_sessions),
            "projects": [
                p.model_dump()
                for p in self._project_mgr.list(local=True)
                if not any(op.project_id == p.id for op in self._open_projects.values())
            ],
            "review_prs": self._review_prs,
        }

    async def _cmd_get_sidebar_state(self, cmd: Command) -> AsyncResponseIterator:
        yield Response(
            type=ResponseType.SIDEBAR_STATE, data=self._build_sidebar_state()
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
                self._push_event("state", self._build_sidebar_state())
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
                self._push_event("state", self._build_sidebar_state())
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

    def _create_git_watcher(self) -> GitWatcher:
        return GitWatcher(
            on_branch_change=self._on_branch_change,
            on_dirty_change=self._on_dirty_change,
        )

    async def _on_branch_change(self, project_id: str) -> None:
        """Handle a branch change detected by the file watcher."""
        for op in self._open_projects.values():
            if op.project_id != project_id:
                continue
            with contextlib.suppress(KeyError):
                project = self._project_mgr.get(op.project_id)
                new_branch = await project.get_current_branch()
                if new_branch != op.branch:
                    op.pr_data = None
                    op.pr_fetched_at = 0.0
                op.branch = new_branch
                op.is_dirty = await project.has_uncommitted_changes()
            break
        self._push_event("state", self._build_sidebar_state())

    async def _on_dirty_change(self, project_id: str) -> None:
        """Handle a working tree change detected by the file watcher."""
        for op in self._open_projects.values():
            if op.project_id != project_id:
                continue
            with contextlib.suppress(KeyError):
                project = self._project_mgr.get(op.project_id)
                op.is_dirty = await project.has_uncommitted_changes()
            break
        self._push_event("state", self._build_sidebar_state())

    async def _polling_loop(self) -> None:
        while self._running:
            try:
                await self._poll_tmux()
                await self._poll_pr_data()
                await self._poll_review_prs()
                await self._maybe_sync_providers()
                self._push_event("state", self._build_sidebar_state())
            except Exception:
                log.exception("Error in polling loop")
            await asyncio.sleep(config.sidebar_refresh_interval)

    async def _poll_tmux(self) -> None:
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
            op = OpenProject(project_id=pid, pane_id=None, session=session_name)
            self._open_projects[key] = op
            log.info("Discovered tmux session: %s (%s)", session_name, pid)
            with contextlib.suppress(KeyError):
                project = self._project_mgr.get(pid)
                op.branch = await project.get_current_branch()
                op.is_dirty = await project.has_uncommitted_changes()
                await self._git_watcher.watch(pid, project.project_home)

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
            op = self._open_projects.pop(k)
            log.info("Removed stale project: %s", k)
            await self._git_watcher.unwatch(op.project_id)

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

    async def _poll_review_prs(self) -> None:
        """Fetch PRs where the authenticated user is a requested reviewer."""
        now = time.monotonic()
        if now - self._review_prs_fetched_at < REVIEW_PR_CACHE_TTL:
            return

        review_prs: dict[str, list[dict[str, Any]]] = {}
        for provider in config.providers:
            if provider.type != ProviderType.github:
                continue
            try:
                prs = await self._fetch_review_prs_for_provider(provider)
                review_prs.update(prs)
            except Exception:  # noqa: BLE001
                log.debug("Failed to poll review PRs for %s", provider.name)

        self._review_prs = review_prs
        self._review_prs_fetched_at = now

    @staticmethod
    async def _fetch_review_prs_for_provider(
        provider: Provider,
    ) -> dict[str, list[dict[str, Any]]]:
        """Fetch review-requested PRs for a single GitHub provider."""
        result: dict[str, list[dict[str, Any]]] = {}
        async with get_provider(provider) as api:
            if not isinstance(api, GitHubApi):
                return result
            prs_by_repo = await api.get_review_requested_prs()
        for owner_repo, prs in prs_by_repo.items():
            project_id = f"{provider.name}/{owner_repo}"
            result[project_id] = [pr.model_dump() for pr in prs]
        return result

    async def _maybe_sync_providers(self) -> None:
        if time.monotonic() - self._last_provider_sync > PROVIDER_SYNC_INTERVAL:
            log.info("Auto-syncing providers...")
            await self._project_mgr.sync()
            self._last_provider_sync = time.monotonic()

    def _push_event(
        self,
        event: str,
        data: dict[str, Any],
        *,
        writer: asyncio.StreamWriter | None = None,
    ) -> None:
        """Push an event to a specific writer or all subscribers of that event category."""
        if not writer and not self._subscribers:
            return
        payload = (
            Response(type=ResponseType.EVENT, event=event, data=data)
            .model_dump_json()
            .encode()
            + b"\n"
        )
        targets = (
            [writer]
            if writer
            else [w for w, events in self._subscribers.items() if event in events]
        )
        for w in targets:
            try:
                w.write(payload)
            except Exception:  # noqa: BLE001
                self._subscribers.pop(w, None)

    def _broadcast(self, level: str, message: str) -> None:
        """Push a notification event to all subscribers (sync-safe, buffers only)."""
        self._push_event("notification", {"level": level, "message": message})

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
        sys.stdout = log_handle
        sys.stderr = log_handle

    daemon = Daemon()
    with contextlib.suppress(KeyboardInterrupt, SystemExit):
        asyncio.run(daemon.start())
