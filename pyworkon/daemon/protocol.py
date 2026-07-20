"""JSON-Lines protocol models for daemon ↔ client communication.

Every command and every response is its own pydantic class, discriminated by
`cmd`/`type` respectively, so required fields are enforced by pydantic
validation instead of manual guards in the daemon's command handlers.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from pyworkon.daemon.models import AgentInfo, PRInfo, ReviewPR
from pyworkon.daemon.project_mgr import Project


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
    KILL_SESSION = "kill_session"
    SWITCH_SESSION = "switch_session"
    ENTER_PROJECT = "enter_project"


class ResponseType(StrEnum):
    PROJECTS = "projects"
    PROJECT = "project"
    SIDEBAR_STATE = "sidebar_state"
    PROGRESS = "progress"
    OK = "ok"
    ERROR = "error"
    STATUS = "status"
    EVENT = "event"


class _FrozenModel(BaseModel):
    """Base for one-shot wire DTOs — immutable, catches accidental mutation."""

    model_config = ConfigDict(frozen=True)


# --- Commands: Client -> Daemon ---------------------------------------------


class ListProjectsCommand(_FrozenModel):
    cmd: Literal[CommandType.LIST_PROJECTS] = CommandType.LIST_PROJECTS
    local: bool = True


class GetProjectCommand(_FrozenModel):
    cmd: Literal[CommandType.GET_PROJECT] = CommandType.GET_PROJECT
    project_id: str = Field(min_length=1)


class OpenProjectCommand(_FrozenModel):
    cmd: Literal[CommandType.OPEN_PROJECT] = CommandType.OPEN_PROJECT
    project_id: str = Field(min_length=1)
    pane_id: str | None = None
    session: str | None = None


class CloseProjectCommand(_FrozenModel):
    cmd: Literal[CommandType.CLOSE_PROJECT] = CommandType.CLOSE_PROJECT
    project_id: str = Field(min_length=1)
    pane_id: str | None = None


class CloneProjectCommand(_FrozenModel):
    cmd: Literal[CommandType.CLONE_PROJECT] = CommandType.CLONE_PROJECT
    project_id: str = Field(min_length=1)


class SyncProvidersCommand(_FrozenModel):
    cmd: Literal[CommandType.SYNC_PROVIDERS] = CommandType.SYNC_PROVIDERS


class GetSidebarStateCommand(_FrozenModel):
    cmd: Literal[CommandType.GET_SIDEBAR_STATE] = CommandType.GET_SIDEBAR_STATE


class AgentStatusCommand(_FrozenModel):
    cmd: Literal[CommandType.AGENT_STATUS] = CommandType.AGENT_STATUS
    session: str = Field(min_length=1)
    pid: int
    name: str = Field(min_length=1)
    status: str = Field(min_length=1)


class AgentClearCommand(_FrozenModel):
    cmd: Literal[CommandType.AGENT_CLEAR] = CommandType.AGENT_CLEAR
    session: str = Field(min_length=1)
    pid: int


class StatusCommand(_FrozenModel):
    cmd: Literal[CommandType.STATUS] = CommandType.STATUS


class ShutdownCommand(_FrozenModel):
    cmd: Literal[CommandType.SHUTDOWN] = CommandType.SHUTDOWN


class SubscribeCommand(_FrozenModel):
    cmd: Literal[CommandType.SUBSCRIBE] = CommandType.SUBSCRIBE
    events: list[str]
    full: bool = True


class NotifyCommand(_FrozenModel):
    cmd: Literal[CommandType.NOTIFY] = CommandType.NOTIFY
    message: str = Field(min_length=1)
    level: str = "information"


class KillSessionCommand(_FrozenModel):
    cmd: Literal[CommandType.KILL_SESSION] = CommandType.KILL_SESSION
    session: str = Field(min_length=1)


class SwitchSessionCommand(_FrozenModel):
    cmd: Literal[CommandType.SWITCH_SESSION] = CommandType.SWITCH_SESSION
    session: str = Field(min_length=1)
    pane_id: str | None = None


class EnterProjectCommand(_FrozenModel):
    cmd: Literal[CommandType.ENTER_PROJECT] = CommandType.ENTER_PROJECT
    project_id: str = Field(min_length=1)


CommandUnion = Annotated[
    ListProjectsCommand
    | GetProjectCommand
    | OpenProjectCommand
    | CloseProjectCommand
    | CloneProjectCommand
    | SyncProvidersCommand
    | GetSidebarStateCommand
    | AgentStatusCommand
    | AgentClearCommand
    | StatusCommand
    | ShutdownCommand
    | SubscribeCommand
    | NotifyCommand
    | KillSessionCommand
    | SwitchSessionCommand
    | EnterProjectCommand,
    Field(discriminator="cmd"),
]

command_adapter: TypeAdapter[CommandUnion] = TypeAdapter(CommandUnion)


# --- Response payloads (shared between GET_SIDEBAR_STATE and the "state" event) ---


class SessionState(_FrozenModel):
    session_name: str
    project: Project
    branch: str | None = None
    is_dirty: bool = False
    pr: PRInfo | None = None
    agents: list[AgentInfo] = []
    pane_id: str | None = None


class SidebarStatePayload(_FrozenModel):
    sessions: list[SessionState]
    plain_sessions: list[str]
    projects: list[Project]
    review_prs: dict[str, list[ReviewPR]]


class NotificationData(_FrozenModel):
    level: str
    message: str


# --- Responses: Daemon -> Client --------------------------------------------


class OkResponse(_FrozenModel):
    type: Literal[ResponseType.OK] = ResponseType.OK


class ErrorResponse(_FrozenModel):
    type: Literal[ResponseType.ERROR] = ResponseType.ERROR
    msg: str


class ProgressResponse(_FrozenModel):
    type: Literal[ResponseType.PROGRESS] = ResponseType.PROGRESS
    msg: str


class ProjectsResponse(_FrozenModel):
    type: Literal[ResponseType.PROJECTS] = ResponseType.PROJECTS
    projects: list[Project]


class ProjectResponse(_FrozenModel):
    type: Literal[ResponseType.PROJECT] = ResponseType.PROJECT
    project: Project


class SidebarStateResponse(SidebarStatePayload):
    type: Literal[ResponseType.SIDEBAR_STATE] = ResponseType.SIDEBAR_STATE


class StatusResponse(_FrozenModel):
    type: Literal[ResponseType.STATUS] = ResponseType.STATUS
    open_projects: int
    total_projects: int
    pid: int


class EventResponse(_FrozenModel):
    type: Literal[ResponseType.EVENT] = ResponseType.EVENT
    event: Literal["state", "notification"]
    data: SidebarStatePayload | NotificationData


ResponseUnion = Annotated[
    OkResponse
    | ErrorResponse
    | ProgressResponse
    | ProjectsResponse
    | ProjectResponse
    | SidebarStateResponse
    | StatusResponse
    | EventResponse,
    Field(discriminator="type"),
]

response_adapter: TypeAdapter[ResponseUnion] = TypeAdapter(ResponseUnion)


def ok() -> OkResponse:
    return OkResponse()


def error(msg: str) -> ErrorResponse:
    return ErrorResponse(msg=msg)


def progress(msg: str) -> ProgressResponse:
    return ProgressResponse(msg=msg)
