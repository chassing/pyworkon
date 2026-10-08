# pyworkon

Software development project management tool for tmux-based workflows.
Manages projects from GitHub/GitLab, organizes them in tmux sessions, and provides Textual TUI apps (dashboard + popup).

## Quick Reference

```bash
uv run ruff check && uv run ruff format   # lint & format
uv run mypy                                # typecheck (strict)
uv run pytest                              # tests
```

## Architecture

```text
pyworkon/
├── config.py              # pydantic-settings Config, YAML-based (~/.config/pyworkon/config.yaml)
├── daemon/                # Background daemon (fully async, Unix socket)
│   ├── server.py          # asyncio server, event-based push, tmux/PR polling
│   ├── client.py          # Sync socket client (DaemonClient)
│   ├── protocol.py        # JSON-Lines protocol models (Command/Response/Event)
│   ├── models.py          # Daemon-internal dataclasses (OpenProject, AgentInfo)
│   ├── project_mgr.py     # ProjectManager + Project model, diskcache
│   ├── git_watcher.py     # GitWatcher — per-project file watchers (watchfiles)
│   ├── tmux_mgr.py        # TmuxManager — tmux subprocess calls (async)
│   ├── relay_publisher.py # RelayPublisher — optional outbound push to the relay (see "Relay")
│   └── providers/         # GitHub/GitLab API via clientele
│       ├── github/        # GitHubApi (clientele standalone functions)
│       └── gitlab/        # GitLabApi (clientele standalone functions)
├── interfaces/
│   ├── shell/             # Click CLI (pyworkon command)
│   │   └── commands/      # Subcommands: workon, dashboard, popup, daemon, clone, provider, agent, opencode, shell
│   ├── relay/             # FastAPI mobile web dashboard (see "Relay" section below)
│   │   ├── app.py         # create_app() — /healthz, /ingest, /, /ws routes
│   │   ├── config.py      # RelaySettings — real env vars (RELAY_TOKEN/HOST/PORT)
│   │   ├── schema.py      # RelayStatePayload/RelayBroadcastPayload wire DTOs
│   │   ├── state.py       # RelayCache — latest-payload cache + WS fanout
│   │   ├── icons.py       # DASHBOARD_ICONS — reuses interfaces/tui/icons.py
│   │   ├── __main__.py    # `pyworkon-relay` script entrypoint (uvicorn.run)
│   │   └── static/
│   │       ├── dashboard.html   # single-file vanilla JS/CSS dashboard, no build step
│   │       └── fonts/           # self-hosted Nerd Font Symbols-Only subset (woff2)
│   └── tui/               # Textual TUI apps and widgets
│       ├── base.py        # BaseApp — shared daemon subscription, item management, navigation
│       ├── dashboard.py   # DashboardApp — full-detail monitoring, sessions only
│       ├── popup.py       # PopupApp — quick switcher, filter, select+exit
│       ├── data.py        # parse_sidebar_state() — converts daemon state to models
│       ├── models.py      # Pydantic/dataclass models (SessionInfo, PRInfo, etc.)
│       ├── icons.py       # Nerd Font icon constants
│       └── widgets/       # Reusable Textual widgets
│           ├── session_card.py     # SessionCard — composes all sub-widgets per session
│           ├── session_header.py   # SessionHeader — indicator + name + provider icon
│           ├── branch_row.py       # BranchRow — branch icon + name + dirty indicator
│           ├── pr_detail.py        # PRDetail — title, link, state, review, CI checks
│           ├── agent_list.py       # AgentList — dynamic agent rows with status
│           ├── review_request_list.py # ReviewRequestList — PRs requesting user review
│           ├── pr_link.py          # PRLink — clickable label → webbrowser
│           ├── project_row.py      # ProjectRow — unattached project display
│           └── plain_session_row.py # PlainSessionRow — plain tmux session
└── utils.py               # run_cmd() — async subprocess helper
```

### Daemon ↔ TUI Flow

