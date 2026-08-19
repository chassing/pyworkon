"""In-memory latest-state cache and WebSocket fan-out for the relay.

Lives on `app.state.cache` (one instance per `create_app()` call), not a
module-level singleton, so tests can spin up isolated app instances.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from pyworkon.interfaces.relay.schema import RelayBroadcastPayload, RelayStatePayload

if TYPE_CHECKING:
    from fastapi import WebSocket

log = logging.getLogger(__name__)


class RelayCache:
    def __init__(self) -> None:
        self._latest: RelayBroadcastPayload | None = None
        self._connections: set[WebSocket] = set()

    def set_latest(self, payload: RelayStatePayload) -> RelayBroadcastPayload:
        broadcast = RelayBroadcastPayload(**payload.model_dump(), pushed_at=time.time())
        self._latest = broadcast
        return broadcast

    def get_latest(self) -> RelayBroadcastPayload | None:
        return self._latest

    def register(self, websocket: WebSocket) -> None:
        self._connections.add(websocket)

    def unregister(self, websocket: WebSocket) -> None:
        self._connections.discard(websocket)

    async def broadcast(self, payload: RelayBroadcastPayload) -> None:
        dead: set[WebSocket] = set()
        for connection in self._connections:
            try:
                await connection.send_json(payload.model_dump(mode="json"))
            except Exception:  # ruff: ignore[blind-except]
                dead.add(connection)
        self._connections -= dead
