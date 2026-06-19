from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, Self

from pydantic import BaseModel

if TYPE_CHECKING:
    from pyworkon.sidebar.models import PRInfo


class Project(BaseModel):
    project_id: str
    repository_url: str


class ProviderApi(Protocol):
    """Common interface for provider API clients."""

    def __enter__(self) -> Self: ...
    def __exit__(self, *args: object, **kwargs: object) -> None: ...
    def projects(self) -> list[Project]: ...
    def get_pr_info(
        self, owner_repo: str, branch: str, *, head_owner: str | None = None
    ) -> PRInfo | None: ...