1. **Daemon** (`server.py`) runs as a background process, listens on a Unix socket
2. Daemon polls tmux sessions and PR data periodically; git branch/dirty state detected via filesystem watchers (`watchfiles`)
3. After each poll cycle or git change, daemon pushes `EVENT(state)` to all subscribers
4. Agent status updates push immediately (no polling delay)
5. **TUI apps** subscribe via `DaemonClient.subscribe()` in a background thread
6. `call_from_thread()` bridges data into Textual's main thread

**TUI is tmux-agnostic.** All tmux operations (session switching, creation, killing) go through daemon commands (`SWITCH_SESSION`, `ENTER_PROJECT`, `KILL_SESSION`). The TUI never imports `tmux_mgr` directly — the daemon is the single point of tmux interaction.

### Providers

Providers use `clientele`'s **standalone function pattern** (not class methods). Each provider exposes an async context manager via `get_provider()`.

GitHub providers support `ignored_review_requests`, a list of typed `IgnoredReviewRequests` rules with `repository` (`owner/repo`) and `authors`. The daemon filters review requests by PR author in `_fetch_review_prs_for_provider()` before caching and upstream-to-fork mapping, so TUI and relay receive the same filtered state. Repository/author matching is case-insensitive, matching rules combine their author lists, and branch PR details are unaffected. Configuration changes require a daemon restart.

## Textual TUI — CRITICAL Rules

### Widget Architecture

Widgets are fine-grained and composable. Each widget owns its own reactives, CSS (`DEFAULT_CSS`), and `update()` method:

- `SessionCard` composes `SessionHeader`, `BranchRow`, `PRDetail`, `ReviewRequestList`, `AgentList`
- `PRDetail` is independently reusable (has `show_ci_checks` parameter)
- `AgentList` is independently reusable
- `BaseApp` provides shared daemon subscription, item management, navigation
- `DashboardApp` and `PopupApp` override hooks for different behavior

### Use Reactive Properties — NEVER Manual Widget Updates

The TUI uses Textual's **reactive system** for all widget updates. This is non-negotiable.

**Pattern:**

```python
class MyWidget(Widget):
    my_text: reactive[str] = reactive("")

    def watch_my_text(self, value: str) -> None:
        with contextlib.suppress(Exception):
            self.query_one("#my-label", Label).update(value)
```

**DO:**

- Declare display data as `reactive[T]` class variables
- Implement `watch_<name>()` methods that update the DOM
- Change reactives in data-update methods → watchers handle the rest

**DO NOT:**

- Manually call `.update()` or `.remove()` on widgets outside of watchers
- Bypass the reactive system with direct DOM manipulation for data that changes over time

### Incremental Updates vs Full Rebuild

- **Structure unchanged** (same sessions, same order): update existing `SessionCard` widgets via `update_session()` → delegates to child widget `update()` methods
- **Structure changed** (session added/removed/reordered): full `_render_items()` rebuild with new `_render_generation` counter

### Widget ID Scheme

Widgets use `id=f"row-{generation}-{index}"` to avoid stale references after a rebuild.

### CSS-in-Python

All widget styles are defined as `DEFAULT_CSS` class variables, not in external `.tcss` files. Use Textual's CSS class toggling (`add_class` / `remove_class`) for state changes (e.g., `--highlight`, `--current-session`).

## Daemon

- Fully async (`asyncio`) — no `asyncio.to_thread()`, no sync blocking calls in the daemon
- JSON-Lines protocol over Unix socket
- Commands/responses defined as pydantic models in `protocol.py`
- Daemon-internal state uses `dataclasses` (`models.py`), not pydantic
- All subprocess calls go through `utils.run_cmd()` (async wrapper around `asyncio.create_subprocess_exec`)
- **Event-based push** via `SUBSCRIBE` command with event categories (`state`, `notification`). Clients specify which events they want and whether to receive initial state (`full=True`). Daemon pushes `EVENT` responses whenever state changes.
- **Git filesystem watchers** (`git_watcher.py`) using `watchfiles` — watches project root with custom filter for `.git/HEAD` (branch), `.git/index`, `.git/refs/heads/` (commit detection), and working tree files (dirty state). Branch changes detected instantly, dirty state via `git status --porcelain -uno`.
- **Circuit breaker** (`pybreaker`) per provider via `get_provider()`. After 3 consecutive API failures, the provider is paused for 5 minutes. Manual `provider sync` resets the breaker (`force=True`).
- **Tmux management** (`tmux_mgr.py`) lives in the daemon package. The daemon is the single owner of all tmux operations: session creation, switching, killing, and polling. TUI and CLI never import `tmux_mgr` directly.

