# Development Guide

## Development Setup

```bash
git clone https://github.com/chassing/pyworkon.git
cd pyworkon
uv sync
```

### Quality Commands

```bash
uv run ruff check       # lint
uv run ruff format      # format
uv run mypy             # type check (strict)
uv run pytest           # tests
make ci                 # all of the above
```

### Running Tests

```bash
uv run pytest                              # all tests
uv run pytest --cov=pyworkon               # with coverage report
uv run pytest tests/test_widgets.py -v     # single file, verbose
uv run pytest -k "test_branch"             # filter by name
```

**Test structure:**
- `tests/test_protocol.py` — daemon protocol serialization
- `tests/test_tui_models.py` — TUI data models (PRInfo, SessionInfo, etc.)
- `tests/test_data.py` — `parse_sidebar_state()` function
- `tests/test_project.py` — Project git methods (uses temp git repos)
- `tests/test_git_watcher.py` — GitWatcher lifecycle (async)
- `tests/test_daemon.py` — Daemon state management (mocked)
- `tests/test_widgets.py` — Textual widget rendering
- `tests/test_apps.py` — DashboardApp/PopupApp composition

**Conventions:**
- pytest functions only, no classes
- `@pytest.fixture` for test data, `@pytest.mark.parametrize` for variants
- Shared fixtures in `tests/conftest.py`
- Async tests work automatically (`asyncio_mode = "auto"` in pyproject.toml)

## Code Structure

```text
pyworkon/
├── __main__.py                     # Entry point, logging setup
├── config.py                       # Config model (pydantic-settings, YAML source)
├── exceptions.py                   # Custom exceptions
├── tmux_mgr.py                     # Tmux subprocess integration (sessions, panes, agents)
├── defaults/
│   └── tmuxp.yml                   # Default tmuxp layout (main + AI windows)
├── interfaces/
│   ├── __init__.py                 # CLI initialization
│   ├── shell/
│   │   ├── __init__.py             # Click CLI group, PyworkonContext
│   │   ├── command.py              # Custom Click command classes with completion support
│   │   ├── common.py               # Utilities (in_shell detection)
│   │   └── commands/
│   │       ├── __init__.py         # Re-exports all commands
│   │       ├── workon.py           # Enter a project (session-based or pane-based)
│   │       ├── clone.py            # Clone a remote project
│   │       ├── provider.py         # Provider sync + ls
│   │       ├── daemon.py           # Daemon start/stop/status
│   │       ├── shell.py            # Interactive shell with fuzzy completion
│   │       ├── dashboard.py        # Dashboard TUI command
│   │       ├── popup.py            # Popup TUI command
│   │       └── agent.py            # Set/clear AI agent status
│   └── tui/                        # Textual TUI apps and widgets
│       ├── base.py                 # BaseApp — shared daemon subscription, navigation
│       ├── dashboard.py            # DashboardApp — full-detail monitoring
│       ├── popup.py                # PopupApp — quick switcher with filtering
│       ├── data.py                 # parse_sidebar_state() — daemon state → models
│       ├── models.py               # TUI data models (SessionInfo, PRInfo, etc.)
│       ├── icons.py                # Nerd Font / Unicode icon constants
│       └── widgets/                # Reusable Textual widgets
│           ├── __init__.py         # Re-exports, SidebarItem type alias
│           ├── session_card.py     # SessionCard — composes sub-widgets per session
│           ├── session_header.py   # SessionHeader — indicator + name + provider icon
│           ├── branch_row.py       # BranchRow — branch + dirty indicator
│           ├── pr_detail.py        # PRDetail — PR title, link, state, review, CI checks
│           ├── agent_list.py       # AgentList — dynamic agent rows with status
│           ├── pr_link.py          # PRLink — clickable label → webbrowser
│           ├── project_row.py      # ProjectRow — unattached project display
│           └── plain_session_row.py # PlainSessionRow — plain tmux session
├── daemon/
│   ├── server.py                   # Async Unix socket daemon with event-based push
│   ├── client.py                   # Sync client for daemon communication
│   ├── protocol.py                 # JSON-Lines protocol models (Command, Response, Event)
│   ├── models.py                   # Daemon-internal models (OpenProject, AgentInfo)
│   ├── project_mgr.py             # Project discovery, git operations, PR lookup
│   ├── git_watcher.py             # Per-project filesystem watchers (watchfiles)
│   └── providers/
│       ├── __init__.py             # Provider factory (get_provider)
│       ├── models.py               # ProviderApi protocol + ProviderProject model
│       ├── circuit_breaker.py      # Per-provider circuit breaker (pybreaker)
│       ├── github/
│       │   ├── github.py           # GitHub API: repos, PRs, check runs, reviews
│       │   ├── consumer.py         # clientele HTTP bindings
│       │   └── models.py           # GitHub API response models
│       └── gitlab/
│           ├── gitlab.py           # GitLab API: projects, MRs, pipeline, approvals
│           ├── consumer.py         # clientele HTTP bindings
│           └── models.py           # GitLab API response models
```

