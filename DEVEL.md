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
```

## Code Structure

```text
pyworkon/
├── __main__.py                     # Entry point, logging setup
├── config.py                       # Config model (pydantic-settings, YAML source)
├── exceptions.py                   # Custom exceptions
├── tmux_mgr.py                     # Tmux subprocess integration (sessions, panes, hooks, agents)
├── defaults/
│   └── tmuxp.yml                   # Default tmuxp layout (main + AI windows)
├── interfaces/
│   ├── __init__.py                 # CLI initialization
│   └── shell/
│       ├── __init__.py             # Click CLI group, PyworkonContext
│       ├── command.py              # Custom Click command classes with completion support
│       ├── common.py               # Utilities (in_shell detection)
│       └── commands/
│           ├── __init__.py         # Re-exports all commands
│           ├── workon.py           # Enter a project (session-based or pane-based)
│           ├── clone.py            # Clone a remote project
│           ├── provider.py         # Provider sync + ls
│           ├── daemon.py           # Daemon start/stop/status
│           ├── shell.py            # Interactive shell with fuzzy completion
│           ├── sidebar.py          # Sidebar, popup, dashboard, sidebar toggle
│           └── agent.py            # Set/clear AI agent status
├── daemon/
│   ├── server.py                   # Async Unix socket daemon with polling loop
│   ├── client.py                   # Sync client for daemon communication
│   ├── protocol.py                 # JSON-Lines protocol models (Command, Response)
│   ├── models.py                   # Daemon-internal models (OpenProject, AgentInfo)
│   ├── project_mgr.py             # Project discovery, git operations, PR lookup
│   └── providers/
│       ├── __init__.py             # Provider factory (get_provider)
│       ├── models.py               # ProviderApi protocol + ProviderProject model
│       ├── github/
│       │   ├── github.py           # GitHub API: repos, PRs, CI status
│       │   ├── consumer.py         # clientele HTTP bindings
│       │   └── models.py           # GitHub API response models
│       └── gitlab/
│           ├── gitlab.py           # GitLab API: projects, MRs, pipeline status
│           ├── consumer.py         # clientele HTTP bindings
│           └── models.py           # GitLab API response models
└── sidebar/
    ├── app.py                      # Textual TUI (SidebarApp, SessionRow, ProjectRow)
    ├── data.py                     # Daemon data collector for sidebar
    ├── models.py                   # Sidebar data models (SessionInfo, PRInfo, AgentInfo)
    └── icons.py                    # Nerd Font / Unicode icon constants
```

**Entry point:** `pyworkon.__main__:run` → `interfaces/__init__.py:init_cli()` → `interfaces/shell/__init__.py:cli()` (Click group)

## Architecture

```text
┌──────────────────┐     ┌──────────────────┐
│   CLI Commands   │     │  Sidebar TUI     │
│  (Click + shell) │     │  (Textual app)   │
└────────┬─────────┘     └────────┬─────────┘
         │                        │
         │    Unix Socket         │    Unix Socket
         │    (JSON-Lines)        │    (polling)
         │                        │
    ┌────▼────────────────────────▼────┐
    │         Daemon Server            │
    │         (asyncio)                │
    │                                  │
    │  ┌────────────┐ ┌────────────┐   │
    │  │ ProjectMgr │ │  Polling   │   │
    │  │ (diskcache)│ │  Loop      │   │
    │  └────────────┘ └─────┬──────┘   │
    │                       │          │
    │            ┌──────────┼─────┐    │
    │            ▼          ▼     ▼    │
    │         tmux        git   APIs   │
    └──────────────────────────────────┘
              │                 │
    ┌─────────▼──────┐  ┌──────▼──────┐
    │  tmux process  │  │  GitHub /   │
    │  (subprocess)  │  │  GitLab API │
    └────────────────┘  └─────────────┘
