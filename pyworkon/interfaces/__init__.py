def init_cli(args: list[str]) -> None:
    """Initialize the CLI."""
    from .shell import (
        cli,
        commands,  # ruff: ignore[unused-import]
        pyworkon_context,
    )

    pyworkon_context.args = args
    cli(obj=pyworkon_context, prog_name="pyworkon", args=args)
