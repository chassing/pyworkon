import logging
from typing import Any

import click
from rich.progress import Progress, SpinnerColumn, TimeElapsedColumn

from pyworkon.config import Config, config
from pyworkon.interfaces.shell.command import PyworkonMultiCommand


class PyworkonMainCommand(PyworkonMultiCommand):
    """Parent command for the Pyworkon CLI."""

    def __init__(self, *args: Any, in_shell: bool = False, **kwargs: Any) -> None:
        """Initialize the main command."""
        self.in_shell = in_shell
        self._params = kwargs.get("params", [])
        super().__init__(*args, **kwargs)

    @property
    def params(self) -> list:
        """Return the list of parameters for this command.

        Exclude the version parameter if we are in a Pyworkon shell.
        """
        disabled_params = ["version"] if self.in_shell else []
        return [param for param in self._params if param.name not in disabled_params]

    @params.setter
    def params(self, value: Any) -> None:
        self._params = value

    def format_options(
        self, ctx: click.Context, formatter: click.HelpFormatter
    ) -> None:
        """Format the command options depending on the fact if we are in a Pyworkon shell or not."""
        if self.in_shell:
            self.format_commands(ctx, formatter)
            with formatter.section("Special Shell Commands"):
                formatter.write_dl([
                    ("help", "Show this message."),
                    ("exit", "Exit the pyworkon shell."),
                ])
        else:
            super().format_options(ctx, formatter)


class PyworkonContext:
    """Global Pyworkon context that gets passed to all commands."""

    def __init__(self, config: Config = config) -> None:
        """Initialize the context.

        Sets some commonly used attributes that can be reused by all commands.
        """
        self.config = config
        self.log = logging.getLogger(f"pyworkon.{self.__class__.__name__}")
        self.args: list[str] = []

    @staticmethod
    def progress_spinner() -> Progress:
        """Display shiny progress spinner."""
        return Progress(
            SpinnerColumn(),
            "[progress.description]{task.description}",
            TimeElapsedColumn(),
        )


pyworkon_context = PyworkonContext()


@click.group(cls=PyworkonMainCommand, invoke_without_command=True)
@click.pass_context
@click.version_option(version="0.2.0", prog_name="pyworkon")
def cli(ctx: click.Context) -> None:
    """Command line tool to interact with Pyworkon projects."""
    if ctx.invoked_subcommand is None:
        if ctx.command.in_shell:  # type: ignore[attr-defined]
            # inside a pyworkon shell the default action is showing the help page
            click.echo(ctx.get_help(), color=ctx.color)
        else:
            # outside a pyworkon shell the default action is invoking the "shell" command
            ctx.invoke(ctx.command.get_command(ctx, "shell"))  # type: ignore[attr-defined]

    # reset the cached project list
    ctx.obj.project_list = None
