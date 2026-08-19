"""FastAPI relay app: receives daemon pushes, serves the read-only dashboard."""

from __future__ import annotations

import json
import secrets
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from pyworkon.interfaces.relay.config import RelaySettings
from pyworkon.interfaces.relay.icons import DASHBOARD_ICONS
from pyworkon.interfaces.relay.schema import RelayStatePayload
from pyworkon.interfaces.relay.state import RelayCache

STATIC_DIR = Path(__file__).parent / "static"
FONTS_DIR = STATIC_DIR / "fonts"
UNAUTHORIZED_WS_CODE = 4401
_ICONS_PLACEHOLDER = "/*__PYWORKON_ICONS__*/"


def _render_dashboard_html() -> str:
    template = (STATIC_DIR / "dashboard.html").read_text(encoding="utf-8")
    return template.replace(_ICONS_PLACEHOLDER, json.dumps(DASHBOARD_ICONS))


_DASHBOARD_HTML = _render_dashboard_html()


def _token_matches(provided: str | None, expected: str) -> bool:
    return provided is not None and secrets.compare_digest(provided, expected)


def _bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    return token if scheme.lower() == "bearer" else None


def _healthz() -> JSONResponse:
    return JSONResponse({"status": "ok"})


async def _ingest(request: Request) -> JSONResponse:
    settings: RelaySettings = request.app.state.settings
    if not _token_matches(_bearer_token(request), settings.token):
        raise HTTPException(status_code=401, detail="unauthorized")
    payload = RelayStatePayload.model_validate_json(await request.body())
    cache: RelayCache = request.app.state.cache
    broadcast = cache.set_latest(payload)
    await cache.broadcast(broadcast)
    return JSONResponse({"ok": True})


def _dashboard_page(request: Request) -> HTMLResponse:
    settings: RelaySettings = request.app.state.settings
    if not _token_matches(request.query_params.get("token"), settings.token):
        raise HTTPException(status_code=401, detail="unauthorized")
    return HTMLResponse(_DASHBOARD_HTML)


async def _ws_endpoint(websocket: WebSocket) -> None:
    settings: RelaySettings = websocket.app.state.settings
    if not _token_matches(websocket.query_params.get("token"), settings.token):
        await websocket.close(code=UNAUTHORIZED_WS_CODE)
        return
    cache: RelayCache = websocket.app.state.cache
    await websocket.accept()
    if latest := cache.get_latest():
        await websocket.send_json(latest.model_dump(mode="json"))
    cache.register(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        cache.unregister(websocket)


def create_app(settings: RelaySettings | None = None) -> FastAPI:
    app = FastAPI()
    app.state.settings = settings or RelaySettings()
    app.state.cache = RelayCache()
    app.get("/healthz")(_healthz)
    app.post("/ingest")(_ingest)
    app.get("/")(_dashboard_page)
    app.websocket("/ws")(_ws_endpoint)
    # Icon webfont only — no session/PR data, so it's not token-gated like the
    # dashboard page. `dashboard.html` itself lives outside this directory.
    app.mount("/fonts", StaticFiles(directory=FONTS_DIR), name="fonts")
    return app
