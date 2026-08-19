"""Tests for the relay FastAPI app."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from pyworkon.interfaces.relay.app import create_app
from pyworkon.interfaces.relay.config import RelaySettings

TOKEN = "devtoken"


@pytest.fixture
def client() -> TestClient:
    app = create_app(RelaySettings(token=TOKEN))
    return TestClient(app)


def _payload() -> bytes:
    return json.dumps({
        "sessions": [],
        "plain_sessions": [],
        "projects": [],
        "review_prs": {},
        "open_providers": [],
        "stale_after_seconds": 15,
    }).encode()


def test_healthz_always_200_no_auth(client: TestClient) -> None:
    assert client.get("/healthz").status_code == 200


def test_ingest_without_token_returns_401(client: TestClient) -> None:
    assert client.post("/ingest", content=_payload()).status_code == 401


def test_ingest_with_wrong_token_returns_401(client: TestClient) -> None:
    response = client.post(
        "/ingest",
        content=_payload(),
        headers={"Authorization": "Bearer wrong"},
    )
    assert response.status_code == 401


def test_ingest_with_correct_token_returns_200_and_broadcasts(
    client: TestClient,
) -> None:
    with client.websocket_connect(f"/ws?token={TOKEN}") as ws:
        response = client.post(
            "/ingest",
            content=_payload(),
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert response.status_code == 200

        received = ws.receive_json()
        assert received["stale_after_seconds"] == 15
        assert "pushed_at" in received


def test_dashboard_requires_token(client: TestClient) -> None:
    assert client.get("/").status_code == 401

    response = client.get(f"/?token={TOKEN}")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_ws_rejects_bad_token(client: TestClient) -> None:
    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect("/ws?token=wrong"),
    ):
        pass


def test_ws_receives_cached_snapshot_immediately_on_connect(
    client: TestClient,
) -> None:
    client.post(
        "/ingest",
        content=_payload(),
        headers={"Authorization": f"Bearer {TOKEN}"},
    )

    with client.websocket_connect(f"/ws?token={TOKEN}") as ws:
        received = ws.receive_json()
        assert received["stale_after_seconds"] == 15