```

### Component Roles

| Component                                    | Role                                                                                                                                                                                   |
| -------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Daemon** (`daemon/server.py`)              | Central async server. Manages project state, runs the polling loop (tmux sessions, git branches, PR data, provider auto-sync). Communicates via Unix socket using JSON-Lines protocol. |
| **CLI** (`interfaces/shell/`)                | User-facing commands built with Click. Communicates with daemon via sync client.                                                                                                       |
| **TUI** (`sidebar/app.py`)                   | Textual app that polls daemon for state. Three modes: sidebar (continuous), popup (one-shot), dashboard (read-only).                                                                   |
| **TmuxManager** (`tmux_mgr.py`)              | Wraps tmux subprocess calls: sessions, panes, hooks, variables, agent discovery.                                                                                                       |
| **ProjectManager** (`daemon/project_mgr.py`) | Discovers local projects by scanning `workspace_dir/*/*/`, merges with diskcache. Handles git branch detection and PR lookups.                                                         |
| **Providers** (`daemon/providers/`)          | GitHub and GitLab API implementations using clientele. Fetch repos, PRs/MRs, CI status.                                                                                                |

### Key Design Decisions

- **Unix socket + JSON-Lines** — lightweight IPC, no HTTP overhead. Each line is one JSON message (`Command` or `Response`).
- **Polling loop** — daemon polls tmux, git, and provider APIs every `sidebar_refresh_interval` seconds. PR data cached 60s per project. Providers auto-sync every 24h.
- **Reactive TUI updates** — sidebar only does a full widget rebuild when structure changes (sessions added/removed). Data-only changes update reactive properties on existing widgets.
- **Session-based vs. pane-based projects** — projects can run in their own tmux session (created via tmuxp) or inside an existing tmux pane (tracked via `pane_id` in daemon). Both show up in the sidebar.
- **diskcache** — persistent cache for the provider project list, survives daemon restarts.

### Protocol

**Client → Daemon** (`Command`):
`LIST_PROJECTS`, `GET_PROJECT`, `OPEN_PROJECT`, `CLOSE_PROJECT`, `CLONE_PROJECT`, `SYNC_PROVIDERS`, `GET_SIDEBAR_STATE`, `AGENT_STATUS`, `AGENT_CLEAR`, `STATUS`, `SHUTDOWN`

**Daemon → Client** (`Response`):
`PROJECTS`, `PROJECT`, `SIDEBAR_STATE`, `PROGRESS`, `OK`, `ERROR`, `STATUS`

Streaming commands (clone, sync) send multiple `PROGRESS` responses before a final `OK`/`ERROR`.

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

| #   | Steps                                 | Expected                                                                                   |
| --- | ------------------------------------- | ------------------------------------------------------------------------------------------ |
| 1.1 | `pyworkon daemon start`               | Prints "Daemon started (PID <n>)." Socket file created at `~/.cache/pyworkon/daemon.sock`. |
| 1.2 | `pyworkon daemon start` (again)       | Prints "Daemon is already running." — no duplicate process.                                |
| 1.3 | `pyworkon daemon status`              | Prints "Daemon running (PID <n>)", open projects count, total projects count.              |
| 1.4 | `pyworkon daemon stop`                | Prints "Daemon stopped." Socket and PID files removed.                                     |
| 1.5 | `pyworkon daemon status` (after stop) | Prints "Daemon is not running." with exit code 1.                                          |
| 1.6 | `pyworkon daemon start --debug`       | Runs in foreground with DEBUG-level log output to stderr. Ctrl+C stops it cleanly.         |

### 2. Provider Sync & List

| #   | Steps                    | Expected                                                                                           |
| --- | ------------------------ | -------------------------------------------------------------------------------------------------- |
| 2.1 | `pyworkon provider ls`   | Rich table with columns: Name, Type, API, User. Shows all providers from config.yaml.              |
| 2.2 | `pyworkon provider sync` | Prints "Fetching projects from <name>..." per provider, then "Done." Projects cached in diskcache. |

### 3. Workon — Session-Based

| #   | Steps                                                                                 | Expected                                                                                                                                           |
| --- | ------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| 3.1 | `pyworkon workon <local_project_id>`                                                  | Drops into project directory. Environment variables set: `PYWORKON_PROJECT_ID`, `PYWORKON_PROJECT_NAME`, `PYWORKON_PROJECT_HOME` (verify with `env | grep PYWORKON`). |
| 3.2 | `pyworkon workon -c "vim" <project_id>`                                               | Opens vim instead of default shell.                                                                                                                |
| 3.3 | `pyworkon workon -t "My Title" <project_id>`                                          | Terminal title set to "My Title" (visible in tmux status bar or terminal tab).                                                                     |
| 3.4 | Set `workon_pre_command: "echo HELLO"` in config, then `pyworkon workon <project_id>` | "HELLO" printed before shell starts.                                                                                                               |
| 3.5 | `pyworkon workon <non_local_project_id>`                                              | Prints "Project has no local working directory (not cloned yet?)" in red.                                                                          |

### 4. Workon — Pane-Based (in Existing Tmux Pane)

| #   | Steps                                                                     | Expected                                                                                                                    |
| --- | ------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| 4.1 | In an existing tmux session, run `pyworkon workon <project_id>` in a pane | Project opens in the current pane (no new tmux session created). Daemon tracks it via `pane_id`.                            |
| 4.2 | Open sidebar (`pyworkon sidebar`)                                         | The pane-based project appears in the session list with its branch and PR info. Session name is the enclosing tmux session. |
| 4.3 | Exit the workon shell (Ctrl+D or `exit`)                                  | Daemon receives `CLOSE_PROJECT` — project disappears from sidebar on next poll.                                             |

### 5. Clone

| #   | Steps                                | Expected                                                                                  |
| --- | ------------------------------------ | ----------------------------------------------------------------------------------------- |
| 5.1 | `pyworkon clone <remote_project_id>` | Prints "Cloning <id>...", then "Done." Directory created at `workspace_dir/<project_id>`. |
| 5.2 | `pyworkon clone <already_cloned_id>` | Prints "Project directory exists already! Use 'workon' instead!" in red.                  |

### 6. Interactive Shell

| #   | Steps                                      | Expected                                                                      |
| --- | ------------------------------------------ | ----------------------------------------------------------------------------- |
| 6.1 | `pyworkon` (no arguments)                  | Enters interactive shell. Prompt shows configured `prompt_sign` (default: 🖖🏻). |
| 6.2 | Type partial command (e.g., `wor`) and Tab | Fuzzy completion suggests `workon`.                                           |
| 6.3 | `help`                                     | Shows all available commands and special shell commands (help, exit).         |
| 6.4 | `exit`                                     | Prints "Bye!" and returns to normal shell.                                    |
| 6.5 | Type a command, exit, re-enter shell       | Previous command appears in history (auto-suggest).                           |

### 7. Sidebar TUI

| #    | Steps                                                                     | Expected                                                                                                                                                 |
| ---- | ------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 7.1  | `pyworkon sidebar`                                                        | Textual TUI launches. Shows pyworkon sessions with project names. Local projects (without open sessions) shown in a separate section below.              |
| 7.2  | Open a project with a non-default branch in another session               | After refresh interval (default 5s), sidebar shows the branch name next to the session (with  icon).                                                     |
| 7.3  | Open a project with an open PR/MR on the current branch                   | Sidebar shows PR number (e.g., `#42`), state icon (green ● for open), and CI status icon (green ✓ for success, red ✗ for failure, yellow ◷ for pending). |
| 7.4  | Set an agent status: `pyworkon agent --status "🤔"` from a project session | Sidebar shows agent row with name and status emoji (e.g., `claude 🤔`) under the session.                                                                 |
| 7.5  | Change agent status to a different emoji                                  | Sidebar updates agent status on next poll.                                                                                                               |
| 7.6  | `pyworkon agent --clear`                                                  | Agent row disappears from sidebar on next poll.                                                                                                          |
| 7.7  | Type characters in sidebar                                                | Filter bar appears at top (`> <text>_`). Only matching sessions/projects shown.                                                                          |
| 7.8  | Press Escape                                                              | Filter cleared. All items visible again.                                                                                                                 |
| 7.9  | Arrow keys to navigate, Enter to select a session                         | Highlighted row changes. Enter switches tmux to the selected session.                                                                                    |
| 7.10 | Select a local project (no active session) with Enter                     | New tmux session created for the project (via tmuxp), then switched to.                                                                                  |
| 7.11 | Ctrl+X on a session                                                       | Session killed. Removed from sidebar immediately.                                                                                                        |
| 7.12 | Wait without interaction for 2+ refresh intervals                         | Sidebar updates reactively (branch/PR/agent changes reflected without full rebuild, no flicker).                                                         |

