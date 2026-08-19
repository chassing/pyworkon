"""Wire schema for the daemon -> relay -> browser push path.

Deliberately independent of `pyworkon.config`/`pyworkon.daemon.protocol`/
`pyworkon.daemon.project_mgr` — the relay runs as a standalone container that
may execute as an arbitrary non-root UID, and `pyworkon.config` performs
`pwd.getpwnam()`/directory-creation at import time, which can crash such a
container. Only `pyworkon.daemon.models` is safe to import (no such
side effects). `Project.provider` (a `pyworkon.config.Provider`) also carries
a `password` credential field that must never leave the laptop, so this
schema only exposes `provider_type`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from pyworkon.daemon.models import AgentInfo, PRInfo, ReviewPR

ProviderKind = Literal["github", "gitlab"]


class _FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class RelayProjectSummary(_FrozenModel):
    id: str
    name: str
    provider_type: ProviderKind | None = None


class RelaySessionState(_FrozenModel):
    session_name: str
    project_id: str
    project_name: str
    provider_type: ProviderKind | None = None
    branch: str | None = None
    is_dirty: bool = False
    pr: PRInfo | None = None
    agents: list[AgentInfo] = []


class RelayStatePayload(_FrozenModel):
    """Exact JSON body POSTed by the daemon to `/ingest`."""

    sessions: list[RelaySessionState]
    plain_sessions: list[str]
    projects: list[RelayProjectSummary]
    review_prs: dict[str, list[ReviewPR]]
    open_providers: list[str] = []
    stale_after_seconds: int


class RelayBroadcastPayload(RelayStatePayload):
    """What the relay caches/broadcasts — adds the relay-stamped receipt time."""

    pushed_at: float
