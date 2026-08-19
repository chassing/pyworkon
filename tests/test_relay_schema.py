"""Round-trip/immutability tests for the pure relay wire DTOs."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pyworkon.interfaces.relay.schema import (
    RelayBroadcastPayload,
    RelayProjectSummary,
    RelaySessionState,
    RelayStatePayload,
)


def test_relay_state_payload_round_trips_through_json() -> None:
    payload = RelayStatePayload(
        sessions=[
            RelaySessionState(
                session_name="my-session",
                project_id="github/owner/repo",
                project_name="repo",
                provider_type="github",
            )
        ],
        plain_sessions=["plain"],
        projects=[RelayProjectSummary(id="github/owner/repo2", name="repo2")],
        review_prs={},
        open_providers=[],
        stale_after_seconds=15,
    )

    restored = RelayStatePayload.model_validate_json(payload.model_dump_json())

    assert restored == payload


def test_relay_state_payload_is_frozen() -> None:
    payload = RelayStatePayload(
        sessions=[],
        plain_sessions=[],
        projects=[],
        review_prs={},
        open_providers=[],
        stale_after_seconds=15,
    )

    with pytest.raises(ValidationError):
        payload.stale_after_seconds = 30  # type: ignore[misc]


def test_relay_broadcast_payload_adds_pushed_at() -> None:
    broadcast = RelayBroadcastPayload(
        sessions=[],
        plain_sessions=[],
        projects=[],
        review_prs={},
        open_providers=[],
        stale_after_seconds=15,
        pushed_at=123.456,
    )

    assert broadcast.pushed_at == pytest.approx(123.456)
