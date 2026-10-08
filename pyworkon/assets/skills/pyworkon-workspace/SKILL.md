---
name: pyworkon-workspace
description: >-
  Locate and work with repositories in a pyworkon-managed workspace. Use this
  skill when finding local or sibling repositories, translating repository URLs
  or pyworkon project IDs into paths, working under ~/workspace, or using
  pyworkon project and agent-integration commands. Follow the provider/owner/repo
  directory structure instead of searching the whole filesystem.
---

# Pyworkon Workspace

## Directory structure

Pyworkon's default workspace root is `~/workspace`. Repositories follow:

```text
~/workspace/<provider-name>/<owner-or-namespace>/<repo>
```

The project ID is the repository's path relative to the workspace root:

```text
<provider-name>/<owner-or-namespace>/<repo>
```

For example:

```text
~/workspace/
├── github/
│   ├── acme/api/
│   └── alice/api/
├── github-work/platform/service/
└── gitlab-work/team/service/
```

`github/acme/api` and `github/alice/api` are different projects even though their
repository names match. The provider directory is the configured provider's
**name**, not necessarily its type or hostname: `github-work` can be a GitHub
provider, and `gitlab-work` can be a GitLab provider. Do not hardcode a provider
directory from a repository URL alone.

## Resolve a repository before searching

1. Check the current directory and, when available, `PYWORKON_PROJECT_ID`,
   `PYWORKON_PROJECT_NAME`, and `PYWORKON_PROJECT_HOME`. The home variable points
   to the current project's repository directory, not the workspace root.
   Verify that inherited environment values still match the checkout in use.
2. Use the configured `workspace_dir` if it differs from `~/workspace`. Pyworkon
   reads YAML configuration from:
   - macOS: `~/Library/Application Support/pyworkon/config.yaml`
   - Linux: `~/.config/pyworkon/config.yaml`
     The `PYWORKON_WORKSPACE_DIR` environment variable is also a configuration
     source, but a value set in YAML takes precedence. Inspect only the fields
     needed for locating repositories; configuration also contains provider
     passwords and tokens, which must not be printed or included in responses.
3. Run `pyworkon provider ls` when the configured provider names are unclear.
   This read-only command lists names, types, API URLs, and usernames without
   exposing credentials.
4. Build the exact candidate path from the workspace root and project ID.
   Check that directory first. If the owner or provider is unknown, list only
   the relevant provider/owner directories. Ask when multiple checkouts match.
5. Search file contents inside the resolved repository. Do not run an
   unrestricted recursive search over `/`, the home directory, or every
   workspace provider when a narrower path is available.
6. Read the repository's `AGENTS.md` and `CLAUDE.md`, including relevant
   ancestor and nested instructions, before changing files.

For example, a request to inspect `acme/api` on the configured `github` provider
starts at `~/workspace/github/acme/api`, not an arbitrary directory named `api`.
If `workspace_dir` is `/srv/projects`, the same project is instead located at
`/srv/projects/github/acme/api`.

## Forks and project operations

- Check `git remote -v` in the resolved checkout before choosing an upstream
  repository. The workspace owner may identify a personal fork; do not assume
  `origin` is the canonical repository or silently switch to another checkout.
- Use `pyworkon clone <project_id>` to clone a known remote project only when
  requested. It creates the repository under the configured workspace root.
- `pyworkon workon <project_id>` enters a local project and launches the
  configured shell or command. It is not a read-only lookup command; do not
  launch an interactive shell just to inspect files.
- Project operations use the pyworkon daemon. Check `pyworkon daemon status`
  when needed, but do not start, stop, or otherwise change it without approval.

## Agent integrations

```sh
pyworkon agentic opencode install
pyworkon agentic skills-install
```

The first command installs the bundled OpenCode CLI plugin. The second installs
all bundled skills into `~/.agents/skills` and also into `~/.claude/skills` when
that directory already exists. Both commands write global files; run them only
when installation or refresh is requested.

The default tmux AI pane uses the `ai_agent_command` configuration setting
(default: `opencode`). It accepts options and shell-quoted arguments. Changing
it requires a daemon restart and affects newly created sessions, not existing
ones. A project-local `.tmuxp.yml` overrides the default layout.
