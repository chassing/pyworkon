"""FastAPI relay app: receives daemon pushes, serves the read-only dashboard."""

from __future__ import annotations

import json
import secrets
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from pyworkon.interfaces.relay.config import RelaySettings
from pyworkon.interfaces.relay.icons import DASHBOARD_ICONS
from pyworkon.interfaces.relay.schema import RelayStatePayload
from pyworkon.interfaces.relay.state import RelayCache

STATIC_DIR = Path(__file__).parent / "static"
FONTS_DIR = STATIC_DIR / "fonts"
PWA_DIR = STATIC_DIR / "pwa"
SERVICE_WORKER_PATH = PWA_DIR / "sw.js"
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


def _manifest(request: Request) -> JSONResponse:
    """PWA manifest.

    Embeds the token in `start_url` so "Add to Home Screen" reopens straight
    into the dashboard instead of the 401 gate.
    """
    settings: RelaySettings = request.app.state.settings
    return JSONResponse({
        "name": "pyworkon Relay Dashboard",
        "short_name": "pyworkon",
        "icons": [
            {"src": "/pwa/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/pwa/icon-512.png", "sizes": "512x512", "type": "image/png"},
        ],
        "theme_color": "#14161a",
        "background_color": "#14161a",
        "display": "standalone",
        "start_url": f"/?token={settings.token}",
    })


def _service_worker() -> FileResponse:
    """Served at the root path (not /pwa/sw.js) so its scope covers the whole site."""
    return FileResponse(
        SERVICE_WORKER_PATH,
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache"},
    )


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
    app.get("/manifest.webmanifest")(_manifest)
    app.get("/sw.js")(_service_worker)
    app.websocket("/ws")(_ws_endpoint)
    # Icon webfont + PWA icons only — no session/PR data, so these aren't
    # token-gated like the dashboard page. `dashboard.html` itself lives
    # outside both of these directories.
    app.mount("/fonts", StaticFiles(directory=FONTS_DIR), name="fonts")
    app.mount("/pwa", StaticFiles(directory=PWA_DIR), name="pwa")
    return app
