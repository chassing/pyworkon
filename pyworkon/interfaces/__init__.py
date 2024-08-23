def init_cli(args: list[str]) -> None:
    """Initialize the CLI."""
    from .shell import (
        cli,
        commands,  # noqa: F401
        pyworkon_context,
    )

    pyworkon_context.args = args
    cli(obj=pyworkon_context, prog_name="pyworkon", args=args)
