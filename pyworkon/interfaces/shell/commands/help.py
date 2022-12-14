import enum
import textwrap

from nubia.internal import parser
from nubia.internal.commands.help import HelpCommand
from nubia.internal.exceptions import (
    CommandError,
    UnknownCommand,
)
from rich.console import (
    Console,
    Group,
)
from rich.padding import Padding
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.theme import Theme
from rich_click.rich_click import (
    ALIGN_COMMANDS_PANEL,
    COLOR_SYSTEM,
    MAX_WIDTH,
    STYLE_COMMANDS_PANEL_BORDER,
    STYLE_METAVAR,
    STYLE_OPTION,
    STYLE_SWITCH,
    STYLE_USAGE,
    _make_command_help,
)


def blend_text(message: str, color1: tuple[int, int, int], color2: tuple[int, int, int]) -> Text:
    """Blend text from one color to another."""
    text = Text(message)
    r1, g1, b1 = color1
    r2, g2, b2 = color2
    dr = r2 - r1
    dg = g2 - g1
    db = b2 - b1
    size = len(text)
    for index in range(size):
        blend = index / size
        color = f"#{int(r1 + dr * blend):2X}{int(g1 + dg * blend):2X}{int(b1 + db * blend):2X}"
        text.stylize(color, index, index + 1)
    return text


FOOTER_TEXT = blend_text("Made with ♥ by https://github.com/chassing/pyworkon", (32, 32, 255), (255, 32, 255))


def run_interactive(self, _0, args, _2):
    """Print nicely formatted help text using rich

    Based on original code from rich-click, by @ewels.
    https://github.com/ewels/rich-click
    """
    console = Console(
        theme=Theme(
            {
                "option": STYLE_OPTION,
                "switch": STYLE_SWITCH,
                "metavar": STYLE_METAVAR,
                "usage": STYLE_USAGE,
            }
        ),
        color_system=COLOR_SYSTEM,
    )

    if args and (arguments := args.split()):
        try:
            cmd_name = arguments[0]
            autocmd = self.registry.find_command(cmd_name)
            if not autocmd:
                raise UnknownCommand(f"Command `{cmd_name}` is unknown")

            if autocmd.super_command and len(arguments) == 1:
                # list subcommands
                commands_table = Table(highlight=False, box=None, show_header=False)
                commands_table.add_column(style="bold cyan", no_wrap=True)

                for _, subcmd in autocmd.metadata.subcommands:
                    commands_table.add_row(subcmd.command.name, _make_command_help(subcmd.command.help))
                help_msg = commands_table
                help_title = "Subcommands"
            else:
                if autocmd.super_command and len(arguments) > 1:
                    # print subcommand help
                    parsed = parser.parse(" ".join(arguments[1:]), expect_subcommand=True).asDict()
                    cmd = autocmd.subcommand_metadata(parsed["__subcommand__"])

                else:
                    cmd = autocmd.metadata

                options_table = Table(
                    highlight=False, box=None, show_header=False, title="Options and Arguments", title_justify="left"
                )
                options_table.add_column(style="bold cyan", no_wrap=True)
                for arg in cmd.arguments.values():
                    choices = None
                    if arg.choices:
                        choices = textwrap.shorten(
                            ", ".join([c.value if isinstance(c, enum.Enum) else str(c) for c in arg.choices]),
                            width=100,
                            placeholder="...",
                        )
                    arg_values = "\n[Values: " + choices + "]" if choices else ""
                    options_table.add_row(arg.name, f"{arg.description}{arg_values}")
                help_msg = Group(_make_command_help(cmd.command.help), Padding(options_table, (1, 0, 0, 0)))
                help_title = cmd.command.name
        except CommandError as e:
            console.print(f"[red]{str(e)}[/]")
            return 1
    else:
        # list commands
        commands_table = Table(highlight=False, box=None, show_header=False)
        commands_table.add_column(style="bold cyan", no_wrap=True)
        for cmd in sorted(self.registry.get_all_commands(), key=lambda c: c.built_in):
            cmd_names = list(cmd.get_command_names())
            if cmd_names[0] in ["connect", ":verbose"]:
                continue
            cmd_help = cmd.get_help(cmd_names[0])
            commands_table.add_row(", ".join(cmd_names), _make_command_help(cmd_help))

        help_msg = commands_table
        help_title = "Commands"

    console.print(
        Panel(
            help_msg,
            border_style=STYLE_COMMANDS_PANEL_BORDER,
            title=help_title,
            title_align=ALIGN_COMMANDS_PANEL,
            width=MAX_WIDTH,
        )
    )
    console.print(FOOTER_TEXT, justify="right")
    return 0


HelpCommand.run_interactive = run_interactive
