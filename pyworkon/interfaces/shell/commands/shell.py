import shlex
from collections.abc import Iterable

import click
from fuzzyfinder import fuzzyfinder
from natsort import natsorted, ns

from pyworkon.config import config
from pyworkon.interfaces.shell import cli, pyworkon_context
from pyworkon.interfaces.shell.command import PyworkonCommand


# ruff: noqa: PLC0415, C901
@cli.command(disabled_in=["shell"])
@click.pass_context
def shell(ctx: click.Context) -> None:
    """Start an interactive pyworkon shell."""
    from prompt_toolkit import prompt
    from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
    from prompt_toolkit.completion import CompleteEvent, Completer, Completion
    from prompt_toolkit.document import Document
    from prompt_toolkit.history import FileHistory

    cli.in_shell = True
    history = FileHistory(config.history_file)

    def _split_args(text: str) -> list[str]:
        try:
            return shlex.split(text)
        except ValueError:
            return []

    class PyworkonCompleter(Completer):
        def get_completions(  # noqa: PLR0912
            self, document: Document, complete_event: CompleteEvent
        ) -> Iterable[Completion]:
            args = _split_args(document.current_line_before_cursor)
            current_multi_command = cli
            current_command = cli
            command_args = args
            completion_candidates: set[str] = set()
            shell_context = cli.make_context(
                "",
                args,
                parent=ctx,
                resilient_parsing=True,
                ignore_unknown_options=True,
            )

            word = document.get_word_under_cursor(WORD=True)
            start_position = document.find_boundaries_of_current_word(WORD=True)[0]
            if word.startswith(("-", "--")) and "=" in word:
                option, value = word.split("=", 1)
                start_position = start_position + len(option) + 1
                word = value

            # we need to walk down the chain of current arguments so far to get to the "latest"
            # subcommand. When we have it, we populate the completion_candidates set based on it's options
            # and additional subcommands if needed.
            for arg_index, arg in enumerate(args):
                if not arg.startswith((
                    "-",
                    "--",
                )) and arg in current_multi_command.list_commands(shell_context):
                    current_command = current_multi_command.get_command(  # type: ignore[assignment]
                        shell_context, arg
                    )
                    command_args = (
                        args[arg_index + 1 :] if (arg_index + 1) < len(args) else []
                    )
                    if isinstance(current_command, click.MultiCommand):
                        current_multi_command = current_command

            if not word:
                command_args.append("")

            if isinstance(current_command, click.MultiCommand):
                # if the current command is a multi command, add it's subcommands as possible completion candidates
                completion_candidates.update(
                    current_command.list_commands(shell_context)
                )

            if current_multi_command.chain:
                # if the current multi command allows chaining, add it's subcommands as possible completion candidates as well
                completion_candidates.update(
                    current_multi_command.list_commands(shell_context)
                )

            for param in current_command.params:
                # add all options from the current command as possible completion candidates
                if isinstance(param, click.Option):
                    completion_candidates.update(param.opts)
                    completion_candidates.update(param.secondary_opts)

            if isinstance(current_command, PyworkonCommand):
                # if the command is a pyworkon command ask it also for possible completion candidates
                # discard all other candidates when the command's completions are "exclusive" (e.g. when the candidates are values for an option)
                extra_candidates, exclusive = current_command.get_completions(
                    shell_context, command_args
                )
                if exclusive:
                    completion_candidates = set(extra_candidates)
                else:
                    completion_candidates.update(extra_candidates)

            for candidate in fuzzyfinder(
                word, natsorted(completion_candidates, alg=ns.IGNORECASE)
            ):
                yield Completion(candidate, start_position=start_position)

    completer = PyworkonCompleter()

    while True:
        command = prompt(
            f"{config.prompt_sign}",
            history=history,
            completer=completer,
            auto_suggest=AutoSuggestFromHistory(),
        )

        if command == "exit":
            break
        args = [f"--{command}"] if command == "help" else _split_args(command)

        try:
            pyworkon_context.args = list(args)
            cli(obj=pyworkon_context, prog_name="", args=args, standalone_mode=False)
        except SystemExit:
            #  we ignore any system exit exceptions
            pass
        except click.ClickException as e:
            #  we print all click exceptions
            e.show()

    click.echo("Bye!")
