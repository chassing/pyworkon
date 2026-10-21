import click

from pyworkon.interfaces.shell import cli
lazy from pyworkon.interfaces.strip.app import start_strip


@cli.command()
@click.option(
    "--auto-hide",
    is_flag=True,
    help="Start collapsed to a thin handle; click it to expand.",
)
def strip(*, auto_hide: bool) -> None:
    """Slim always-on-top session strip, docked at the screen bottom."""
    start_strip(auto_hide=auto_hide)