**Entry point:** `pyworkon.__main__:run` → `interfaces/__init__.py:init_cli()` → `interfaces/shell/__init__.py:cli()` (Click group)

## Architecture

```text
┌──────────────────┐     ┌──────────────────┐
│   CLI Commands   │     │   TUI Apps       │
│  (Click + shell) │     │  (Dashboard /    │
│                  │     │   Popup)         │
└────────┬─────────┘     └────────┬─────────┘
         │                        │
         │    Unix Socket         │    Unix Socket
         │    (JSON-Lines)        │    (SUBSCRIBE + events)
         │                        │
    ┌────▼────────────────────────▼────┐
    │         Daemon Server            │
    │         (asyncio)                │
    │                                  │
    │  ┌────────────┐ ┌────────────┐   │
    │  │ ProjectMgr │ │  Polling   │   │
    │  │ (diskcache)│ │  + Watch   │   │
    │  └────────────┘ └─────┬──────┘   │
    │                       │          │
    │            ┌──────────┼─────┐    │
    │            ▼          ▼     ▼    │
    │         tmux    watchfiles APIs  │
    └──────────────────────────────────┘
              │          │         │
    ┌─────────▼──┐ ┌─────▼───┐ ┌──▼──────┐
    │  tmux      │ │ .git/   │ │ GitHub/ │
    │  (IPC)     │ │ files   │ │ GitLab  │
    └────────────┘ └─────────┘ └─────────┘
```

### Component Roles

| Component | Role |
|---|---|
| **Daemon** (`daemon/server.py`) | Central async server. Polls tmux sessions and PR data. Watches git state via filesystem watchers. Pushes events to subscribers. |
| **CLI** (`interfaces/shell/`) | User-facing commands built with Click. Communicates with daemon via sync client. |
| **TUI** (`interfaces/tui/`) | Textual apps (Dashboard, Popup) that subscribe to daemon events. Fine-grained widgets with reactive updates. |
| **TmuxManager** (`tmux_mgr.py`) | Wraps tmux subprocess calls: sessions, panes, agent discovery. |
| **ProjectManager** (`daemon/project_mgr.py`) | Discovers local projects, handles git operations and PR lookups via provider APIs. |
| **GitWatcher** (`daemon/git_watcher.py`) | Per-project filesystem watchers using `watchfiles`. Detects branch changes and working tree modifications in real-time. |
| **Providers** (`daemon/providers/`) | GitHub and GitLab API implementations. Fetch repos, PRs/MRs with reviews, CI check runs. |

### Key Design Decisions

- **Unix socket + JSON-Lines** — lightweight IPC, no HTTP overhead. Each line is one JSON message (`Command` or `Response`).
- **Event-based push** — daemon pushes state events to TUI subscribers immediately after changes (agent updates, git watcher events, polling cycles). No polling delay for TUI apps.
- **Filesystem watchers** — `watchfiles` (kqueue on macOS, inotify on Linux) watches `.git/HEAD` for branch changes and the working tree for dirty state. Replaces git subprocess polling.
- **Reactive TUI updates** — TUI only does a full widget rebuild when structure changes (sessions added/removed). Data-only changes update reactive properties on existing widgets.
- **Session-based vs. pane-based projects** — projects can run in their own tmux session (created via tmuxp) or inside an existing tmux pane (tracked via `pane_id` in daemon).
- **diskcache** — persistent cache for the provider project list, survives daemon restarts.

### Protocol

**Client → Daemon** (`Command`):
`LIST_PROJECTS`, `GET_PROJECT`, `OPEN_PROJECT`, `CLOSE_PROJECT`, `CLONE_PROJECT`, `SYNC_PROVIDERS`, `GET_SIDEBAR_STATE`, `AGENT_STATUS`, `AGENT_CLEAR`, `STATUS`, `SHUTDOWN`, `SUBSCRIBE`, `NOTIFY`

**Daemon → Client** (`Response`):
`PROJECTS`, `PROJECT`, `SIDEBAR_STATE`, `PROGRESS`, `OK`, `ERROR`, `STATUS`, `EVENT`

**Event subscription**: `SUBSCRIBE` with `events: ["state", "notification"]` and `full: true`. Daemon pushes `EVENT` responses with `event` field identifying the category.

## Adding a New Provider

1. Create `daemon/providers/<name>/` with `__init__.py`, `models.py`, `consumer.py`, `<name>.py`
2. Implement the `ProviderApi` protocol from `daemon/providers/models.py`:
   - `projects() -> list[ProviderProject]`
   - `get_pr_info(owner_repo, branch, *, head_owner) -> PRInfo | None`
   - Context manager (`__enter__`/`__exit__`)
3. Register in `daemon/providers/__init__.py` (`get_provider` factory)

