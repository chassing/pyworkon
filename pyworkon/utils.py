import logging
import os
import sys
from copy import deepcopy
from urllib.parse import urlparse

from .exceptions import RunError

log = logging.getLogger(__name__)


def url_to_project_id(url: str):
    """Convert given url in project_id.

    E.g.:
        https://github.com/chassing/linux-sysadmin-interview-questions.git -> github/chassing/linux-sysadmin-interview-questions
    """
    url = urlparse(url)
    org = url.hostname.split(".")[-2]
    path = url.path.lstrip("/").removesuffix(".git")
    return f"{org}/{path}"


def run(command, hide_output=False, warn_only=False, env_overrides={}, enforce_pty=False):
    """Run the given *command* locally.

    See :func:`~nudev.api.v4.SourceConfigBase.run` for a detailed explanation.
    """

    class _ResultStr(str):
        """Class extending str that allows to add custom attributes to our result."""

        pass

    log.info(f"Executing: {command}")
    import invoke

    with TempEnv(env_overrides):
        invoke_result = invoke.run(
            command,
            pty=enforce_pty or (sys.stdin.isatty() and sys.stdout.isatty()),
            hide=hide_output,
            warn=True,
            encoding="utf-8",
        )
    result = _ResultStr(invoke_result.stdout.replace("\r\n", "\n").replace("\r", "\n"))
    result.stderr = invoke_result.stderr.replace("\r\n", "\n").replace("\r", "\n")
    result.cmd = command
    result.return_code = invoke_result.exited
    result.ok = invoke_result.ok

    if not warn_only and not result.ok:
        raise RunError(
            f"""The following command finished with a non-zero exit code:

{result.cmd}

Exit code: {result.return_code}
Output: {result}
StdErr: {result.stderr}
""",
            result,
        )

    return result


def git(command, hide_output=False, warn_only=False):
    """Execute git *command* as a subprocess."""
    return run(f"git {command}", hide_output=hide_output, warn_only=warn_only)


class TempEnv:
    """Context manager for creating a temporary environment.

    Usage:
        os.environ['MYVAR'] = 'oldvalue'
        with TempEnv('MYVAR', 'myvalue'):
            print os.getenv('MYVAR')    # Should print myvalue.
        print os.getenv('MYVAR')        # Should print oldvalue.
    """

    def __init__(self, env):
        """Contructor.

        Args:
            env: dictionary with key as environment variable name and value as value
        """
        self._new_env = self._default_env()
        self._new_env.update(env)

    def __enter__(self):
        """Set the environment variable and saves the old value."""
        self._old_env = deepcopy(os.environ)
        os.environ.update(self._new_env)

    def __exit__(self, *args):
        """Set the environment variable back to the way it was before."""
        os.environ = deepcopy(self._old_env)

    def _default_env(self):
        """Environment variables which should be used per default.

        Check if LD_LIBRARY_PATH_ORIG is set and use it for LD_LIBRARY_PATH (pyinstaller overwrites it and this could break subprocesses).
        """
        env = dict()
        env["LD_LIBRARY_PATH"] = os.environ.get("LD_LIBRARY_PATH_ORIG", "")
        return env
