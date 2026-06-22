"""Tests for daemon JSON-Lines protocol models."""

from __future__ import annotations

import pytest

from pyworkon.daemon.protocol import (
    Command,
    CommandType,
    Response,
    ResponseType,
    error,
    ok,
    progress,
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


def test_command_minimal() -> None:
    cmd = Command(cmd=CommandType.STATUS)
    assert cmd.cmd == CommandType.STATUS
    assert cmd.project_id is None
    assert cmd.events is None
    assert cmd.full is None


def test_command_serialization_roundtrip() -> None:
    cmd = Command(
        cmd=CommandType.OPEN_PROJECT,
        project_id="github/owner/repo",
        session="my-session",
    )
    json_str = cmd.model_dump_json()
    restored = Command.model_validate_json(json_str)
    assert restored == cmd
    assert restored.cmd == CommandType.OPEN_PROJECT
    assert restored.project_id == "github/owner/repo"
    assert restored.session == "my-session"


def test_command_subscribe_with_events_and_full() -> None:
    cmd = Command(
        cmd=CommandType.SUBSCRIBE,
        events=["state", "notification"],
        full=True,
    )
    assert cmd.cmd == CommandType.SUBSCRIBE
    assert cmd.events == ["state", "notification"]
    assert cmd.full is True

    restored = Command.model_validate_json(cmd.model_dump_json())
    assert restored.events == ["state", "notification"]
    assert restored.full is True


def test_command_agent_status() -> None:
    cmd = Command(
        cmd=CommandType.AGENT_STATUS,
        session="dev",
        name="copilot",
        status="working",
    )
    assert cmd.name == "copilot"
    assert cmd.status == "working"
    assert cmd.session == "dev"


def test_command_notify() -> None:
    cmd = Command(
        cmd=CommandType.NOTIFY,
        message="deployment complete",
        level="info",
    )
    assert cmd.message == "deployment complete"
    assert cmd.level == "info"


def test_response_minimal() -> None:
    resp = Response(type=ResponseType.OK)
    assert resp.type == ResponseType.OK
    assert resp.event is None
    assert resp.data is None
    assert resp.msg is None


def test_response_with_event() -> None:
    resp = Response(
        type=ResponseType.EVENT,
        event="state",
        data={"sessions": [], "projects": []},
    )
    assert resp.type == ResponseType.EVENT
    assert resp.event == "state"
    assert resp.data == {"sessions": [], "projects": []}


def test_response_serialization_roundtrip() -> None:
    resp = Response(
        type=ResponseType.SIDEBAR_STATE,
        data={"sessions": [{"name": "test"}]},
    )
    json_str = resp.model_dump_json()
    restored = Response.model_validate_json(json_str)
    assert restored == resp


def test_ok_helper() -> None:
    resp = ok()
    assert resp.type == ResponseType.OK
    assert resp.msg is None
    assert resp.data is None


def test_error_helper() -> None:
    resp = error("something went wrong")
    assert resp.type == ResponseType.ERROR
    assert resp.msg == "something went wrong"


def test_progress_helper() -> None:
    resp = progress("syncing providers…")
    assert resp.type == ResponseType.PROGRESS
    assert resp.msg == "syncing providers…"
