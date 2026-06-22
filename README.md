```text
$$$$$$$\            $$\      $$\                     $$\
$$  __$$\           $$ | $\  $$ |                    $$ |
$$ |  $$ |$$\   $$\ $$ |$$$\ $$ | $$$$$$\   $$$$$$\  $$ |  $$\  $$$$$$\  $$$$$$$\
$$$$$$$  |$$ |  $$ |$$ $$ $$\$$ |$$  __$$\ $$  __$$\ $$ | $$  |$$  __$$\ $$  __$$\
$$  ____/ $$ |  $$ |$$$$  _$$$$ |$$ /  $$ |$$ |  \__|$$$$$$  / $$ /  $$ |$$ |  $$ |
$$ |      $$ |  $$ |$$$  / \$$$ |$$ |  $$ |$$ |      $$  _$$<  $$ |  $$ |$$ |  $$ |
$$ |      \$$$$$$$ |$$  /   \$$ |\$$$$$$  |$$ |      $$ | \$$\ \$$$$$$  |$$ |  $$ |
\__|       \____$$ |\__/     \__| \______/ \__|      \__|  \__| \______/ \__|  \__|
          $$\   $$ |
          \$$$$$$  |
           \______/
```

# PyWorkon

[![PyPI version][pypi-version]][pypi-link]
[![PyPI platforms][pypi-platforms]][pypi-link]
[![GitHub Discussion][github-discussions-badge]][github-discussions-link]

PyWorkon is a CLI and TUI tool for managing software development projects across GitHub and GitLab, with deep tmux integration. It provides an interactive shell, a real-time sidebar showing git branches, PR/MR status, CI results, and AI agent activity — all in your terminal.

## 📋 Requirements

