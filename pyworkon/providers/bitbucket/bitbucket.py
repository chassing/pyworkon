import logging
from typing import Any, Self

from pyworkon.providers.models import Project

from .consumer import BitbucketConsumer
from .models import (
    Repository,
    Workspace,
)

log = logging.getLogger(__name__)


class BitbucketApi:
    """Bitucket REST interface."""

    API_URL = "https://api.bitbucket.org"

    def __init__(self, name: str, api_url: str, username: str, password: str) -> None:
        """Init."""
        self._name = name
        self._api = BitbucketConsumer(base_url=api_url, auth=(username, password))
        self._username = username

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object, **kwargs: Any) -> None: ...

    def workspaces(self) -> list[Workspace]:
        workspaces: list[Workspace] = []
        page = 1
        total_size = 0
        while not workspaces or len(workspaces) < total_size:
            ws = self._api.workspaces(page=page, pagelen=100)
            total_size = ws.size
            workspaces += ws.values
            page += 1
        return workspaces

    def projects(self) -> list[Project]:
        repositories: list[Repository] = []
        projects: list[Project] = []
        for ws in self.workspaces():
            page = 1
            total_size = 0
            ws_repos: list[Repository] = []
            while not ws_repos or len(ws_repos) < total_size:
                repos = self._api.repositories(
                    workspace=ws.uuid, page=page, pagelen=100
                )
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