## Manual Testing Checklist

These tests require a running tmux session, configured providers, and at least one local project in `workspace_dir`.

### 1. Daemon Lifecycle

| # | Steps | Expected |
|---|---|---|
| 1.1 | `pyworkon daemon start` | Prints "Daemon started (PID <n>)." Socket file created at `~/.cache/pyworkon/daemon.sock`. |
| 1.2 | `pyworkon daemon start` (again) | Prints "Daemon is already running." — no duplicate process. |
| 1.3 | `pyworkon daemon status` | Prints "Daemon running (PID <n>)", open projects count, total projects count. |
| 1.4 | `pyworkon daemon stop` | Prints "Daemon stopped." Socket and PID files removed. |
| 1.5 | `pyworkon daemon status` (after stop) | Prints "Daemon is not running." with exit code 1. |
| 1.6 | `pyworkon daemon start --debug` | Runs in foreground with DEBUG-level log output to stderr. Ctrl+C stops it cleanly. |
| 1.7 | `pyworkon daemon notify "hello"` | Toast notification appears in all connected TUI apps (dashboard/popup). |

### 2. Provider Sync & List

| # | Steps | Expected |
|---|---|---|
| 2.1 | `pyworkon provider ls` | Rich table with columns: Name, Type, API, User. Shows all providers from config.yaml. |
| 2.2 | `pyworkon provider sync` | Prints "Fetching projects from <name>..." per provider, then "Done." Projects cached in diskcache. |

### 3. Workon — Session-Based

| # | Steps | Expected |
|---|---|---|
| 3.1 | `pyworkon workon <local_project_id>` | Drops into project directory. Environment variables set: `PYWORKON_PROJECT_ID`, `PYWORKON_PROJECT_NAME`, `PYWORKON_PROJECT_HOME`. |
| 3.2 | `pyworkon workon -c "vim" <project_id>` | Opens vim instead of default shell. |
| 3.3 | `pyworkon workon -t "My Title" <project_id>` | Terminal title set to "My Title". |

### 4. Workon — Pane-Based (in Existing Tmux Pane)

| # | Steps | Expected |
|---|---|---|
| 4.1 | In an existing tmux session, run `pyworkon workon <project_id>` in a pane | Project opens in the current pane. Daemon tracks it via `pane_id`. |
| 4.2 | Open dashboard (`pyworkon dashboard`) | The pane-based project appears in the session list. |
| 4.3 | Exit the workon shell (Ctrl+D or `exit`) | Daemon receives `CLOSE_PROJECT` — project disappears from dashboard. |

### 5. Dashboard

| # | Steps | Expected |
|---|---|---|
| 5.1 | `pyworkon dashboard` | TUI opens showing only pyworkon sessions with full details (branch, dirty, PR title/link, CI checks, agents). |
| 5.2 | Switch branch in a project | Dashboard updates instantly (filesystem watcher). |
| 5.3 | Edit a file in a project | Dirty indicator (pencil icon) appears within ~2 seconds. |
| 5.4 | Set agent status via hook | Agent status updates instantly (event push, no polling delay). |
| 5.5 | PR with failed CI checks | Red background on PR link row, individual failed check names listed as clickable links. |
| 5.6 | Draft PR | "[Draft]" prefix in title, dimmed state icon, no review icon. |
| 5.7 | Enter on a session | Switches to that tmux session. Dashboard stays open. |

### 6. Popup

| # | Steps | Expected |
|---|---|---|
| 6.1 | `pyworkon popup` | TUI opens showing three sections: plain tmux sessions, pyworkon sessions, and local projects. |
| 6.2 | Type to filter | Filter bar appears. Only matching items shown. |
| 6.3 | Select a session and press Enter | Switches to session. Popup exits. |
| 6.4 | Select a local project and press Enter | Creates new tmux session. Popup exits. |
| 6.5 | Ctrl+X on a session | Session killed. Removed from list. |
| 6.6 | Escape (no filter) | Popup exits. |

### 7. Agent Status

| # | Steps | Expected |
|---|---|---|
| 7.1 | `pyworkon agent --status "idle"` | Agent appears in dashboard/popup with moon icon. |
| 7.2 | `pyworkon agent --status "working"` | Agent icon changes to green cog instantly. |
| 7.3 | `pyworkon agent --clear` | Agent disappears from dashboard/popup instantly. |

### 8. PR/MR Display

| # | Steps | Expected |
|---|---|---|
| 8.1 | Open PR, all checks pass | PR title + review icon on line 1, clickable link + green state icon on line 2. |
| 8.2 | Open PR, checks failing | Red ✗ state icon, red background on link row, failed check names listed below. |
| 8.3 | Switch to default branch (main/master) | PR rows disappear (no PR lookup for default branch). |
| 8.4 | Click PR number | Opens PR in browser. |
| 8.5 | Click failed check name | Opens check detail page in browser. |