### Protocol Commands

| Command             | Fields                               | Purpose                                                                |
| ------------------- | ------------------------------------ | ---------------------------------------------------------------------- |
| `OPEN_PROJECT`      | `project_id`, `pane_id?`, `session?` | Register a project as open (called by `workon` on shell entry)         |
| `CLOSE_PROJECT`     | `project_id`, `pane_id?`             | Unregister a single pane (called by `workon` on shell exit)            |
| `ENTER_PROJECT`     | `project_id`                         | Create tmux session (if needed) and switch to it (called by popup/TUI) |
| `SWITCH_SESSION`    | `session`, `pane_id?`                | Switch to an existing tmux session/pane (called by popup/TUI)          |
| `KILL_SESSION`      | `session`                            | Kill a tmux session and clean up all tracking (called by popup Ctrl-X) |
| `SUBSCRIBE`         | `events[]`, `full?`                  | Subscribe to push events (`state`, `notification`)                     |
| `AGENT_STATUS`      | `session`, `pid`, `name`, `status`   | Update agent status for a session (matched by `pid`, not `name`)       |
| `AGENT_CLEAR`       | `session`, `pid`                     | Remove an agent from a session (matched by `pid`)                      |
| `LIST_PROJECTS`     | `local?`                             | List all known projects                                                |
| `GET_PROJECT`       | `project_id`                         | Get a single project                                                   |
| `CLONE_PROJECT`     | `project_id`                         | Clone a project repository                                             |
| `SYNC_PROVIDERS`    | —                                    | Force-sync all providers                                               |
| `GET_SIDEBAR_STATE` | —                                    | One-shot state query (no subscription)                                 |
| `STATUS`            | —                                    | Daemon health/stats                                                    |
| `NOTIFY`            | `message`, `level?`                  | Broadcast a notification to subscribers                                |
| `SHUTDOWN`          | —                                    | Stop the daemon                                                        |

### CRITICAL: State Event Push Rule

**Every command that modifies `_open_projects` MUST call `_push_event("state", self._build_sidebar_state())`.** Without this, TUI subscribers (dashboard, popup) won't see the change until the next 5-second polling cycle. This was the root cause of multiple "session doesn't appear" bugs.

Commands that push state: `OPEN_PROJECT`, `CLOSE_PROJECT`, `KILL_SESSION`, `AGENT_STATUS`, `AGENT_CLEAR`, branch/dirty change callbacks.

### `AgentInfo` Identity is `pid`, Not `name`