### 8. Sidebar Toggle (tmux pane)

| #   | Steps                                      | Expected                                                                               |
| --- | ------------------------------------------ | -------------------------------------------------------------------------------------- |
| 8.1 | `pyworkon sidebar toggle` (in tmux)        | Left pane created with sidebar TUI. Width matches `sidebar_width` config (default 40). |
| 8.2 | Open a new tmux window in the same session | Sidebar pane auto-created in the new window (via `after-new-window` hook).             |
| 8.3 | `pyworkon sidebar toggle` (again)          | Sidebar pane removed. Hook uninstalled.                                                |
| 8.4 | `pyworkon sidebar toggle --no-focus`       | Sidebar pane created but cursor stays in the main pane.                                |

### 9. Popup

| #   | Steps                                  | Expected                                                                                                                                         |
| --- | -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| 9.1 | `pyworkon popup`                       | TUI opens showing three sections: plain tmux sessions (▸ icon), pyworkon sessions (with branch/PR/agent info), and local projects (folder icon). |
| 9.2 | Sessions with PRs/MRs                  | PR number, state icon, and CI status icon visible — same as sidebar.                                                                             |
| 9.3 | Sessions with active agents            | Agent name and status emoji visible — same as sidebar.                                                                                           |
| 9.4 | Select a session and press Enter       | Switches to selected session. Popup exits immediately.                                                                                           |
| 9.5 | Select a local project and press Enter | Creates new tmux session for the project. Popup exits.                                                                                           |
| 9.6 | Press Escape (no filter active)        | Popup exits without selecting anything.                                                                                                          |
| 9.7 | Type to filter, then Escape            | Filter cleared first. Second Escape exits popup.                                                                                                 |

