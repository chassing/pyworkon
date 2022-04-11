import logging
import re
from pathlib import Path
from subprocess import CalledProcessError, run
from urllib.parse import urlparse

import orm
from rich import print

from .config import Provider, config
from .db import Db
from .exceptions import ProjectNotFound
from .providers import get_provider

log = logging.getLogger(__name__)


class Project:
    def __init__(self, id, repository_url) -> None:
        self.id = id
        self.repository_url = repository_url

    def __str__(self):
        return f"Project: {self.id}"

    @property
    def name(self):
        return str(Path(self.id).name)

    @property
    def project_home(self):
        return config.workspace_dir / self.id

    async def enter(self):
        """Enter project."""

        if not self.project_home.exists():
            print(
                f"[green]cloning repository {self.repository_url} to {self.project_home}. This may take a while ...[/]"
            )
            try:
                run(["git", "clone", self.repository_url, self.project_home], check=True)
            except CalledProcessError:
                print(f"[b red]cloning {self.repository_url} failed[/]")
                return

        workon_pre_command = [config.workon_pre_command] if config.workon_pre_command else []
        commands = (
            [
                f"PYWORKON_PROJECT_ID='{self.id}'",
                f"PYWORKON_PROJECT_NAME='{self.name}'",
                f"PYWORKON_PROJECT_HOME='{self.project_home}'",
                "export PYWORKON_PROJECT_ID PYWORKON_PROJECT_NAME PYWORKON_PROJECT_HOME",
                f"cd '{self.project_home}'",
            ]
            + workon_pre_command
            + [f"exec {config.workon_command}"]
        )

        entry_command = " && ".join(commands)
        log.debug(f"Project entry command: {entry_command}")
        run(entry_command, shell=True)


class ProjectManager:
    def __init__(self):
        self.db = Db()

    async def sync(self, provider: Provider):
        async with self.db as db:
            async with get_provider(provider) as _api:
                for p in await _api.projects():
                    await db.project_update_or_create(project_id=p.project_id, repository_url=p.repository_url)

    async def remove_projects(self, provider: Provider):
        async with self.db as db:
            await db.delete_projects(provider=provider.name)

    async def list(self) -> list[Project]:
        async with self.db as db:
            return [Project(id=p.project_id, repository_url=p.repository_url) for p in await db.projects()]  # type: ignore

    async def get(self, project_id, repository_url=None) -> Project:
        if repository_url:
            return Project(id=project_id, repository_url=repository_url)

        async with self.db as db:
            try:
                p = await db.project(project_id)
                return Project(id=p.project_id, repository_url=p.repository_url)  # type: ignore
            except orm.exceptions.NoMatch:
                raise ProjectNotFound(f"{project_id} not found")

    async def enter(self, project_id__or__url):
        if re.match(r"https?://", project_id__or__url):
            # treat it as an URL to another github/bitbucket/gitlab repository :)
            repository_url = project_id__or__url
            project_id = self._url_to_project_id(project_id__or__url)
        else:
            repository_url = None
            project_id = project_id__or__url

        project = await self.get(project_id=project_id, repository_url=repository_url)
        await project.enter()

    def _url_to_project_id(self, url: str):
        """Convert given url in project_id.

        E.g.:
            https://github.com/chassing/linux-sysadmin-interview-questions.git -> github/chassing/linux-sysadmin-interview-questions
        """
        parsed_url = urlparse(url)
        if not parsed_url.hostname:
            raise Exception("URL parse error")
        provider = parsed_url.hostname.split(".")[-2]
        path = parsed_url.path.lstrip("/").removesuffix(".git")
        return f"{provider}/{path}"


project_manager = ProjectManager()
