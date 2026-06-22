"""JSON-Lines protocol models for daemon ↔ client communication."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel


class CommandType(StrEnum):
    LIST_PROJECTS = "list_projects"
    GET_PROJECT = "get_project"
    OPEN_PROJECT = "open_project"
    CLOSE_PROJECT = "close_project"
    CLONE_PROJECT = "clone_project"
    SYNC_PROVIDERS = "sync_providers"
    GET_SIDEBAR_STATE = "get_sidebar_state"
    AGENT_STATUS = "agent_status"
    AGENT_CLEAR = "agent_clear"
    STATUS = "status"
    SHUTDOWN = "shutdown"
    SUBSCRIBE = "subscribe"
    NOTIFY = "notify"


class ResponseType(StrEnum):
    PROJECTS = "projects"
    PROJECT = "project"
    SIDEBAR_STATE = "sidebar_state"
    PROGRESS = "progress"
    OK = "ok"
    ERROR = "error"
    STATUS = "status"
    NOTIFICATION = "notification"


class Command(BaseModel):
    """Client → Daemon message."""

    cmd: CommandType
    project_id: str | None = None
    local: bool | None = None
    pane_id: str | None = None
    session: str | None = None
    window: str | None = None
    name: str | None = None
    status: str | None = None
    message: str | None = None
    level: str | None = None


class Response(BaseModel):
    """Daemon → Client message."""

    type: ResponseType
    data: dict[str, Any] | None = None
    msg: str | None = None


def ok() -> Response:
    return Response(type=ResponseType.OK)


def error(msg: str) -> Response:
    return Response(type=ResponseType.ERROR, msg=msg)


def progress(msg: str) -> Response:
    return Response(type=ResponseType.PROGRESS, msg=msg)
