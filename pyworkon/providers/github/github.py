from typing import TYPE_CHECKING, Any, Self

from pyworkon.providers.models import Project

from .consumer import GitHubConsumer

if TYPE_CHECKING:
    from .models import Repository


class GitHubApi:
    """GitHub REST interface."""

    API_URL = "https://api.github.com"

    def __init__(self, name: str, api_url: str, username: str, password: str) -> None:
        """Init."""
        self._name = name
        self._api = GitHubConsumer(base_url=api_url, auth=(username, password))
        self._username = username

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object, **kwargs: Any) -> None: ...

    def projects(self) -> list[Project]:
        repos: list[Repository] = []
        per_page = 100
        for page in range(1, 1000):
            repos += self._api.user_repos(page=page, per_page=per_page)
            if len(repos) < page * per_page:
                break

        return [
            Project(
                project_id=f"{self._name}/{repo.full_name}",
                repository_url=repo.ssh_url,
            )
            for repo in repos
        ]
