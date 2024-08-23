from collections.abc import Callable, Iterable
from typing import Any

import click

from .common import in_shell


class PyworkonMultiCommand(click.Group):
    """Click group command with some Pyworkon extras."""

    def __init__(
        self, disabled_in: list[str] | None = None, *args: Any, **kwargs: Any
    ) -> None:
        """Initialize this multi command."""
        self.disabled_in = disabled_in or []
        if "commands" in kwargs:
            kwargs["commands"] = {
                name: [cmd] for name, cmd in kwargs["commands"].items()
            }
        super().__init__(*args, **kwargs)

    @staticmethod
    def _command_enabled(cmd: "PyworkonMultiCommand") -> bool:
        """Return True when the given command should be enabled in the current CLI environment."""
        disabled_in = getattr(cmd, "disabled_in", [])
        return not (in_shell() and "shell" in disabled_in)

    def add_command(self, cmd: "PyworkonMultiCommand", name: str | None = None) -> None:
        """Add the given command as a subcommand."""
        name = name or cmd.name
        if not name:
            raise TypeError("Command has no name.")
        if name in self.commands:
            self.commands[name].append(cmd)
        else:
            self.commands[name] = [cmd]

    def get_command(self, ctx: click.Context, cmd_name: str) -> "PyworkonMultiCommand":
        """Return the command instance identified by the given *cmd_name*."""
        for cmd in self.commands.get(cmd_name, []):
            if self._command_enabled(cmd):
                return cmd
        raise click.ClickException(f"Unknown command '{cmd_name}'")

    def list_commands(self, ctx: click.Context) -> list[str]:
        """List all associated subcommands."""
        return sorted([
            cmd_name
            for cmd_name, cmds in self.commands.items()
            if any(self._command_enabled(cmd) for cmd in cmds)
        ])

    def command(self, *args: Any, **kwargs: Any) -> "PyworkonCommand":
        """Handy decorator to easily add a new subcommand to this one."""
        kwargs.setdefault("cls", PyworkonCommand)
        return super().command(*args, **kwargs)

    def group(self, *args: Any, **kwargs: Any) -> "PyworkonMultiCommand":
        """Handy decorator to easily add a new sub-multicommand to this one."""
        kwargs.setdefault("cls", PyworkonMultiCommand)
        return super().group(*args, **kwargs)


class PyworkonCommand(click.Command):
    """Click command with some Pyworkon extras."""

    def __init__(
        self,
        completion_callback: Callable | None = None,
        disabled_in: Iterable[str] = [],
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Initialize this command and register the given *completion_callback* with it."""
        self.completion_callback = completion_callback
        self.disabled_in = disabled_in
        super().__init__(*args, **kwargs)

    def _find_param_from_args(
        self, ctx: click.Context, command_args: list[str]
    ) -> str | None:
        """Return the name of the currently important command line parameter for this command based on the given *command_args* string."""
        _, _, param_order = self.make_parser(ctx).parse_args(args=list(command_args))
        param_positions = []
        for param in param_order:
            param_positions.extend([
                param
                for x in range(param.nargs if param.nargs >= 0 else len(command_args))
            ])
            if isinstance(param, click.Option) and not param.is_flag:
                param_positions.append(param)

        if param_positions and len(command_args) <= len(param_positions):
            return param_positions[max(0, len(command_args) - 1)].name
        return None

    def get_completions(
        self, ctx: click.Context, command_args: list[str]
    ) -> tuple[list[str], bool]:
        """Return a list of completion values based on the given *command_args* string.

        If a *completion_callback* was specified during command creation, it is also called to retrieve completion values.
        """
        param_name = self._find_param_from_args(ctx, command_args)
        for param in self.params:
            if param.name == param_name:
                completions = (
                    self.completion_callback(ctx, self, param)
                    if self.completion_callback
                    else []
                )
                if not completions and param.type.name == "choice":
                    completions = param.type.choices
                return completions, isinstance(
                    param, click.Option
                ) and not param.is_flag
        return [], False
