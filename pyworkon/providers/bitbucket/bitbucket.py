from uplink_httpx import HttpxClient

from .consumer import BitbucketConsumer
from .models import Repository, Workspace


class BitbucketApi:
    """Bitucket REST interface."""

    def __init__(self, url, username, password):
        """Init."""
        self._api = BitbucketConsumer(base_url=url, client=HttpxClient(), auth=(username, password))
        self._username = username

    async def __aenter__(self):
        await self._api.__aenter__()
        return self

    async def __aexit__(self, *args, **kwargs):
        await self._api.__aexit__()

    async def workspaces(self) -> list[Workspace]:
        workspaces = []
        page = 1
        total_size = 0
        while not workspaces or len(workspaces) < total_size:
            ws = await self._api.workspaces(page=page, pagelen=100)
            total_size = ws.size
            workspaces += ws.values
            page += 1
        return workspaces

    async def projects(self) -> list[Repository]:
        repositories = []
        for ws in await self.workspaces():
            page = 1
            total_size = 0
            ws_repos = []
            while not ws_repos or len(ws_repos) < total_size:
                repos = await self._api.repositories(workspace=ws.uuid, page=page, pagelen=100)
                total_size = repos.size
                ws_repos += repos.values
                page += 1
            repositories += ws_repos
        return repositories
