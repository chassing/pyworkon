def init_cli(args: list[str]) -> None:
    """Initialize the CLI."""
    # `commands` is imported only for its side effect of registering each
    # subcommand on `cli`. A module-level `lazy from .shell import commands`
    # would never actually run, since lazy bindings only resolve on access,
    # and this name is deliberately never accessed — so this import must
    # stay here, eager, rather than move to module scope.
    from .shell import (
        cli,
        commands,  # ruff: ignore[unused-import]
        pyworkon_context,
    )

    pyworkon_context.args = args
    cli(obj=pyworkon_context, prog_name="pyworkon", args=args)