- 🐍 Python 3.12+
- 🖥️ [tmux](https://github.com/tmux/tmux) and [tmuxp](https://github.com/tmux-python/tmuxp)
- 🔀 [git](https://git-scm.com/)
- 🔤 A [Nerd Font](https://www.nerdfonts.com/) (for TUI icons)

## 📦 Installation

Install with [uv](https://docs.astral.sh/uv/) (recommended):

```bash
uv tool install pyworkon
```

Or with pip:

```bash
pip install pyworkon
```

## 🔄 Workflow

PyWorkon follows a provider → sync → workon cycle:

1. ⚙️ **Configure providers** — Add your GitHub/GitLab accounts to the config file (see [Configuration](#-configuration))
2. 🚀 **Start the daemon** — `pyworkon daemon start` launches a background service that manages project state
3. 🔄 **Sync projects** — `pyworkon provider sync` fetches all your repositories from configured providers and caches them locally
4. 👨‍💻 **Work on projects** — Use `pyworkon workon <project_id>` to enter a project, or use the sidebar/popup TUI to browse and switch
5. 👁️ **Monitor** — The daemon continuously polls tmux sessions, git branches, and PR/MR status. The sidebar TUI shows everything in real-time.

Projects are identified by their provider-prefixed path: `github/owner/repo` or `gitlab/group/project`. Local projects live under `workspace_dir` following the same directory structure (e.g., `~/workspace/github/owner/repo`).

## 🚀 Quickstart

```bash
# 1. Configure at least one provider (see Configuration section below)
#    Edit the config file and add your GitHub/GitLab credentials

# 2. Start the background daemon
pyworkon daemon start

# 3. Sync your projects from configured providers
pyworkon provider sync

# 4. Clone a project (if not already local)
pyworkon clone github/myuser/myrepo

# 5. Enter a project
pyworkon workon github/myuser/myrepo

# 6. Or launch the interactive sidebar in tmux
pyworkon sidebar toggle
```

## ✨ Features

### 🐚 Interactive Shell

Run `pyworkon` without arguments to enter an interactive shell with fuzzy auto-completion, command history, and auto-suggest.

![Interactive Shell](docs/screenshots/shell.png)

### 📂 Project Management

- **`workon <project_id>`** — Enter a local project. Starts your configured shell (or IDE) with project environment variables set. Works both as a dedicated tmux session and inside an existing tmux pane.
  - `--command, -c` — Custom command to run instead of default shell
  - `--title, -t` — Set terminal title
- **`clone <project_id>`** — Clone a remote repository to your workspace directory with streaming progress.

### 📊 Sidebar TUI

A [Textual](https://github.com/Textualize/textual)-based terminal UI that shows all your active projects at a glance:

- **`sidebar`** — Full sidebar with continuous polling and auto-refresh
- **`sidebar toggle`** — Toggle a sidebar pane in the current tmux window (auto-creates in new windows via tmux hooks)

For each session the sidebar displays:

- 🌿 Current git branch
- 🔀 PR/MR number with state (🟢 open / 🔴 closed / 🟣 merged) and CI status (✅ success / ❌ failure / ⏳ pending)
- 🤖 Active AI agents (e.g. Claude Code) with status emoji

**⌨️ Keyboard shortcuts:** Arrow keys to navigate, Enter to select, Escape to clear filter or exit popup, Ctrl+X to kill a session, type to fuzzy-filter.

![Sidebar TUI](docs/screenshots/sidebar.png)

### 🔍 Popup

One-shot project switcher: shows plain tmux sessions, pyworkon sessions, and local projects — including branch, PR/MR, and agent info. Exits immediately after selection.

![Popup](docs/screenshots/popup.png)

### 📺 Dashboard

Read-only monitoring view of all open pyworkon sessions. Shows branch, PR/MR state, CI status, and active agents — same information as the sidebar, but without interaction (no filtering, navigation, or selection). Useful for a dedicated monitoring pane or screen.

![Dashboard](docs/screenshots/dashboard.png)

### 👻 Background Daemon

The daemon is an async Unix socket server that manages all project state:

- **`daemon start`** — Start in background (or `--debug` for foreground)
- **`daemon stop`** — Graceful shutdown
- **`daemon status`** — Show PID, open/total project count

The daemon automatically:

- 🔍 Discovers tmux sessions with pyworkon projects
- 🌿 Polls git branches for open projects
- 🔀 Fetches PR/MR data (cached 60s per project)
- 🔄 Auto-syncs providers every 24 hours

### 🔌 Providers

Providers connect pyworkon to your Git hosting platforms. They fetch your repository list and provide PR/MR + CI status information.

- **`provider sync`** — Fetch all repositories from configured providers and cache them locally
- **`provider ls`** — List configured providers in a table

**Supported providers:**

| Type     | Platforms                                             | Authentication              | What it fetches                                                                |
| -------- | ----------------------------------------------------- | --------------------------- | ------------------------------------------------------------------------------ |
| `github` | [GitHub.com](https://github.com/), GitHub Enterprise  | Basic auth (username + PAT) | All user repositories, pull requests by branch, combined commit status (CI)    |
| `gitlab` | [GitLab.com](https://gitlab.com/), self-hosted GitLab | Bearer token (PAT)          | All projects with membership, merge requests by source branch, pipeline status |

You can configure multiple providers of the same type (e.g., one for GitHub.com and one for your company's GitHub Enterprise instance). Each provider needs a unique `name` — this name becomes the directory prefix for projects (e.g., `github/owner/repo`, `gitlab-work/group/project`).

🍴 **GitHub fork support:** PR lookup supports forks — if your project has an `upstream` remote, pyworkon looks up PRs against the upstream repository with your fork as the head.

🔀 **GitLab MR lookup:** Searches across opened, merged, and closed states. Pipeline status is read from the MR's associated pipeline.

### 🤖 AI Agent Integration

- **`agent --status <emoji>`** — Set agent status (visible in sidebar/popup/dashboard)
- **`agent --clear`** — Clear agent status
- Auto-detects Claude Code sessions by matching the current working directory

## ⚙️ Configuration

Configuration is stored in a platform-specific location (via [appdirs](https://github.com/ActiveState/appdirs)):

| Platform | Path                                                 |
| -------- | ---------------------------------------------------- |
| 🍎 macOS  | `~/Library/Application Support/pyworkon/config.yaml` |
| 🐧 Linux  | `~/.config/pyworkon/config.yaml`                     |

The file is auto-created on first run. Edit it to add your providers — **without providers, pyworkon has no projects to manage**.

```yaml
prompt_sign: "🖖🏻"
workspace_dir: ~/workspace
workon_command: /bin/zsh           # default: user's login shell
workon_pre_command: ""             # runs before workon_command
sidebar_width: 40
sidebar_refresh_interval: 5        # seconds
debug: false

providers:
  # GitHub.com
  - name: github
    type: github
    api_url: https://api.github.com
    username: your_username
    password: ghp_your_token       # GitHub Personal Access Token

  # GitHub Enterprise
  - name: github-work
    type: github
    api_url: https://github.example.com/api/v3
    username: your_username
    password: ghp_your_token

  # GitLab.com
  - name: gitlab
    type: gitlab
    api_url: https://gitlab.com
    username: your_username         # not used for auth, but required
    password: glpat-your_token     # GitLab Personal Access Token

  # Self-hosted GitLab
  - name: gitlab-work
    type: gitlab
    api_url: https://gitlab.example.com
    username: your_username
    password: glpat-your_token
```

### 🏗️ Per-Project tmux Layout

Place a `.tmuxp.yml` in your project root to override the default tmux layout. The default layout creates two windows: "main 👨🏼‍💻" and "AI 🤖".

## 🛠️ Development

See [DEVEL.md](DEVEL.md) for code structure, architecture, and the manual testing checklist.

## 📄 License

MIT

[github-discussions-badge]: https://img.shields.io/static/v1?label=Discussions&message=Ask&color=blue&logo=github
[github-discussions-link]:  https://github.com/chassing/pyworkon/discussions
[pypi-link]:                https://pypi.org/project/pyworkon/
[pypi-platforms]:           https://img.shields.io/pypi/pyversions/pyworkon
[pypi-version]:             https://badge.fury.io/py/pyworkon.svg
