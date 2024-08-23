import logging.config
import sys

from rich.logging import RichHandler

from pyworkon.config import config
from pyworkon.interfaces import init_cli


def run() -> None:
    logging.basicConfig(
        level="DEBUG" if config.debug else "ERROR",
        format="%(name)-20s: %(message)s",
        datefmt="[%X]",
        handlers=[RichHandler()],
    )
    init_cli(args=sys.argv[1:])


if __name__ == "__main__":
    run()
