from typing import TYPE_CHECKING, Any, Self

from pyworkon.providers.models import Project

from .consumer import GitLabConsumer

if TYPE_CHECKING:
    from .models import Repository


class GitLabApi:
    """GitLab REST interface."""

    API_URL = "https://gitlab.com"

    def __init__(self, name: str, api_url: str, username: str, password: str) -> None:
        """Init."""
        self._name = name
        self._api = GitLabConsumer(base_url=api_url, auth=(username, password))
        self._username = username

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object, **kwargs: Any) -> None: ...

    def projects(self) -> list[Project]:
        page = 1
        repos: list[Repository] = []
        while True:
            repos_page = self._api.projects(membership=True, page=page)
            if not repos_page:
                break
            repos += repos_page
            page += 1

        return [
            Project(
                project_id=f"{self._name}/{repo.path_with_namespace}",
                repository_url=repo.ssh_url_to_repo,
            )
            for repo in repos
        ]
