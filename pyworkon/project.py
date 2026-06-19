import contextlib
import glob
import json
import logging
import os
import subprocess
from pathlib import Path
from subprocess import CalledProcessError, run
from urllib.parse import urlparse

from diskcache import Cache
from pydantic import BaseModel
from rich import print as rich_print

from pyworkon.config import Provider, config
from pyworkon.providers import get_provider
from pyworkon.sidebar.models import PRInfo

log = logging.getLogger(__name__)


class Project(BaseModel):
    id: str
    repository_url: str | None = None
    provider: Provider | None = None

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

    @property
    def owner_repo(self) -> str:
        """Strip provider name prefix from id: 'github/owner/repo' -> 'owner/repo'."""
        parts = self.id.split("/", 1)
        return parts[1] if len(parts) > 1 else self.id

    @property
    def env_vars(self) -> dict[str, str]:
        """Environment variables for project context."""
        return {
            "PYWORKON_PROJECT_ID": self.id,
            "PYWORKON_PROJECT_NAME": self.name,
            "PYWORKON_PROJECT_HOME": str(self.project_home),
        }

    def get_current_branch(self) -> str | None:
        """Get the current git branch for this project."""
        if not self.is_local:
            return None
        with contextlib.suppress(subprocess.CalledProcessError, FileNotFoundError):
            result = subprocess.run(
                ["git", "-C", str(self.project_home), "branch", "--show-current"],  # noqa: S607
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip() or None
        return None

    def get_upstream_owner_repo(self) -> str | None:
        """Get the upstream remote's owner/repo (for forks)."""
        if not self.is_local:
            return None
        with contextlib.suppress(subprocess.CalledProcessError, FileNotFoundError):
            result = subprocess.run(
                ["git", "-C", str(self.project_home), "remote", "get-url", "upstream"],  # noqa: S607
                capture_output=True,
                text=True,
                check=True,
            )
            url = result.stdout.strip()
            if url:
                return _url_to_owner_repo(url)
        return None

    def get_pr_info(self, branch: str) -> PRInfo | None:
        """Get PR/MR info for the given branch using the project's provider API."""
        if not self.provider:
            return None
        with contextlib.suppress(Exception), get_provider(self.provider) as api:
            owner, _, _ = self.owner_repo.partition("/")
            target = self.get_upstream_owner_repo() or self.owner_repo
            return api.get_pr_info(target, branch, head_owner=owner)
        return None

    def enter(self, command: str | None = None, title: str | None = None) -> None:
        """Enter project."""
        if not self.is_local:
            rich_print(
                "[b red]Project has no local working directory (not cloned yet?)[/]"
            )
            return

        workon_pre_command = (
            [config.workon_pre_command] if config.workon_pre_command else []
        )
        if title:
            workon_pre_command.append(f"echo '\\033]0;{title}\\007'")
        workon_command = command or config.workon_command
        env_exports = [f"{k}='{v}'" for k, v in self.env_vars.items()]
        commands = [
            *env_exports,
            f"export {' '.join(self.env_vars)}",
            f"cd '{self.project_home}'",
            *workon_pre_command,
            f"exec {workon_command}",
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

    def _find_provider(self, project_id: str) -> Provider | None:
        """Find the matching provider for a project ID by name prefix."""
        for provider in config.providers:
            if project_id.startswith(f"{provider.name}/"):
                return provider
        return None

    def _init_project_list(self) -> None:
        self._projects = {}
        for project_id in glob.glob(  # noqa: PTH207
            "*/*/*", root_dir=config.workspace_dir, include_hidden=False
        ):
            if not os.path.isdir(f"{config.workspace_dir}/{project_id}"):  # noqa: PTH112
                continue
            if provider := self._find_provider(project_id):
                self._projects[project_id] = Project(id=project_id, provider=provider)
        for p in self._cache.get("PROJECTS", []):
            cached = Project(**json.loads(p))
            if existing := self._projects.get(cached.id):
                existing.repository_url = (
                    existing.repository_url or cached.repository_url
                )
                existing.provider = existing.provider or cached.provider
            else:
                if not cached.provider:
                    cached.provider = self._find_provider(cached.id)
                self._projects[cached.id] = cached

    def sync(self) -> None:
        projects: list[Project] = []
        for provider in config.providers:
            rich_print(f"[blue]Fetching projects from provider {provider.name}...[/]")
            with get_provider(provider) as api:
                provider_projects = [
                    Project(
                        id=p.project_id,
                        repository_url=p.repository_url,
                        provider=provider,
                    )
                    for p in api.projects()
                ]
                rich_print(
                    f"[green]Fetched {len(provider_projects)} projects from {provider.name}[/]"
                )
                projects.extend(provider_projects)
        self._cache.set("PROJECTS", [p.model_dump_json() for p in projects])
        self._init_project_list()

    def list(self, *, local: bool) -> list[Project]:
        return sorted(
            [
                project
                for project in self._projects.values()
                if project.is_local == local
            ],
            key=lambda p: p.id,
        )

    def get(self, project_id: str) -> Project:
        return self._projects[project_id]

    def enter(
        self, project_id: str, command: str | None = None, title: str | None = None
    ) -> None:
        project = self.get(project_id=project_id)
        project.enter(command=command, title=title)

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


def _url_to_owner_repo(url: str) -> str | None:
    """Extract owner/repo from a git remote URL.

    Supports both SSH and HTTPS:
        git@github.com:app-sre/qontract-reconcile.git -> app-sre/qontract-reconcile
        https://github.com/app-sre/qontract-reconcile.git -> app-sre/qontract-reconcile
    """
    url = url.strip()
    if url.startswith("git@"):
        _, _, path = url.partition(":")
    else:
        parsed = urlparse(url)
        path = parsed.path.lstrip("/")
    return path.removesuffix(".git") or None


project_manager = ProjectManager()
