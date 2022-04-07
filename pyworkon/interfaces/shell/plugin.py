import argparse
import logging
import sys
import textwrap
from typing import Any

from nubia import PluginInterface, context
from nubia.internal import cmdloader
from nubia.internal.io import logger
from pygments.token import Token

from ...config import config
from .command import AutoCommand


class ShellContext(context.Context):
    """."""

    def get_prompt_tokens(self) -> list[tuple[Any, str]]:
        """Override interactive prompt."""
        tokens = [(Token.String, config.prompt_sign), (Token.Colon, "")]
        return tokens


class ShellPlugin(PluginInterface):
    """."""

    def setup_logging(self, root_logger, args):
        if args.verbose and args.verbose >= 2:
            logging_level = logging.DEBUG
        elif args.verbose == 1:
            logging_level = logging.INFO
        else:
            logging_level = logging.WARN

        logger.setup_logger(level=logging_level, stream=sys.stderr)

        return True

    def get_opts_parser(self, add_help=True):
        opts_parser = argparse.ArgumentParser(
            description=textwrap.dedent(
                r"""
                    TODO
            """
            ),
            epilog=textwrap.dedent(
                """
                NOTES:
                    LIST types are given as space separated values (e.g. --hosts server1 server 2).
            """
            ),
            formatter_class=argparse.RawTextHelpFormatter,
            add_help=add_help,
        )
        opts_parser.add_argument(
            "--verbose", "-v", action="count", default=0, help="Increase verbosity, can be specified multiple times"
        )

        opts_parser.add_argument(
            "-f", "--force", action="store_true", help="Don't ask stupid questions, just do what I want!"
        )
        opts_parser.add_argument(
            "-q",
            "--quiet",
            action="store_true",
            help="Silent or quiet mode. Don't show progress meter, spinners or messages.",
        )

        return opts_parser

    def create_context(self):
        """."""
        return ShellContext()

    def get_commands(self):
        from . import commands

        return [AutoCommand(cmd) for cmd in cmdloader.load_commands(commands)]
