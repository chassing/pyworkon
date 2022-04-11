from uplink_httpx import HttpxClient

from ..models import Project
from .consumer import GitHubConsumer
from .models import Repository


class GitHubApi:
    """GitHub REST interface."""

    API_URL = "https://api.github.com"

    def __init__(self, name, api_url, username, password):
        """Init."""
        self._name = name
        self._api = GitHubConsumer(base_url=api_url, client=HttpxClient(), auth=(username, password))  # type: ignore
        self._username = username

    async def __aenter__(self):
        await self._api.__aenter__()
        return self

    async def __aexit__(self, *args, **kwargs):
        await self._api.__aexit__()

    async def projects(self) -> list[Project]:
        repos: list[Repository] = []
        projects: list[Project] = []
        per_page = 100
        for page in range(1, 1000):
            repos += await self._api.user_repos(page=page, per_page=per_page)
            if len(repos) < page * per_page:
                break

        for repo in repos:
            projects.append(Project(project_id=f"{self._name}/{repo.full_name}", repository_url=repo.ssh_url))
        return projects
