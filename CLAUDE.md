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
│   └── providers/         # GitHub/GitLab API via clientele
│       ├── github/        # GitHubApi (clientele standalone functions)
│       └── gitlab/        # GitLabApi (clientele standalone functions)
├── interfaces/
│   ├── shell/             # Click CLI (pyworkon command)
│   │   └── commands/      # Subcommands: workon, dashboard, popup, daemon, clone, provider, agent, shell
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
│           ├── pr_link.py          # PRLink — clickable label → webbrowser
│           ├── project_row.py      # ProjectRow — unattached project display
│           └── plain_session_row.py # PlainSessionRow — plain tmux session
├── tmux_mgr.py            # TmuxManager — tmux subprocess calls (async)
└── utils.py               # run_cmd() — async subprocess helper
```

### Daemon ↔ TUI Flow

1. **Daemon** (`server.py`) runs as a background process, listens on a Unix socket
2. Daemon polls tmux sessions and PR data periodically; git branch/dirty state detected via filesystem watchers (`watchfiles`)
3. After each poll cycle or git change, daemon pushes `EVENT(state)` to all subscribers
4. Agent status updates push immediately (no polling delay)
5. **TUI apps** subscribe via `DaemonClient.subscribe()` in a background thread
6. `call_from_thread()` bridges data into Textual's main thread

### Providers

Providers use `clientele`'s **standalone function pattern** (not class methods). Each provider exposes an async context manager via `get_provider()`.

## Textual TUI — CRITICAL Rules

### Widget Architecture

Widgets are fine-grained and composable. Each widget owns its own reactives, CSS (`DEFAULT_CSS`), and `update()` method:

- `SessionCard` composes `SessionHeader`, `BranchRow`, `PRDetail`, `AgentList`
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
- **Git filesystem watchers** (`git_watcher.py`) using `watchfiles` — watches project root with custom filter for `.git/HEAD` (branch) and working tree files (dirty state). Branch changes detected instantly, dirty state via `git status --porcelain -uno`.
- **Circuit breaker** (`pybreaker`) per provider via `get_provider()`. After 3 consecutive API failures, the provider is paused for 5 minutes. Manual `provider sync` resets the breaker (`force=True`).

## CLI

- Uses **Click** (not typer) — the CLI is Click-based
- Subcommands auto-discovered from `interfaces/shell/commands/`
- `PyworkonContext` passed via Click's `obj`

## Nerd Font Icons

Icons are defined in `interfaces/tui/icons.py`. **ALWAYS use explicit Unicode escapes** (e.g., `""`) — never paste the raw glyph character. Raw glyphs get silently stripped by formatters and editors, producing empty strings that are hard to debug.

```python
# GOOD
ICON_GITHUB = ""  # (nf-fa-github)

# BAD — glyph will be silently stripped
ICON_GITHUB = ""  # (nf-fa-github)
```

**ONLY use single-width icons** from the BMP Private Use Area (U+E000–U+F8FF): Powerline, Devicons, Font Awesome, Codicons, etc. **NEVER use Material Design Icons** (U+F0000+, Supplementary PUA) — Nerd Fonts v3 renders them as double-width, which breaks Textual's layout calculations.

### Agent Status Icons

Agent status is set via CLI hooks as plain strings (`idle`, `working`, `waiting`). The TUI maps these to colored Nerd Font icons via `_AGENT_STATUS_ICONS` in `widgets/agent_list.py`. Unknown status values are rendered as-is.

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
