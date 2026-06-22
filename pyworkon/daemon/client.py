"""Daemon client — sync socket communication with streaming support."""

from __future__ import annotations

import json
import socket
import sys
from typing import TYPE_CHECKING, Any, Self

if TYPE_CHECKING:
    from collections.abc import Iterator

from pyworkon.config import user_cache_dir
from pyworkon.daemon.protocol import Command, CommandType, Response, ResponseType

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

    def _send_cmd(self, cmd: Command) -> Response:
        """Send a command and return the terminal response (ok/error/data)."""
        for resp in self._send_stream(cmd):
            if resp.type != ResponseType.PROGRESS:
                return resp
        return Response(type=ResponseType.ERROR, msg="No response from daemon")

    def _reconnect(self) -> bool:
        """Close and try to reconnect to the daemon."""
        self.close()
        try:
            self.connect()
        except DaemonNotRunningError:
            return False
        return True

    def _send_stream(self, cmd: Command) -> Iterator[Response]:
        """Send a command and yield all responses including progress. Auto-reconnects."""
        try:
            yield from self._do_send(cmd)
        except (BrokenPipeError, ConnectionError, OSError, DaemonNotRunningError):
            if not self._reconnect():
                yield Response(type=ResponseType.ERROR, msg="Daemon not running")
                return
            try:
                yield from self._do_send(cmd)
            except (BrokenPipeError, ConnectionError, OSError, DaemonNotRunningError):
                yield Response(type=ResponseType.ERROR, msg="Daemon not running")

    def _do_send(self, cmd: Command) -> Iterator[Response]:
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
                resp = Response(**json.loads(line))
                yield resp
                if resp.type in {ResponseType.OK, ResponseType.ERROR}:
                    return

    def list_projects(self, *, local: bool = True) -> list[dict[str, Any]]:
        resp = self._send_cmd(Command(cmd=CommandType.LIST_PROJECTS, local=local))
        return resp.data.get("projects", []) if resp.data else []

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        resp = self._send_cmd(
            Command(cmd=CommandType.GET_PROJECT, project_id=project_id)
        )
        if resp.type == ResponseType.ERROR:
            return None
        return resp.data.get("project") if resp.data else None

    def open_project(
        self, project_id: str, pane_id: str | None = None, session: str | None = None
    ) -> None:
        self._send_cmd(
            Command(
                cmd=CommandType.OPEN_PROJECT,
                project_id=project_id,
                pane_id=pane_id,
                session=session,
            )
        )

    def close_project(self, project_id: str, pane_id: str | None = None) -> None:
        self._send_cmd(
            Command(
                cmd=CommandType.CLOSE_PROJECT, project_id=project_id, pane_id=pane_id
            )
        )

    def clone_project(self, project_id: str) -> Iterator[Response]:
        yield from self._send_stream(
            Command(cmd=CommandType.CLONE_PROJECT, project_id=project_id)
        )

    def sync_providers(self) -> Iterator[Response]:
        yield from self._send_stream(Command(cmd=CommandType.SYNC_PROVIDERS))

    def get_sidebar_state(self) -> dict[str, Any]:
        resp = self._send_cmd(Command(cmd=CommandType.GET_SIDEBAR_STATE))
        return resp.data or {}

    def set_agent(
        self, session: str, name: str, status: str, window: str | None = None
    ) -> None:
        self._send_cmd(
            Command(
                cmd=CommandType.AGENT_STATUS,
                session=session,
                name=name,
                status=status,
                window=window,
            )
        )

    def clear_agent(self, session: str, name: str | None = None) -> None:
        self._send_cmd(Command(cmd=CommandType.AGENT_CLEAR, session=session, name=name))

    def status(self) -> dict[str, Any]:
        resp = self._send_cmd(Command(cmd=CommandType.STATUS))
        return resp.data or {}

    def shutdown(self) -> None:
        self._send_cmd(Command(cmd=CommandType.SHUTDOWN))


def require_daemon() -> DaemonClient:
    """Get a connected DaemonClient or exit with error."""
    client = DaemonClient()
    try:
        client.connect()
    except DaemonNotRunningError:
        print("Daemon not running. Start with: pyworkon daemon start", file=sys.stderr)  # noqa: T201
        sys.exit(1)
    return client
