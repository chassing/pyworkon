"""
Improved AutoCommandCompletion class - added fuzzyfinder search

based on https://github.com/facebookincubator/python-nubia/blob/main/nubia/internal/completion.py
"""

import enum
from typing import Iterable

import pyparsing as pp
from fuzzyfinder.main import fuzzyfinder
from nubia.internal.cmdbase import AutoCommand as _AutoCommand
from nubia.internal.completion import AutoCommandCompletion as _AutoCommandCompletion
from nubia.internal.completion import TokenParse
from prompt_toolkit.completion import (
    CompleteEvent,
    Completion,
)
from prompt_toolkit.document import Document


class AutoCommandCompletion(_AutoCommandCompletion):
    def _prepare_args_completions(self, parsed_command: pp.ParseResults, last_token) -> Iterable[Completion]:
        """Use fuzzyfinder for argument completion."""
        parsed_token = TokenParse(last_token)
        if parsed_token.is_argument:
            argument_name = parsed_token.argument_name
            arg = self._find_argument_by_name(argument_name)
            if not arg or arg.choices in [False, None]:
                return []
            if parsed_token.is_dict:
                return []
            return [
                Completion(
                    text=str(choice),
                    start_position=-len(parsed_token.last_value),
                )
                # CA: added fuzzyfinder
                for choice in fuzzyfinder(
                    parsed_token.last_value, [c.value if isinstance(c, enum.Enum) else str(c) for c in arg.choices]
                )
            ]
        return super()._prepare_args_completions(parsed_command, last_token)


class AutoCommand(_AutoCommand):
    def get_completions(self, _: str, document: Document, complete_event: CompleteEvent) -> Iterable[Completion]:
        if self._is_super_command:  # type: ignore
            exploded = document.text.lstrip().split(" ", 1)
            # Are we at the first word? we expect a sub-command here
            if len(exploded) <= 1:
                return self._commands_completer.get_completions(document, complete_event)

        state_machine = AutoCommandCompletion(self, document, complete_event)
        return state_machine.get_completions()
