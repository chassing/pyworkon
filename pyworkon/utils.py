import os
from copy import deepcopy


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
