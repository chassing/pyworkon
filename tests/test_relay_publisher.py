"""Tests for the daemon-side relay publisher."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING

import httpx2

from pyworkon.config import Provider, ProviderType
from pyworkon.daemon.models import ReviewPR
from pyworkon.daemon.project_mgr import Project
from pyworkon.daemon.protocol import SessionState, SidebarStatePayload
from pyworkon.daemon.relay_publisher import RelayPublisher, to_relay_payload

from .conftest import make_pr_info

if TYPE_CHECKING:
    import pytest
    from pytest_httpx2 import HTTPXMock


def _provider(*, password: str) -> Provider:
    return Provider(
        name="github",
        type=ProviderType.github,
        api_url="https://api.github.com",
        username="chassing",
        password=password,
    )


def _state_with_provider(provider: Provider | None) -> SidebarStatePayload:
    return SidebarStatePayload(
        sessions=[
            SessionState(
                session_name="my-session",
                project=Project(id="github/owner/repo", provider=provider),
                branch="main",
                is_dirty=True,
                pr=make_pr_info(),
            )
        ],
        plain_sessions=["plain"],
        projects=[Project(id="github/owner/repo2", provider=provider)],
        review_prs={
            "github/owner/repo": [
                ReviewPR(number=1, title="Review me", url="https://x/1", author="bob")
            ]
        },
        open_providers=["gitlab"],
    )


def test_to_relay_payload_excludes_provider_credentials() -> None:
    state = _state_with_provider(_provider(password="supersecret123"))

    relay_payload = to_relay_payload(state, stale_after_seconds=15)

    assert "supersecret123" not in relay_payload.model_dump_json()


def test_to_relay_payload_maps_provider_type_only() -> None:
    state = _state_with_provider(_provider(password="unused"))

    relay_payload = to_relay_payload(state, stale_after_seconds=15)

    assert relay_payload.sessions[0].provider_type == "github"
    assert relay_payload.projects[0].provider_type == "github"


def test_to_relay_payload_handles_no_provider() -> None:
    state = _state_with_provider(None)

    relay_payload = to_relay_payload(state, stale_after_seconds=15)

    assert relay_payload.sessions[0].provider_type is None


def test_to_relay_payload_preserves_pr_agent_review_data() -> None:
    state = _state_with_provider(_provider(password="unused"))

    relay_payload = to_relay_payload(state, stale_after_seconds=15)

    assert relay_payload.sessions[0].pr == state.sessions[0].pr
    assert relay_payload.review_prs == state.review_prs
    assert relay_payload.open_providers == ["gitlab"]
    assert relay_payload.stale_after_seconds == 15


def test_submit_replaces_stale_queued_payload() -> None:
    publisher = RelayPublisher(
        base_url="http://relay.example.com", token="t", stale_after_seconds=15
    )
    first = _state_with_provider(None)
    second = SidebarStatePayload(
        sessions=[], plain_sessions=[], projects=[], review_prs={}
    )

    publisher.submit(first)
    publisher.submit(second)

    assert publisher._queue.qsize() == 1
    assert publisher._queue.get_nowait() is second


async def test_post_success_after_failure_logs_only_on_transition(
    httpx_mock: HTTPXMock, caplog: pytest.LogCaptureFixture
) -> None:
    httpx_mock.add_exception(httpx2.ConnectError("boom"))
    httpx_mock.add_response(status_code=200)
    publisher = RelayPublisher(
        base_url="http://relay.example.com", token="t", stale_after_seconds=15
    )
    state = _state_with_provider(None)

    logger_name = "pyworkon.daemon.relay_publisher"
    with caplog.at_level(logging.WARNING, logger=logger_name):
        await publisher._post(state)
    warnings = [r for r in caplog.records if r.name == logger_name]
    assert len(warnings) == 1
    assert warnings[0].levelno == logging.WARNING

    caplog.clear()
    with caplog.at_level(logging.INFO, logger=logger_name):
        await publisher._post(state)
    infos = [r for r in caplog.records if r.name == logger_name]
    assert len(infos) == 1
    assert "recovered" in infos[0].message

    await publisher.aclose()


async def test_post_does_not_log_on_repeated_failure(
    httpx_mock: HTTPXMock, caplog: pytest.LogCaptureFixture
) -> None:
    httpx_mock.add_exception(httpx2.ConnectError("boom"))
    httpx_mock.add_exception(httpx2.ConnectError("boom"))
    publisher = RelayPublisher(
        base_url="http://relay.example.com", token="t", stale_after_seconds=15
    )
    state = _state_with_provider(None)
    logger_name = "pyworkon.daemon.relay_publisher"

    with caplog.at_level(logging.WARNING, logger=logger_name):
        await publisher._post(state)
        caplog.clear()
        await publisher._post(state)

    warnings = [r for r in caplog.records if r.name == logger_name]
    assert len(warnings) == 0

    await publisher.aclose()


async def test_run_drains_queue_and_posts(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=200)
    publisher = RelayPublisher(
        base_url="http://relay.example.com", token="t", stale_after_seconds=15
    )
    state = _state_with_provider(None)
    publisher.submit(state)

    run_task = asyncio.create_task(publisher.run())
    for _ in range(100):
        if httpx_mock.get_requests():
            break
        await asyncio.sleep(0.01)
    run_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await run_task

    request = httpx_mock.get_request()
    assert request is not None
    assert request.url.path == "/ingest"
    assert request.headers["authorization"] == "Bearer t"

    await publisher.aclose()
