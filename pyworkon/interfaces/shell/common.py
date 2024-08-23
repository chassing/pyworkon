def in_shell() -> bool:
    """Check if an interactive Pyworkon shell was started."""
    from pyworkon.interfaces.shell import cli

    return cli.in_shell
