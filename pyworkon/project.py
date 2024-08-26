import glob
import json
import logging
import os
from pathlib import Path
from subprocess import CalledProcessError, run
from urllib.parse import urlparse

from diskcache import Cache
from pydantic import BaseModel
from rich import print as rich_print

from pyworkon.config import config
from pyworkon.providers import get_provider

log = logging.getLogger(__name__)


class Project(BaseModel):
    id: str
    repository_url: str | None = None

    def __str__(self) -> str:
        return f"Project: {self.id}"

    @property
    def name(self) -> str:
        return str(Path(self.id).name)

    @property
    def project_home(self) -> Path:
        return config.workspace_dir / self.id

    @property
    def is_local(self) -> bool:
        return self.project_home.exists()

    def enter(self) -> None:
        """Enter project."""
        if not self.is_local:
            rich_print(
                "[b red]Project has no local working directory (not cloned yet?)[/]"
            )
            return

        workon_pre_command = (
            [config.workon_pre_command] if config.workon_pre_command else []
        )
        commands = [
            f"PYWORKON_PROJECT_ID='{self.id}'",
            f"PYWORKON_PROJECT_NAME='{self.name}'",
            f"PYWORKON_PROJECT_HOME='{self.project_home}'",
            "export PYWORKON_PROJECT_ID PYWORKON_PROJECT_NAME PYWORKON_PROJECT_HOME",
            f"cd '{self.project_home}'",
            *workon_pre_command,
            f"exec {config.workon_command}",
        ]

        entry_command = " && ".join(commands)
        log.debug(f"Project entry command: {entry_command}")
        run(entry_command, shell=True, check=False)

    def clone(self) -> None:
        """Clone project."""
        if self.is_local:
            rich_print(
                "[b red]Project directory exists already! Use 'workon' instead![/]"
            )
            return
        if not self.repository_url:
            rich_print("[b red]No repository URL found![/]")
            return

        rich_print(
            f"[green]Cloning repository {self.repository_url} to {self.project_home}. This may take a while ...[/]"
        )
        try:
            run(["git", "clone", self.repository_url, self.project_home], check=True)  # noqa: S607
        except CalledProcessError:
            rich_print(f"[b red]Cloning {self.repository_url} failed[/]")
            return


class ProjectManager:
    def __init__(self) -> None:
        self._cache = Cache(directory=str(config.project_cache))
        self._init_project_list()

    def _init_project_list(self) -> None:
        self._projects = {
            project_id: Project(id=project_id)
            for project_id in glob.glob(  # noqa: PTH207
                "*/*/*", root_dir=config.workspace_dir, include_hidden=False
            )
            if os.path.isdir(f"{config.workspace_dir}/{project_id}")  # noqa: PTH112
            and project_id.startswith(tuple(p.name for p in config.providers))
        }
        for p in self._cache.get("PROJECTS", []):
            project = Project(**json.loads(p))
            self._projects[project.id] = project

    def sync(self) -> None:
        projects: list[Project] = []
        for provider in config.providers:
            with get_provider(provider) as _api:
                projects += [
                    Project(id=p.project_id, repository_url=p.repository_url)
                    for p in _api.projects()
                ]
        self._cache.set("PROJECTS", [p.model_dump_json() for p in projects])

    def list(self, *, local: bool) -> list[Project]:
        return [
            project for project in self._projects.values() if project.is_local == local
        ]

    def get(self, project_id: str) -> Project:
        return self._projects[project_id]

    def enter(self, project_id: str) -> None:
        project = self.get(project_id=project_id)
        project.enter()

    def clone(self, project_id: str) -> None:
        project = self.get(project_id=project_id)
        project.clone()

    @staticmethod
    def _url_to_project_id(url: str) -> str:
        """Convert given url in project_id.

        E.g.:
            https://github.com/chassing/linux-sysadmin-interview-questions.git -> github/chassing/linux-sysadmin-interview-questions
        """
        parsed_url = urlparse(url)
        if not parsed_url.hostname:
            msg = "URL parse error"
            raise RuntimeError(msg)
        provider = parsed_url.hostname.split(".")[-2]
        path = parsed_url.path.lstrip("/").removesuffix(".git")
        return f"{provider}/{path}"


project_manager = ProjectManager()
