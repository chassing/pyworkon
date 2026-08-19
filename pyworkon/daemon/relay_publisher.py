"""Best-effort push of sidebar state to an optional remote relay.

Fully inert unless `config.relay_url` is set (see `Daemon.__init__`). Mirrors
the log-on-transition style of `daemon/providers/circuit_breaker.py` so a
down/misconfigured relay doesn't spam the daemon log every poll cycle.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING

import httpx2

from pyworkon.interfaces.relay.schema import (
    RelayProjectSummary,
    RelaySessionState,
    RelayStatePayload,
)

if TYPE_CHECKING:
    from pyworkon.daemon.protocol import SidebarStatePayload

log = logging.getLogger(__name__)

# httpx2 logs one INFO line per request by default; we already log our own
# WARNING/INFO on failure/recovery transitions, so silence its per-request spam.
logging.getLogger("httpx2").setLevel(logging.WARNING)

RELAY_STALE_MULTIPLIER = 3  # stale-banner threshold = sidebar_refresh_interval * this


def to_relay_payload(
    state: SidebarStatePayload, *, stale_after_seconds: int
) -> RelayStatePayload:
    """Sanitize daemon state for external transmission.

    Strips `Project.provider` (carries a `password` credential field) down to
    just `provider_type`, and drops `pane_id` (tmux-pane plumbing, meaningless
    to a remote viewer).
    """
    return RelayStatePayload(
        sessions=[
            RelaySessionState(
                session_name=s.session_name,
                project_id=s.project.id,
                project_name=s.project.name,
                provider_type=s.project.provider.type if s.project.provider else None,
                branch=s.branch,
                is_dirty=s.is_dirty,
                pr=s.pr,
                agents=list(s.agents),
            )
            for s in state.sessions
        ],
        plain_sessions=list(state.plain_sessions),
        projects=[
            RelayProjectSummary(
                id=p.id,
                name=p.name,
                provider_type=p.provider.type if p.provider else None,
            )
            for p in state.projects
        ],
        review_prs=state.review_prs,
        open_providers=list(state.open_providers),
        stale_after_seconds=stale_after_seconds,
    )


class RelayPublisher:
    """Pushes the latest sidebar state to a relay's `/ingest` endpoint."""

    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        stale_after_seconds: int,
        timeout: float = 5.0,
    ) -> None:
        self._stale_after_seconds = stale_after_seconds
        self._queue: asyncio.Queue[SidebarStatePayload] = asyncio.Queue(maxsize=1)
        self._client = httpx2.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
        )
        self._last_post_failed = False

    def submit(self, state: SidebarStatePayload) -> None:
        """Queue the latest state for publishing, replacing any pending one."""
        with contextlib.suppress(asyncio.QueueEmpty):
            self._queue.get_nowait()
        with contextlib.suppress(asyncio.QueueFull):
            self._queue.put_nowait(state)

    async def run(self) -> None:
        """Drain the queue and publish forever until cancelled."""
        while True:
            state = await self._queue.get()
            await self._post(state)

    async def _post(self, state: SidebarStatePayload) -> None:
        payload = to_relay_payload(state, stale_after_seconds=self._stale_after_seconds)
        try:
            response = await self._client.post(
                "/ingest", content=payload.model_dump_json().encode()
            )
            response.raise_for_status()
        except httpx2.HTTPError as exc:
            if not self._last_post_failed:
                log.warning("Relay publish failed: %s", exc)
                self._last_post_failed = True
            return
        if self._last_post_failed:
            log.info("Relay publish recovered")
            self._last_post_failed = False

    async def aclose(self) -> None:
        await self._client.aclose()
