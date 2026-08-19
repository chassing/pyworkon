import uvicorn

from pyworkon.interfaces.relay.app import create_app
from pyworkon.interfaces.relay.config import RelaySettings


def run() -> None:
    settings = RelaySettings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":
    run()
