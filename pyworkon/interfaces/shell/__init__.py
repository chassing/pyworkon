import sys

from nubia import Nubia

from .plugin import ShellPlugin


def init_shell():
    plugin = ShellPlugin()
    shell = Nubia(name="pyworkon", plugin=plugin)
    sys.exit(shell.run())
