from uplink_httpx import HttpxClient

from .consumer import GitHubConsumer
from .models import Repository


class GitHubApi:
    """GitHub REST interface."""

    URL = "https://api.github.com"

    def __init__(self, url, username, password):
        """Init."""
        self._api = GitHubConsumer(base_url=url, client=HttpxClient(), auth=(username, password))  # type: ignore
        self._username = username

    async def __aenter__(self):
        await self._api.__aenter__()
        return self

    async def __aexit__(self, *args, **kwargs):
        await self._api.__aexit__()

    async def projects(self) -> list[Repository]:
        repos = []
        per_page = 100
        for page in range(1, 1000):
            repos += await self._api.user_repos(page=page, per_page=per_page)
            if len(repos) < page * per_page:
                break
        return repos
