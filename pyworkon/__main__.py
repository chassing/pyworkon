import logging
import sys

from rich.logging import RichHandler

from pyworkon.config import config, user_cache_dir
from pyworkon.interfaces import init_cli

_LOG_FILE = user_cache_dir / "pyworkon.log"


def run() -> None:
    level = "DEBUG" if config.debug else "ERROR"
    handlers: list[logging.Handler] = [RichHandler()]
    if "sidebar" in sys.argv:
        file_handler = logging.FileHandler(_LOG_FILE)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s %(name)s %(levelname)s: %(message)s")
        )
        file_handler.setLevel("DEBUG")
        handlers.append(file_handler)
    logging.basicConfig(
        level=level,
        format="%(name)-20s: %(message)s",
        datefmt="[%X]",
        handlers=handlers,
    )
    init_cli(args=sys.argv[1:])


if __name__ == "__main__":
    run()
