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

[![CI][ci-badge]][ci-link]
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

- 🔌 **Multi-provider** — GitHub + GitLab (including self-hosted) with automatic project sync
- 📊 **Real-time sidebar** — git branches, PR/MR status, CI results, AI agent activity
- 🔍 **Popup project switcher** — fuzzy filter, instant session switching
- 👻 **Async daemon** — Unix socket server, concurrent polling, zero blocking
- 🔒 **Circuit breaker** — auto-pauses unreachable providers (VPN down), auto-recovers
- 🔔 **Push notifications** — daemon events as Textual toast notifications
- 🤖 **AI agent tracking** — Claude Code hook integration with per-agent status
- 🖥️ **tmux native** — sessions, panes, tmuxp layouts, sidebar toggle per window

---

### 🐚 Interactive Shell

Run `pyworkon` without arguments to enter an interactive shell with fuzzy auto-completion, command history, and auto-suggest.

![Interactive Shell](docs/screenshots/shell.png)

### 📂 Project Management

- **`workon <project_id>`** — Enter a local project. Starts your configured shell (or IDE) with project environment variables set. Works both as a dedicated tmux session and inside an existing tmux pane.
  - `--command, -c` — Custom command to run instead of default shell
  - `--title, -t` — Set terminal title
- **`clone <project_id>`** — Clone a remote repository to your workspace directory with streaming progress.

### 📺 Dashboard

A [Textual](https://github.com/Textualize/textual)-based terminal UI that shows all your active sessions at a glance with real-time updates:

- **`dashboard`** — Full-detail monitoring of all open sessions

For each session the dashboard displays:

- 🌿 Current git branch with dirty indicator (uncommitted changes)
- 🔀 PR/MR title, clickable link, state (🟢 open / 🔴 closed / 🟣 merged), review status (✅ approved / ❌ changes requested)
- 🔧 CI check status with clickable links to individual failed checks
- 🤖 Active AI agents (e.g. Claude Code) with status icons (idle/working/waiting)

**⌨️ Keyboard shortcuts:** Arrow keys to navigate, Enter to select session, Escape/Ctrl+Q to quit.

![Dashboard](docs/screenshots/dashboard.png)

### 🔍 Popup

One-shot project switcher: shows plain tmux sessions, pyworkon sessions, and local projects. Compact view (no CI check links). Exits immediately after selection.

**⌨️ Keyboard shortcuts:** Type to fuzzy-filter, Enter to select, Escape to clear filter or exit, Ctrl+X to kill a session.

![Popup](docs/screenshots/popup.png)

### 👻 Background Daemon

The daemon is an async Unix socket server that manages all project state:

- **`daemon start`** — Start in background (or `--foreground` for init systems, `--debug` for debug logging)
- **`daemon stop`** — Graceful shutdown
- **`daemon status`** — Show PID, open/total project count
- **`daemon notify "message"`** — Send a toast notification to all connected TUI apps

#### Auto-start at login

**macOS (launchd):**

```bash
cat > ~/Library/LaunchAgents/com.pyworkon.daemon.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.pyworkon.daemon</string>
    <key>ProgramArguments</key>
    <array>
        <string>/path/to/pyworkon</string>
        <string>daemon</string>
        <string>start</string>
        <string>--foreground</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
</dict>
</plist>
EOF
# Adjust /path/to/pyworkon (find it with: which pyworkon)
launchctl load ~/Library/LaunchAgents/com.pyworkon.daemon.plist
```

**Linux (systemd):**

```bash
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/pyworkon-daemon.service << 'EOF'
[Unit]
Description=PyWorkon Daemon

[Service]
ExecStart=/path/to/pyworkon daemon start --foreground
Restart=on-failure

[Install]
WantedBy=default.target
EOF
# Adjust /path/to/pyworkon (find it with: which pyworkon)
systemctl --user enable --now pyworkon-daemon
```

The daemon automatically:

- 🔍 Discovers tmux sessions with pyworkon projects
- 🌿 Watches git branches and dirty state in real-time via filesystem watchers (`watchfiles`)
- 🔀 Fetches PR/MR data with review status and CI checks (cached 60s per project)
- 📡 Pushes state updates to all connected TUI apps instantly (event-based, no polling delay)
- 🔄 Auto-syncs providers every 24 hours
- 🔌 Circuit breaker per provider — when a provider is unreachable (e.g., VPN down), polling pauses automatically and resumes when connectivity returns

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

- **`agent --status <status>`** — Set agent status: `idle`, `working`, `waiting` (visible in sidebar/popup/dashboard, mapped to Nerd Font icons)
- **`agent --clear`** — Clear agent status
- Auto-detects Claude Code sessions by matching the current working directory

**Claude Code hooks** (in `~/.claude/settings.json`):

```json
{
  "hooks": {
    "SessionStart": [{"hooks": [{"command": "pyworkon agent --status idle", "type": "command"}]}],
    "UserPromptSubmit": [{"hooks": [{"command": "pyworkon agent --status working", "type": "command"}]}],
    "Stop": [{"hooks": [{"command": "pyworkon agent --status idle", "type": "command"}]}],
    "Elicitation": [{"hooks": [{"command": "pyworkon agent --status waiting", "type": "command"}]}],
    "PermissionRequest": [{"hooks": [{"command": "pyworkon agent --status waiting", "type": "command"}]}],
    "SessionEnd": [{"hooks": [{"command": "pyworkon agent --clear", "type": "command"}]}]
  }
}
```

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
sidebar_refresh_interval: 5        # seconds (daemon poll interval for tmux/PR data)
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
[ci-badge]:                 https://github.com/chassing/pyworkon/actions/workflows/ci.yml/badge.svg
[ci-link]:                  https://github.com/chassing/pyworkon/actions/workflows/ci.yml
