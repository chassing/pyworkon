# pyworkon

Software development project management tool for tmux-based workflows.
Manages projects from GitHub/GitLab, organizes them in tmux sessions, and provides a Textual TUI sidebar.

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
│   ├── server.py          # asyncio server, polling loop (tmux, git, PR data)
│   ├── client.py          # Sync socket client (DaemonClient)
│   ├── protocol.py        # JSON-Lines protocol models (Command/Response)
│   ├── models.py          # Daemon-internal dataclasses (OpenProject, AgentInfo)
│   ├── project_mgr.py     # ProjectManager + Project model, diskcache
│   └── providers/         # GitHub/GitLab API via clientele
│       ├── github/        # GitHubApi (clientele standalone functions)
│       └── gitlab/        # GitLabApi (clientele standalone functions)
├── sidebar/               # Textual TUI sidebar
│   ├── app.py             # SidebarApp, SessionRow, ProjectRow, PlainSessionRow, PRLink
│   ├── data.py            # SessionDataCollector (reads from daemon socket)
│   ├── models.py          # Pydantic/dataclass models (SessionInfo, PRInfo, etc.)
│   └── icons.py           # Nerd Font icon constants
├── interfaces/shell/      # Click CLI (pyworkon command)
│   └── commands/          # Subcommands: workon, sidebar, daemon, clone, provider, agent, shell
├── tmux_mgr.py            # TmuxManager — all tmux subprocess calls (async)
└── utils.py               # run_cmd() — async subprocess helper
```

### Daemon ↔ Sidebar Flow

1. **Daemon** (`server.py`) runs as a background process, listens on a Unix socket (`~/.cache/pyworkon/daemon.sock`)
2. Daemon polls tmux sessions, git branches, and PR data on a configurable interval (`sidebar_refresh_interval`)
3. **Sidebar TUI** (`app.py`) connects via `DaemonClient` (sync socket), polls with `@work(thread=True)`
4. `call_from_thread()` bridges background thread data into Textual's main thread

### Providers

Providers use `clientele`'s **standalone function pattern** (not class methods). Each provider exposes an async context manager via `get_provider()`.

## Textual TUI — CRITICAL Rules

### Use Reactive Properties — NEVER Manual Widget Updates

The sidebar uses Textual's **reactive system** for all widget updates. This is non-negotiable.

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

- **Structure unchanged** (same sessions, same order): update existing `SessionRow` widgets via `update_session()` → triggers reactive watchers
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
- **Circuit breaker** (`pybreaker`) per provider via `get_provider()`. After 3 consecutive API failures, the provider is paused for 5 minutes (one WARNING logged). On recovery, one INFO logged. Manual `provider sync` resets the breaker (`force=True`). Config: `providers/circuit_breaker.py`.
- **Push notifications** via `SUBSCRIBE` command. Sidebar/dashboard opens a dedicated second socket connection, daemon pushes `NOTIFICATION` responses for circuit breaker events, sync results, and manual `daemon notify` messages. Circuit breaker integration via `set_notification_callback()` in `circuit_breaker.py`. Client: `subscribe_notifications()` (blocking iterator). App: `_listen_notifications()` worker → `self.notify()` toasts.

## CLI

- Uses **Click** (not typer) — the CLI is Click-based
- Subcommands auto-discovered from `interfaces/shell/commands/`
- `PyworkonContext` passed via Click's `obj`

## Nerd Font Icons

Icons are defined in `sidebar/icons.py`. **ALWAYS use explicit Unicode escapes** (e.g., `""`) — never paste the raw glyph character. Raw glyphs get silently stripped by formatters and editors, producing empty strings that are hard to debug.

```python
# GOOD
ICON_GITHUB = ""  # (nf-fa-github)

# BAD — glyph will be silently stripped
ICON_GITHUB = ""  # (nf-fa-github)
```

**ONLY use single-width icons** from the BMP Private Use Area (U+E000–U+F8FF): Powerline, Devicons, Font Awesome, Codicons, etc. **NEVER use Material Design Icons** (U+F0000+, Supplementary PUA) — Nerd Fonts v3 renders them as double-width, which breaks Textual's layout calculations.

### Agent Status Icons

Agent status is set via CLI hooks as plain strings (`idle`, `working`, `waiting`). The sidebar maps these to colored Nerd Font icons via `_AGENT_STATUS_ICONS` in `app.py`. Unknown status values are rendered as-is.

## Key Patterns

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