### 10. Dashboard

| #    | Steps                             | Expected                                                                            |
| ---- | --------------------------------- | ----------------------------------------------------------------------------------- |
| 10.1 | `pyworkon dashboard`              | TUI opens showing only pyworkon sessions (no plain sessions, no local projects).    |
| 10.2 | Sessions with PRs/MRs and agents  | PR and agent info displayed — same icons and format as sidebar.                     |
| 10.3 | Type characters, press arrow keys | No interaction — dashboard is read-only. No filter bar, no navigation highlighting. |
| 10.4 | Wait for refresh                  | Dashboard auto-refreshes, showing updated branch/PR/agent data.                     |

### 11. Agent Status

| #    | Steps                                                                   | Expected                                                                                                     |
| ---- | ----------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| 11.1 | `pyworkon agent --status "🔨"` (in a project session)                    | Status set. `pyworkon daemon status` still works. Agent appears in sidebar/popup/dashboard for that session. |
| 11.2 | `pyworkon agent --name "my-agent" --status "⏳"`                         | Agent with custom name "my-agent" shown in sidebar.                                                          |
| 11.3 | `pyworkon agent --status "❓"` (simulating agent asking a question)      | Status emoji changes to ❓ in sidebar/popup/dashboard. Useful to signal that the AI agent needs user input.   |
| 11.4 | `pyworkon agent --clear`                                                | All agents cleared for current session.                                                                      |
| 11.5 | `pyworkon agent --clear --name "my-agent"`                              | Only "my-agent" cleared, other agents remain.                                                                |
| 11.6 | `pyworkon agent --status "🔨"` (outside tmux)                            | Prints "Not inside tmux" to stderr, exit code 1.                                                             |
| 11.7 | Auto-detection: run from a directory with an active Claude Code session | Agent name auto-resolved from `~/.claude/sessions/*.json` matching cwd.                                      |

### 12. PR/MR Display Across Views

| #    | Steps                                                             | Expected                                          |
| ---- | ----------------------------------------------------------------- | ------------------------------------------------- |
| 12.1 | Open project on a branch with an **open** PR                      | Green ● state icon, PR number shown.              |
| 12.2 | Merge the PR, wait for refresh                                    | Purple ● state icon (merged).                     |
| 12.3 | Close PR without merging, wait for refresh                        | Red ● state icon (closed).                        |
| 12.4 | CI passing on PR                                                  | Green ✓ next to PR number.                        |
| 12.5 | CI failing on PR                                                  | Red ✗ next to PR number.                          |
| 12.6 | CI still running                                                  | Yellow ◷ next to PR number.                       |
| 12.7 | Switch to a branch without a PR                                   | PR row disappears from session display.           |
| 12.8 | Verify PR/MR display in **sidebar**, **popup**, and **dashboard** | All three views show identical PR state/CI icons. |

### 13. Fork Support

| #    | Steps                                                              | Expected                                                                |
| ---- | ------------------------------------------------------------------ | ----------------------------------------------------------------------- |
| 13.1 | Open a project that is a fork with an `upstream` remote configured | PR lookup uses the upstream repo's owner/repo for matching.             |
| 13.2 | Push a branch to your fork and open a PR against upstream          | Sidebar shows the PR from the upstream repo, not a self-referencing PR. |

### 14. tmuxp Session Layout

| #    | Steps                                                  | Expected                                                                       |
| ---- | ------------------------------------------------------ | ------------------------------------------------------------------------------ |
| 14.1 | Enter a project without `.tmuxp.yml` via sidebar/popup | New tmux session created with default layout: "main 👨🏼‍💻" window + "AI 🤖" window. |
| 14.2 | Add `.tmuxp.yml` to project root, enter project        | Custom layout from project's `.tmuxp.yml` used instead of default.             |
