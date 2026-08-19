# Relay-only image (pyworkon/interfaces/relay/). Never imports pyworkon.config (which does
# pwd.getpwnam()/mkdir() at import time), so this is safe to run as an
# arbitrary non-root UID, e.g. under an OpenShift `restricted` SCC.
FROM python:3.14-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.5@sha256:e85be844203885286c60ffad8a858d48afb6c5a5c237ca0e67f12e74b8f174b1 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Sync dependencies only first so this layer is cached independently of
# source changes (per uv's documented Docker pattern).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev --extra relay

COPY README.md ./
COPY pyworkon ./pyworkon
RUN uv sync --frozen --no-dev --extra relay --no-editable

EXPOSE 8080
ENV RELAY_HOST=0.0.0.0 RELAY_PORT=8080

ENTRYPOINT ["pyworkon-relay"]
