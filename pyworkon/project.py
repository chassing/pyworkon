import logging
import subprocess
from pathlib import Path

from rich import print

from .config import config
from .utils import TempEnv, git

log = logging.getLogger(__name__)


class Project:
    def __init__(self, id="project") -> None:
        self.id = id
        self.name = str(Path(id).name)
        self.reository_url = "https://github.com/chassing/linux-sysadmin-interview-questions.git"
        self.project_home = config.workspace_dir / id

    @classmethod
    async def get(cls, project_id):
        return cls(project_id)

    async def enter(self):
        """Enter project."""

        if not self.project_home.exists():
            print(
                f"[green]cloning repository {self.reository_url} to {self.project_home}. This may take a while ...[/]"
            )
            git(f"clone {self.reository_url} {self.project_home}")

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
        print(f"Project entry command: {entry_command}")
        with TempEnv({}):
            project_shell = subprocess.Popen(entry_command, shell=True)
            project_shell.communicate()
