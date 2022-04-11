from uplink.auth import BearerToken
from uplink_httpx import HttpxClient

from ..models import Project
from .consumer import GitLabConsumer
from .models import Repository


class GitLabApi:
    """GitLab REST interface."""

    API_URL = "https://gitlab.com"

    def __init__(self, name, api_url, username, password):
        """Init."""
        self._name = name
        self._api = GitLabConsumer(base_url=api_url, client=HttpxClient(), auth=BearerToken(password))  # type: ignore
        self._username = username

    async def __aenter__(self):
        await self._api.__aenter__()
        return self

    async def __aexit__(self, *args, **kwargs):
        await self._api.__aexit__()

    async def projects(self) -> list[Project]:
        repos: list[Repository] = await self._api.projects(membership=True)
        return [
            Project(project_id=f"{self._name}/{repo.path_with_namespace}", repository_url=repo.ssh_url_to_repo)
            for repo in repos
        ]
