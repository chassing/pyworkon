"""pyworkon daemon — fully async Unix socket server with event-based push."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import subprocess
import sys
import time
from collections.abc import AsyncGenerator
from typing import ClassVar, Literal

from pydantic import ValidationError

from pyworkon.config import Provider, ProviderType, config, user_cache_dir
from pyworkon.daemon.git_watcher import GitWatcher
from pyworkon.daemon.models import AgentInfo, OpenProject, ReviewPR
from pyworkon.daemon.project_mgr import ProjectManager
from pyworkon.daemon.protocol import (
    AgentClearCommand,
    AgentStatusCommand,
    CloneProjectCommand,
    CloseProjectCommand,
    CommandType,
    CommandUnion,
    EnterProjectCommand,
    ErrorResponse,
    EventResponse,
    GetProjectCommand,
    GetSidebarStateCommand,
    KillSessionCommand,
    ListProjectsCommand,
    NotificationData,
    NotifyCommand,
    OkResponse,
    OpenProjectCommand,
    ProjectResponse,
    ProjectsResponse,
    ResponseUnion,
    SessionState,
    ShutdownCommand,
    SidebarStatePayload,
    SidebarStateResponse,
    StatusCommand,
    StatusResponse,
    SubscribeCommand,
    SwitchSessionCommand,
    SyncProvidersCommand,
    command_adapter,
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

AsyncResponseIterator = AsyncGenerator[ResponseUnion, None]

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
        self._review_prs: dict[str, list[ReviewPR]] = {}
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
                cmd = command_adapter.validate_json(line)
            except ValidationError:
                await self._send(writer, error("Invalid command"))
                continue

            log.debug("Command: %s", cmd.cmd)
            gen = self._dispatch(cmd)
            try:
                async for resp in gen:
                    await self._send(writer, resp)
                    if isinstance(resp, (OkResponse, ErrorResponse)):
                        break
            finally:
                await gen.aclose()

            if isinstance(cmd, ShutdownCommand):
                self._running = False
                raise SystemExit
            if isinstance(cmd, SubscribeCommand):
                events = set(cmd.events)
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

    async def _dispatch(self, cmd: CommandUnion) -> AsyncResponseIterator:
        if handler_name := self._HANDLERS.get(cmd.cmd):
            handler = getattr(self, handler_name)
            async for resp in handler(cmd):
                yield resp
            return
        yield error(f"Unknown command: {cmd.cmd}")

    async def _cmd_shutdown(self, cmd: ShutdownCommand) -> AsyncResponseIterator:
        yield ok()

    async def _cmd_subscribe(self, cmd: SubscribeCommand) -> AsyncResponseIterator:
        yield ok()

    async def _cmd_notify(self, cmd: NotifyCommand) -> AsyncResponseIterator:
        self._broadcast(cmd.level, cmd.message)
        yield ok()

    async def _cmd_list_projects(
        self, cmd: ListProjectsCommand
    ) -> AsyncResponseIterator:
        yield ProjectsResponse(projects=self._project_mgr.list(local=cmd.local))

    async def _cmd_get_project(self, cmd: GetProjectCommand) -> AsyncResponseIterator:
        try:
            project = self._project_mgr.get(cmd.project_id)
            yield ProjectResponse(project=project)
        except KeyError:
            yield error(f"Project not found: {cmd.project_id}")

    async def _cmd_open_project(self, cmd: OpenProjectCommand) -> AsyncResponseIterator:
        # Remove existing entry for this project (e.g. tmux-discovered).
        # If one already existed, the project is open in more than one pane
        # (e.g. the default tmuxp template's main + AI windows both register
        # themselves) — the pane is then ambiguous, so don't track one.
        stale = [
            k for k, v in self._open_projects.items() if v.project_id == cmd.project_id
        ]
        pane_id = None if stale else cmd.pane_id
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
            pane_id=pane_id,
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

    async def _cmd_close_project(
        self, cmd: CloseProjectCommand
    ) -> AsyncResponseIterator:
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

    async def _cmd_kill_session(self, cmd: KillSessionCommand) -> AsyncResponseIterator:
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

    async def _cmd_switch_session(
        self, cmd: SwitchSessionCommand
    ) -> AsyncResponseIterator:
        if cmd.pane_id:
            await tmux_manager.select_pane(cmd.session, cmd.pane_id)
        else:
            await tmux_manager.attach_session(cmd.session)
        yield ok()

    async def _cmd_enter_project(
        self, cmd: EnterProjectCommand
    ) -> AsyncResponseIterator:
        try:
            project = self._project_mgr.get(cmd.project_id)
        except KeyError:
            yield error(f"Project not found: {cmd.project_id}")
            return

        await tmux_manager.enter(project)
        yield ok()

    async def _cmd_clone_project(
        self, cmd: CloneProjectCommand
    ) -> AsyncResponseIterator:
        try:
            project = self._project_mgr.get(cmd.project_id)
        except KeyError:
            yield error(f"Project not found: {cmd.project_id}")
            return
        yield progress(f"Cloning {cmd.project_id}...")
        await project.clone()
        yield ok()

    async def _cmd_sync_providers(
        self, cmd: SyncProvidersCommand
    ) -> AsyncResponseIterator:
        for provider in config.providers:
            yield progress(f"Fetching projects from {provider.name}...")
        await self._project_mgr.sync(force=True)
        self._last_provider_sync = time.monotonic()
        yield ok()

    def _build_sidebar_state(self) -> SidebarStatePayload:
        sessions = []
        for op in self._open_projects.values():
            try:
                project = self._project_mgr.get(op.project_id)
            except KeyError:
                continue
            sessions.append(
                SessionState(
                    session_name=op.session or project.name,
                    project=project,
                    branch=op.branch,
                    is_dirty=op.is_dirty,
                    pr=op.pr_data,
                    agents=op.agents,
                    pane_id=op.pane_id,
                )
            )
        sessions.sort(key=lambda s: s.session_name)
        return SidebarStatePayload(
            sessions=sessions,
            plain_sessions=sorted(self._plain_sessions),
            projects=[
                p
                for p in self._project_mgr.list(local=True)
                if not any(op.project_id == p.id for op in self._open_projects.values())
            ],
            review_prs=self._review_prs,
        )

    async def _cmd_get_sidebar_state(
        self, cmd: GetSidebarStateCommand
    ) -> AsyncResponseIterator:
        payload = self._build_sidebar_state()
        yield SidebarStateResponse(
            sessions=payload.sessions,
            plain_sessions=payload.plain_sessions,
            projects=payload.projects,
            review_prs=payload.review_prs,
        )

    async def _cmd_agent_status(self, cmd: AgentStatusCommand) -> AsyncResponseIterator:
        new_status = cmd.status
        for op in self._open_projects.values():
            if op.session == cmd.session:
                existing = next((a for a in op.agents if a.pid == cmd.pid), None)
                if existing:
                    if existing.status == new_status and existing.name == cmd.name:
                        yield ok()
                        return
                    existing.status = new_status
                    existing.name = cmd.name
                else:
                    op.agents.append(
                        AgentInfo(pid=cmd.pid, name=cmd.name, status=new_status)
                    )
                log.info(
                    "Agent %s (pid %d) in %s: %s",
                    cmd.name,
                    cmd.pid,
                    cmd.session,
                    new_status,
                )
                self._push_event("state", self._build_sidebar_state())
                yield ok()
                return
        yield error(f"No open project for session: {cmd.session}")

    async def _cmd_agent_clear(self, cmd: AgentClearCommand) -> AsyncResponseIterator:
        for op in self._open_projects.values():
            if op.session == cmd.session:
                op.agents = [a for a in op.agents if a.pid != cmd.pid]
                self._push_event("state", self._build_sidebar_state())
                yield ok()
                return
        yield ok()

    async def _cmd_status(self, cmd: StatusCommand) -> AsyncResponseIterator:
        yield StatusResponse(
            open_projects=len(self._open_projects),
            total_projects=len(self._project_mgr.list(local=True)),
            pid=os.getpid(),
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
                and (
                    (v.session and v.session not in active_sessions)
                    or (not v.session and v.project_id not in tmux_project_ids)
                )
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
        op.pr_data = pr
        op.pr_fetched_at = now
        if pr:
            log.info("PR data: %s #%s (%s)", op.project_id, pr.number, pr.state)

    async def _poll_review_prs(self) -> None:
        """Fetch PRs where the authenticated user is a requested reviewer."""
        now = time.monotonic()
        if now - self._review_prs_fetched_at < REVIEW_PR_CACHE_TTL:
            return

        review_prs: dict[str, list[ReviewPR]] = {}
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
        await self._map_review_prs_to_forks()

    async def _map_review_prs_to_forks(self) -> None:
        """Duplicate review PR entries for fork projects under their fork project ID."""
        if not self._review_prs:
            return
        for project in self._project_mgr.list(local=True):
            upstream = await project.get_upstream_owner_repo()
            if not upstream:
                continue
            provider_name = project.id.split("/", 1)[0]
            upstream_id = f"{provider_name}/{upstream}"
            if prs := self._review_prs.get(upstream_id):
                self._review_prs[project.id] = prs

    @staticmethod
    async def _fetch_review_prs_for_provider(
        provider: Provider,
    ) -> dict[str, list[ReviewPR]]:
        """Fetch review-requested PRs for a single GitHub provider."""
        result: dict[str, list[ReviewPR]] = {}
        async with get_provider(provider) as api:
            if not isinstance(api, GitHubApi):
                return result
            prs_by_repo = await api.get_review_requested_prs()
        for owner_repo, prs in prs_by_repo.items():
            project_id = f"{provider.name}/{owner_repo}"
            result[project_id] = prs
        return result

    async def _maybe_sync_providers(self) -> None:
        if time.monotonic() - self._last_provider_sync > PROVIDER_SYNC_INTERVAL:
            log.info("Auto-syncing providers...")
            await self._project_mgr.sync()
            self._last_provider_sync = time.monotonic()

    def _push_event(
        self,
        event: Literal["state", "notification"],
        data: SidebarStatePayload | NotificationData,
        *,
        writer: asyncio.StreamWriter | None = None,
    ) -> None:
        """Push an event to a specific writer or all subscribers of that event category."""
        if not writer and not self._subscribers:
            return
        payload = (
            EventResponse(event=event, data=data).model_dump_json().encode() + b"\n"
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
        self._push_event("notification", NotificationData(level=level, message=message))

    @staticmethod
    async def _send(writer: asyncio.StreamWriter, response: ResponseUnion) -> None:
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
