"""Daemon client — sync socket communication with streaming support."""

from __future__ import annotations

import socket
import sys
from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    from collections.abc import Iterator

    from pyworkon.daemon.project_mgr import Project

from pyworkon.config import user_cache_dir
from pyworkon.daemon.protocol import (
    AgentClearCommand,
    AgentStatusCommand,
    CloneProjectCommand,
    CloseProjectCommand,
    CommandUnion,
    EnterProjectCommand,
    ErrorResponse,
    EventResponse,
    GetProjectCommand,
    GetSidebarStateCommand,
    KillSessionCommand,
    ListProjectsCommand,
    NotifyCommand,
    OkResponse,
    OpenProjectCommand,
    ProgressResponse,
    ProjectResponse,
    ProjectsResponse,
    ResponseUnion,
    ShutdownCommand,
    SidebarStatePayload,
    StatusCommand,
    StatusResponse,
    SubscribeCommand,
    SwitchSessionCommand,
    SyncProvidersCommand,
    response_adapter,
)

SOCKET_PATH = user_cache_dir / "daemon.sock"


class DaemonNotRunningError(Exception):
    """Raised when the daemon is not running."""


class DaemonClient:
    """Sync client for the pyworkon daemon."""

    def __init__(self) -> None:
        self._sock: socket.socket | None = None

    def __enter__(self) -> Self:
        self.connect()
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def connect(self) -> None:
        if not SOCKET_PATH.exists():
            raise DaemonNotRunningError
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            self._sock.connect(str(SOCKET_PATH))
        except ConnectionRefusedError:
            self._sock = None
            raise DaemonNotRunningError from None

    def close(self) -> None:
        if self._sock:
            self._sock.close()
            self._sock = None

    def _send_cmd(self, cmd: CommandUnion) -> ResponseUnion:
        """Send a command and return the terminal response (ok/error/data)."""
        for resp in self._send_stream(cmd):
            if not isinstance(resp, ProgressResponse):
                return resp
        return ErrorResponse(msg="No response from daemon")

    def _reconnect(self) -> bool:
        """Close and try to reconnect to the daemon."""
        self.close()
        try:
            self.connect()
        except DaemonNotRunningError:
            return False
        return True

    def _send_stream(self, cmd: CommandUnion) -> Iterator[ResponseUnion]:
        """Send a command and yield all responses including progress. Auto-reconnects."""
        try:
            yield from self._do_send(cmd)
        except (BrokenPipeError, ConnectionError, OSError, DaemonNotRunningError):
            if not self._reconnect():
                yield ErrorResponse(msg="Daemon not running")
                return
            try:
                yield from self._do_send(cmd)
            except (BrokenPipeError, ConnectionError, OSError, DaemonNotRunningError):
                yield ErrorResponse(msg="Daemon not running")

    def _do_send(self, cmd: CommandUnion) -> Iterator[ResponseUnion]:
        if not self._sock:
            raise DaemonNotRunningError
        self._sock.sendall(cmd.model_dump_json().encode() + b"\n")
        buf = b""
        while True:
            chunk = self._sock.recv(4096)
            if not chunk:
                return
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                resp = response_adapter.validate_json(line)
                yield resp
                if isinstance(resp, (OkResponse, ErrorResponse)):
                    return

    def list_projects(self, *, local: bool = True) -> list[Project]:
        resp = self._send_cmd(ListProjectsCommand(local=local))
        return resp.projects if isinstance(resp, ProjectsResponse) else []

    def get_project(self, project_id: str) -> Project | None:
        resp = self._send_cmd(GetProjectCommand(project_id=project_id))
        return resp.project if isinstance(resp, ProjectResponse) else None

    def open_project(
        self, project_id: str, pane_id: str | None = None, session: str | None = None
    ) -> None:
        self._send_cmd(
            OpenProjectCommand(project_id=project_id, pane_id=pane_id, session=session)
        )

    def close_project(self, project_id: str, pane_id: str | None = None) -> None:
        self._send_cmd(CloseProjectCommand(project_id=project_id, pane_id=pane_id))

    def clone_project(self, project_id: str) -> Iterator[ResponseUnion]:
        yield from self._send_stream(CloneProjectCommand(project_id=project_id))

    def sync_providers(self) -> Iterator[ResponseUnion]:
        yield from self._send_stream(SyncProvidersCommand())

    def get_sidebar_state(self) -> SidebarStatePayload:
        resp = self._send_cmd(GetSidebarStateCommand())
        if not isinstance(resp, SidebarStatePayload):
            raise DaemonNotRunningError
        return resp

    def set_agent(self, session: str, name: str, status: str) -> None:
        self._send_cmd(AgentStatusCommand(session=session, name=name, status=status))

    def clear_agent(self, session: str, name: str) -> None:
        self._send_cmd(AgentClearCommand(session=session, name=name))

    def status(self) -> StatusResponse:
        resp = self._send_cmd(StatusCommand())
        if not isinstance(resp, StatusResponse):
            raise DaemonNotRunningError
        return resp

    def kill_session(self, session_name: str) -> None:
        self._send_cmd(KillSessionCommand(session=session_name))

    def switch_session(self, session_name: str, pane_id: str | None = None) -> None:
        self._send_cmd(SwitchSessionCommand(session=session_name, pane_id=pane_id))

    def enter_project(self, project_id: str) -> None:
        self._send_cmd(EnterProjectCommand(project_id=project_id))

    def send_notification(self, message: str, level: str = "information") -> None:
        self._send_cmd(NotifyCommand(message=message, level=level))

    def shutdown(self) -> None:
        self._send_cmd(ShutdownCommand())

    def subscribe(
        self, events: list[str], *, full: bool = True
    ) -> Iterator[EventResponse]:
        """Subscribe to daemon events. Blocks indefinitely, yields EVENT responses.

        To interrupt cleanly, close the client from another thread.
        """
        if not self._sock:
            raise DaemonNotRunningError
        cmd = SubscribeCommand(events=events, full=full)
        self._sock.sendall(cmd.model_dump_json().encode() + b"\n")
        buf = b""
        while True:
            chunk = self._sock.recv(4096)
            if not chunk:
                return
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                resp = response_adapter.validate_json(line)
                if isinstance(resp, EventResponse):
                    yield resp


def require_daemon() -> DaemonClient:
    """Get a connected DaemonClient or exit with error."""
    client = DaemonClient()
    try:
        client.connect()
    except DaemonNotRunningError:
        print("Daemon not running. Start with: pyworkon daemon start", file=sys.stderr)  # noqa: T201
        sys.exit(1)
    return client
