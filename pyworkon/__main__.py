# from .tui import PyWorkonTui
import logging.config

from rich.logging import RichHandler

from .config import config
from .interfaces import init_cli


def run():
    logging.basicConfig(
        level="DEBUG" if config.debug else "ERROR",
        format="%(name)-20s: %(message)s",
        datefmt="[%X]",
        handlers=[RichHandler()],
    )
    init_cli()


if __name__ == "__main__":
    run()
