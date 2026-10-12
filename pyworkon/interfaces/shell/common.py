lazy from pyworkon.interfaces.shell import cli


def in_shell() -> bool:
    """Check if an interactive Pyworkon shell was started."""
    return cli.in_shell
