import logging

from uplink_httpx import HttpxClient

from ..models import Project
from .consumer import BitbucketConsumer
from .models import (
    Repository,
    Workspace,
)

log = logging.getLogger(__name__)


class BitbucketApi:
    """Bitucket REST interface."""

    API_URL = "https://api.bitbucket.org"

    def __init__(self, name, api_url, username, password):
        """Init."""
        self._name = name
        self._api = BitbucketConsumer(base_url=api_url, client=HttpxClient(), auth=(username, password))  # type: ignore
        self._username = username

    async def __aenter__(self):
        await self._api.__aenter__()
        return self

    async def __aexit__(self, *args, **kwargs):
        await self._api.__aexit__()

    async def workspaces(self) -> list[Workspace]:
        workspaces: list[Workspace] = []
        page = 1
        total_size = 0
        while not workspaces or len(workspaces) < total_size:
            ws = await self._api.workspaces(page=page, pagelen=100)
            total_size = ws.size
            workspaces += ws.values
            page += 1
        return workspaces

    async def projects(self) -> list[Project]:
        repositories: list[Repository] = []
        projects: list[Project] = []
        for ws in await self.workspaces():
            page = 1
            total_size = 0
            ws_repos: list[Repository] = []
            while not ws_repos or len(ws_repos) < total_size:
                repos = await self._api.repositories(workspace=ws.uuid, page=page, pagelen=100)
                total_size = repos.size
                ws_repos += repos.values
                page += 1
            repositories += ws_repos

        for repo in repositories:
            project_id = f"{self._name}/{repo.full_name}"
            ssh_url = None
            for link in repo.links.clone:
                if link.name.lower() == "ssh":
                    ssh_url = link.href
            if not ssh_url:
                log.error(f"{project_id} doesn't have an ssh clone url configured!")
                continue

            projects.append(Project(project_id=project_id, repository_url=ssh_url))
        return projects
