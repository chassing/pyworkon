"""Tests for daemon JSON-Lines protocol models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pyworkon.daemon.models import PRInfo, ReviewPR
from pyworkon.daemon.project_mgr import Project
from pyworkon.daemon.protocol import (
    AgentClearCommand,
    AgentStatusCommand,
    CloneProjectCommand,
    CloseProjectCommand,
    CommandType,
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
    ProgressResponse,
    ProjectResponse,
    ProjectsResponse,
    ResponseType,
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
    response_adapter,
)


@pytest.mark.parametrize(
    "member",
    list(CommandType),
    ids=[m.name for m in CommandType],
)
def test_command_type_values_are_strings(member: CommandType) -> None:
    assert isinstance(member.value, str)
    assert member == member.value


@pytest.mark.parametrize(
    "member",
    list(ResponseType),
    ids=[m.name for m in ResponseType],
)
def test_response_type_values_are_strings(member: ResponseType) -> None:
    assert isinstance(member.value, str)
    assert member == member.value


# --- Command round-trips -----------------------------------------------------

_COMMAND_SAMPLES = [
    ListProjectsCommand(local=False),
    GetProjectCommand(project_id="github/owner/repo"),
    OpenProjectCommand(project_id="github/owner/repo", pane_id="%1", session="s"),
    CloseProjectCommand(project_id="github/owner/repo", pane_id="%1"),
    CloneProjectCommand(project_id="github/owner/repo"),
    SyncProvidersCommand(),
    GetSidebarStateCommand(),
    AgentStatusCommand(session="dev", name="copilot", status="working"),
    AgentClearCommand(session="dev", name="copilot"),
    StatusCommand(),
    ShutdownCommand(),
    SubscribeCommand(events=["state", "notification"], full=True),
    NotifyCommand(message="deployment complete", level="info"),
    KillSessionCommand(session="my-session"),
    SwitchSessionCommand(session="my-session", pane_id="%5"),
    EnterProjectCommand(project_id="github/owner/repo"),
]


@pytest.mark.parametrize(
    "cmd", _COMMAND_SAMPLES, ids=[type(c).__name__ for c in _COMMAND_SAMPLES]
)
def test_command_roundtrip(cmd: object) -> None:
    restored = command_adapter.validate_json(cmd.model_dump_json())  # type: ignore[attr-defined]
    assert type(restored) is type(cmd)
    assert restored == cmd


def test_command_adapter_resolves_by_cmd_field() -> None:
    cmd = command_adapter.validate_json('{"cmd": "kill_session", "session": "x"}')
    assert isinstance(cmd, KillSessionCommand)
    assert cmd.session == "x"


def test_command_adapter_unknown_cmd_raises() -> None:
    with pytest.raises(ValidationError):
        command_adapter.validate_json('{"cmd": "not_a_real_command"}')


@pytest.mark.parametrize(
    ("cls", "kwargs"),
    [
        (GetProjectCommand, {}),
        (OpenProjectCommand, {}),
        (CloseProjectCommand, {}),
        (CloneProjectCommand, {}),
        (AgentStatusCommand, {"session": "dev", "name": "bot"}),
        (AgentClearCommand, {"session": "dev"}),
        (NotifyCommand, {}),
        (KillSessionCommand, {}),
        (SwitchSessionCommand, {}),
        (EnterProjectCommand, {}),
    ],
)
def test_command_missing_required_field_raises(
    cls: type, kwargs: dict[str, str]
) -> None:
    with pytest.raises(ValidationError):
        cls(**kwargs)


@pytest.mark.parametrize(
    ("cls", "field", "kwargs"),
    [
        (GetProjectCommand, "project_id", {"project_id": ""}),
        (KillSessionCommand, "session", {"session": ""}),
        (NotifyCommand, "message", {"message": ""}),
        (AgentStatusCommand, "status", {"session": "s", "name": "n", "status": ""}),
    ],
)
def test_command_empty_string_required_field_raises(
    cls: type, field: str, kwargs: dict[str, str]
) -> None:
    with pytest.raises(ValidationError):
        cls(**kwargs)


def test_subscribe_command_requires_events() -> None:
    with pytest.raises(ValidationError):
        SubscribeCommand()  # type: ignore[call-arg]


# --- Response round-trips -----------------------------------------------------

_project = Project(id="github/owner/repo")
_pr = PRInfo(number=1, title="t", status="success")
_review_pr = ReviewPR(number=2, title="t2", url="https://x", author="alice")

_RESPONSE_SAMPLES = [
    OkResponse(),
    ErrorResponse(msg="boom"),
    ProgressResponse(msg="working..."),
    ProjectsResponse(projects=[_project]),
    ProjectResponse(project=_project),
    SidebarStateResponse(
        sessions=[
            SessionState(session_name="s", project=_project, pr=_pr),
        ],
        plain_sessions=["scratch"],
        projects=[_project],
        review_prs={"github/owner/repo": [_review_pr]},
    ),
    StatusResponse(open_projects=1, total_projects=2, pid=1234),
    EventResponse(
        event="notification", data=NotificationData(level="info", message="hi")
    ),
]


@pytest.mark.parametrize(
    "resp", _RESPONSE_SAMPLES, ids=[type(r).__name__ for r in _RESPONSE_SAMPLES]
)
def test_response_roundtrip(resp: object) -> None:
    restored = response_adapter.validate_json(resp.model_dump_json())  # type: ignore[attr-defined]
    assert type(restored) is type(resp)
    assert restored == resp


def test_response_adapter_resolves_by_type_field() -> None:
    resp = response_adapter.validate_json('{"type": "error", "msg": "nope"}')
    assert isinstance(resp, ErrorResponse)
    assert resp.msg == "nope"


def test_event_response_state_payload() -> None:
    payload = SidebarStatePayload(
        sessions=[], plain_sessions=[], projects=[], review_prs={}
    )
    resp = EventResponse(event="state", data=payload)
    restored = response_adapter.validate_json(resp.model_dump_json())
    assert isinstance(restored, EventResponse)
    assert isinstance(restored.data, SidebarStatePayload)


def test_event_response_notification_payload() -> None:
    resp = EventResponse(
        event="notification", data=NotificationData(level="warning", message="hi")
    )
    restored = response_adapter.validate_json(resp.model_dump_json())
    assert isinstance(restored, EventResponse)
    assert isinstance(restored.data, NotificationData)
    assert restored.data.level == "warning"


def test_ok_helper() -> None:
    resp = ok()
    assert isinstance(resp, OkResponse)
    assert resp.type == ResponseType.OK


def test_error_helper() -> None:
    resp = error("something went wrong")
    assert isinstance(resp, ErrorResponse)
    assert resp.type == ResponseType.ERROR
    assert resp.msg == "something went wrong"


def test_progress_helper() -> None:
    resp = progress("syncing providers…")
    assert isinstance(resp, ProgressResponse)
    assert resp.type == ResponseType.PROGRESS
    assert resp.msg == "syncing providers…"