`AgentInfo.pid` (from `_find_claude_pid()` in `interfaces/shell/commands/agent.py`) is the stable identity the daemon uses to match an existing entry in `OpenProject.agents` — `AgentInfo.name` is display-only and can legitimately change between hook calls for the *same* agent (the resolved title updates as the session's live `agent-name`/`ai-title` transcript field changes, e.g. when a delegated sub-agent starts). `_cmd_agent_status`/`_cmd_agent_clear` in `server.py` match by `pid`; matching by `name` instead caused duplicate stale entries for the same session. When updating an existing entry, update both `name` and `status` in place — never append a second `AgentInfo` for a pid that's already tracked.

### `_open_projects` Key Schema

Keys follow the pattern `{project_id}|{qualifier}`:

- `github/owner/repo|%5` — opened by `workon` with tmux pane `%5`
- `github/owner/repo|default` — opened without pane_id
- `github/owner/repo|tmux` — auto-discovered by `_poll_tmux()` or created by `ENTER_PROJECT`

The same project can have **multiple entries** (different panes/windows). `CLOSE_PROJECT` removes one entry by key. Git watcher is only unwatched when **no entries** remain for that `project_id`.

### Session Ownership (`PYWORKON_PROJECT_ID`)

Sessions created by pyworkon (via `tmuxp load`) get `PYWORKON_PROJECT_ID` as a tmux session environment variable. `KILL_SESSION` checks for this before killing — sessions without it are protected (daemon sends a warning notification instead). This prevents killing manually-created tmux sessions that happen to have `workon` running inside them.

### `_push_event` is Sync

`_push_event` uses `writer.write()` (buffer-only, no `drain()`) so it can be called from sync contexts like the circuit breaker callback (`_broadcast`). This means it doesn't await — data goes into the kernel buffer but delivery is not guaranteed before the next `await`.

## Relay (mobile web dashboard)

A read-only mobile web dashboard, fed by the daemon pushing state outbound to a small relay service (deployed separately, e.g. in a k8s cluster) rather than the phone connecting inbound to the laptop:

```text
laptop daemon --(outbound HTTPS POST, Authorization: Bearer <token>)--> relay --(WebSocket push, ?token=)--> phone browser
```

- **Daemon side** (`daemon/relay_publisher.py`): `RelayPublisher` is constructed in `Daemon.__init__` only when `config.relay_url` is set (`Config.relay_url: HttpUrl | None`, `Config.relay_token: str | None`) — fully inert otherwise. `Daemon._push_event()` calls `RelayPublisher.submit()` for every `"state"` event (not `"notification"`), which replaces any not-yet-sent payload in an `asyncio.Queue(maxsize=1)` (only the latest state matters — no backlog). A background task (`RelayPublisher.run()`) drains the queue and does a best-effort `httpx2.AsyncClient` POST to `{relay_url}/ingest`; failures/recoveries are logged only on the transition (mirrors `daemon/providers/circuit_breaker.py`'s log-spam-avoidance style), never per attempt. `to_relay_payload()` sanitizes `SidebarStatePayload` into `RelayStatePayload` — critically, it strips `Project.provider` (a `config.Provider`, which carries a `password` credential field) down to just `provider_type`, since this payload leaves the laptop.
- **Relay side** (`interfaces/relay/`): a standalone FastAPI app (`pyworkon-relay` script entrypoint), deployed independently from the daemon (see `deploy/Dockerfile`). **Must never import `pyworkon.config`, `daemon.protocol`, or `daemon.project_mgr`** — `pyworkon.config` runs `pwd.getpwnam()`/`mkdir()` at import time, which crashes under an arbitrary non-root UID (e.g. OpenShift's `restricted` SCC), which the relay container is expected to run under. `interfaces/relay/schema.py` only imports `daemon.models` (a dependency-free leaf module) for this reason — verified by `tests/test_relay_icons.py::test_importing_relay_icons_does_not_pull_in_pyworkon_config`, which must keep passing. `RelaySettings` (`interfaces/relay/config.py`) reads real env vars (`RELAY_TOKEN`/`RELAY_HOST`/`RELAY_PORT`) since the container has no `~/.config/pyworkon/config.yaml`.
- **Auth**: both the daemon's `POST /ingest` and the browser-facing `GET /` + `WS /ws` require the shared token (`secrets.compare_digest`). The daemon sends it as `Authorization: Bearer`; browsers can't set custom headers for a plain navigation or the native `WebSocket` handshake, so those two use a `?token=` query param instead.
- **Dashboard** (`interfaces/relay/static/dashboard.html`): single file, no build step, vanilla JS WebSocket client. Icons come from `interfaces/relay/icons.py`, which builds a `DASHBOARD_ICONS` dict directly from `interfaces/tui/icons.py` (stripping Rich color markup — the web page colors via CSS classes instead) and is injected into the served HTML at import time by replacing a `/*__PYWORKON_ICONS__*/` placeholder with JSON. **Never hardcode icon glyphs in `dashboard.html` — add a key to `interfaces/relay/icons.py` instead.** The PUA glyphs are served via a self-hosted webfont (`static/fonts/pyworkon-icons.woff2`) since phones essentially never have a Nerd Font installed; it's subsetted from the **Mono** variant of Nerd Fonts' "Symbols Nerd Font" release specifically because the proportional variant has wildly inconsistent per-glyph advance widths (regenerate via the command in `static/fonts/NERD_FONTS_LICENSE.txt` if a new icon is added). "Working"/pending states animate through the same Braille-dot frames Rich's `Spinner("dots", ...)` uses in the TUI, driven by one shared `setInterval` keyed off `data-spin="true"` elements.
- **Staleness**: the relay stamps `pushed_at` itself (not trusting the daemon's clock) when caching an ingest; the browser compares `Date.now()` against it every second and shows a banner past `stale_after_seconds` (`sidebar_refresh_interval * RELAY_STALE_MULTIPLIER`), mirroring the TUI's `#provider-banner` outage-banner pattern in `interfaces/tui/base.py` instead of the page just failing to load.
- **Deployment**: `deploy/Dockerfile` builds a relay-only image via `uv sync --frozen --no-dev --extra relay --no-editable` (the `relay` extra — `fastapi`/`uvicorn` — is optional so a plain CLI install doesn't pull in a web server), using the official `ghcr.io/astral-sh/uv` image (digest-pinned) rather than plain `pip`. `.github/workflows/build.yaml` builds and pushes it to `ghcr.io/<repo>-relay` on every push to `main`. k8s manifests live in a separate infra repo (not this one) — see that repo's `k3s/pyworkon-relay.yaml` for the actual `Namespace`/`Secret`/`Deployment`/`Service`/`IngressRoute` (HTTPS via the cluster's default wildcard cert, no per-route `tls:` needed).
- **PWA**: `interfaces/relay/static/pwa/` holds the manifest icons + service worker so iOS/Android can "Add to Home Screen". `GET /manifest.webmanifest` is generated per-request (not a static file) specifically so it can embed the configured token into `start_url` — otherwise relaunching from the home-screen icon would just hit the 401 gate. `GET /sw.js` is served at the root path (not `/pwa/sw.js`) so its scope covers the whole site; the worker only ever caches `/fonts/`/`/pwa/` static assets, never the dashboard page, `/ingest`, or the `/ws` connection — this is a live view that must never serve stale cached state.

## CLI

- Uses **Click** (not typer) — the CLI is Click-based
- Subcommands auto-discovered from `interfaces/shell/commands/`
- `app.py` installs the standalone macOS Dashboard wrapper with a nested `Contents/Resources/Pyworkon Terminal.app` runtime copied from `/Applications/Ghostty.app` using `ditto --noqtn`. The wrapper opens the nested native bundle through `/usr/bin/open -na ... --args --config-file=...`, preserving a valid application PID for accessibility/window managers such as Rectangle. The runtime uses `dev.pyworkon.dashboard.terminal` and the bundled `PyworkonDashboard.icns`; its `CFBundleIconName` and `NSDockTilePlugIn` overrides are removed. Do not use Ghostty's `macos-icon` custom settings: its Dock plugin shares icon preferences across instances. Only the copy is ad-hoc signed (preserving entitlements) and verified. Installation builds in a temporary sibling directory before replacing the old app, with rollback on publication failure. The Dashboard config disables runtime auto-updates. Close the Dashboard and rerun `pyworkon app install` after pyworkon/Ghostty upgrades; the original Ghostty app is never modified.
- `PyworkonContext` passed via Click's `obj`
- `Config.ai_agent_command` selects the command in the default tmux AI pane (default: `opencode`), including shell-quoted options and arguments. `TmuxManager.create_session()` passes shell-quoted `PYWORKON_TMUX_AI_AGENT_COMMAND` and `PYWORKON_TMUX_AI_AGENT_TITLE` to tmuxp because tmuxp expands variables before the pane shell parses them. These internal variables are separate from the raw `PYWORKON_AI_AGENT_COMMAND` configuration source. The title is the executable's basename. Project-local `.tmuxp.yml` overrides remain unchanged. Restart the daemon for configuration changes; existing sessions are unaffected.
- **`interfaces/shell/commands/__init__.py` shadows submodule names**: it does `from .agent import agent` (etc.), so `pyworkon.interfaces.shell.commands.agent` resolves to the Click *command* object, not the submodule, once the package is imported. Tests that need the submodule itself (e.g. `tests/test_agent_cli.py`) must use `importlib.import_module("pyworkon.interfaces.shell.commands.agent")` instead of `from ... import agent` / `import ...agent as x`.

### Agent Name Resolution (`pyworkon agent`)

`_resolve_agent_name()` in `interfaces/shell/commands/agent.py` derives a human-readable agent name instead of a bare PID:

1. `_find_agent_process()` — Claude Code, Codex, and OpenCode hooks can run via a transient shell, so the hook's direct parent (`os.getppid()`) may not be the stable agent process. Walks up the process tree (via `ps`) to find a `claude`, `codex`, or `opencode` ancestor, bounded to a few hops, falling back to the direct parent PID. `agent --pid` overrides this identity for integrations; tmux lookups target `TMUX_PANE` when present rather than the ambient active session.
2. For Claude Code, `_process_cwd()` resolves the `claude` process's cwd (`/proc/<pid>/cwd` on Linux, `lsof -a -d cwd -p <pid>` on macOS).
3. `_find_active_transcript()` — Claude Code transcripts live at `~/.claude/projects/<cwd-with-slashes-as-dashes>/<session-id>.jsonl`. A running session can silently move to a **new session ID** (e.g. after compaction) without the process's command line changing, so parsing `--resume <uuid>` from argv is unreliable — instead, pick the most recently *modified* `.jsonl` in that project directory, which reflects the session the process is actually writing to right now.
4. `_extract_latest_transcript_field()` — Claude Code writes live `{"type": "agent-name", "agentName": "..."}` entries to the transcript (the same short slug shown by dashboard/FleetView-style UIs — it can change mid-session as delegated sub-agents run) and a stable `{"type": "ai-title", "aiTitle": "..."}` entry. Use the **latest** `agent-name` entry, falling back to the latest `ai-title` entry.

Falls back to `<agent>-<pid>` whenever no Claude transcript name is available. Codex and standalone OpenCode CLI calls use this fallback name. Do NOT synthesize a title from the first user message — Claude Code already provides both fields above, use them instead of re-deriving.

### OpenCode V2 Integration

`pyworkon/assets/opencode/` contains the CLI-only TypeScript plugin. The wheel bundles its runtime files (`tui.ts`, `status.ts`), excluding development dependencies, tests, and tooling metadata. `pyworkon opencode install` (`interfaces/shell/commands/opencode.py`) reads these package resources and copies the runtime files to `~/.config/opencode/plugins/pyworkon/`, respecting `XDG_CONFIG_HOME`. OpenCode discovers this directory automatically; no development checkout or configuration edits are needed. Rerun the installer after upgrading pyworkon to refresh the copied plugin.

The plugin must not run in the shared background server: only the CLI has a reliable `TMUX`/`TMUX_PANE` and terminal PID. It invokes `pyworkon agent --pid <terminal-pid> --name <session-title> --status <status>` with literal subprocess arguments (never a shell), targeting the existing daemon protocol without changes to the TUI or relay.

`status.ts` derives status from the selected root session and its family: pending permissions/forms take precedence (`waiting`), then execution (`working`), otherwise `idle`. A Solid reactive effect watches route, title, and cached state changes. OpenCode owns permission/form hydration; the plugin only reads its reactive cache and must not initiate synchronization. New sessions are cached optimistically before server creation, so even a cached session can return 404 if synchronized too early. Regression tests use OpenCode's actual data layer with a blocked creation request. Unrelated sessions/background tabs are excluded. `AgentReporter` serializes and deduplicates writes, reports failures once per outage, and clears only after in-flight writes finish during cleanup. `tui.ts` also performs bounded best-effort synchronous cleanup on process exit, since the exit event cannot await promises. Forced kills cannot run cleanup.

Runtime Solid imports must stay in `tui.ts`, where OpenCode resolves them to its shared runtime. Pass `createEffect` and `createRoot` into `watchAgent`; `status.ts` uses only type imports from `solid-js`. Importing Solid at runtime from the helper fails in the compiled OpenCode executable even when ordinary Bun tests pass. `loading.test.ts` tests the installed files against a compiled host without local `node_modules`, including host-signal reactivity and cleanup (ad-hoc signing the temporary host on macOS).

Run `make opencode-check` for frozen Bun dependency installation, strict TypeScript checking (including dependencies), and Bun tests. `make ci` includes these checks; Bun is a development requirement, not a Python runtime dependency.

## Nerd Font Icons

Icons are defined in `interfaces/tui/icons.py`. **ALWAYS use explicit Unicode escapes** (e.g., `""`) — never paste the raw glyph character. Raw glyphs get silently stripped by formatters and editors, producing empty strings that are hard to debug.

```python
# GOOD
ICON_GITHUB = ""  # (nf-fa-github)

# BAD — glyph will be silently stripped
ICON_GITHUB = ""  # (nf-fa-github)
```

**ONLY use single-width icons** from the BMP Private Use Area (U+E000–U+F8FF): Powerline, Devicons, Font Awesome, Codicons, etc. **NEVER use Material Design Icons** (U+F0000+, Supplementary PUA) — Nerd Fonts v3 renders them as double-width, which breaks Textual's layout calculations.

### Agent Status Icons

Agent status is set via CLI hooks as plain strings (`idle`, `working`, `waiting`). The TUI maps these to colored Nerd Font icons via `_AGENT_STATUS_ICONS` in `widgets/agent_list.py`. Unknown status values are rendered as-is.

### Reuse in the relay web dashboard

`interfaces/relay/icons.py` builds its icon set from these same constants rather than duplicating glyphs — see the "Relay" section above. Add new dashboard icons there, not as hardcoded glyphs in `dashboard.html`.

## Testing

```bash
uv run pytest                              # run all tests
uv run pytest --cov=pyworkon               # with coverage
uv run pytest tests/test_widgets.py -v     # single file
make test                                  # via Makefile
make ci                                    # lint + typecheck + tests
```

**Rules:**

- ALWAYS use pytest functions, never class-based tests
- Use `@pytest.fixture` for reusable test data and dependencies
- Use `@pytest.mark.parametrize` for testing with different inputs
- Keep tests focused and fast, mock I/O where needed
- Async tests work automatically (`asyncio_mode = "auto"`)
- Textual widget tests use `app.run_test()` pattern from `textual.testing`
- Shared fixtures in `tests/conftest.py`: `make_session_info()`, `make_pr_info()`, `tmp_git_repo`, `project`
- Relay tests (`tests/test_relay_*.py`): mock the daemon's outbound `httpx2` calls with the `httpx_mock` fixture from `httpx2-pytest` (import name `pytest_httpx2`), not `respx` (which targets real `httpx`, not `httpx2`). `fastapi.testclient.TestClient` works out of the box — `starlette.testclient` itself runs on `httpx2` now, no real `httpx` dependency needed anywhere in this project.

## Key Patterns

- **No inline imports.** All imports go at the top of the file. Never use `from X import Y` inside functions or methods — there are no circular import issues in this codebase that would justify it.
- `contextlib.suppress(Exception)` for best-effort DOM queries in watchers
- `contextlib.suppress(subprocess.CalledProcessError)` for optional tmux/git calls
- `StrEnum` for all enum types (`PRStatus`, `PRState`, `ProviderType`, `CommandType`, `ResponseType`)
- Pydantic models for API-facing data, `@dataclass` for internal transfer objects
- `appdirs` for platform-specific config/cache paths
- `diskcache.Cache` for project list persistence

## Maintaining This File

**Keep this CLAUDE.md up to date.** When making code changes that affect architecture, patterns, conventions, or module responsibilities, update the relevant sections in this file as part of the same change. This includes:

- Adding/removing/renaming modules or commands
- Changing the daemon protocol or data flow
- Introducing new patterns or deprecating existing ones
- Modifying the Textual widget/reactive structure
