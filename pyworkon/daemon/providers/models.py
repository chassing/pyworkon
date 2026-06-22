from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, Self

from pydantic import BaseModel

if TYPE_CHECKING:
    from pyworkon.interfaces.tui.models import PRInfo


class Project(BaseModel):
    project_id: str
    repository_url: str


class ProviderApi(Protocol):
    """Common interface for provider API clients."""

    async def __aenter__(self) -> Self: ...
    async def __aexit__(self, *args: object, **kwargs: object) -> None: ...
    async def projects(self) -> list[Project]: ...
    async def get_pr_info(
        self, owner_repo: str, branch: str, *, head_owner: str | None = None
    ) -> PRInfo | None: ...
