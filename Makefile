.PHONY: test opencode-check daemon-pause daemon-resume

# Must match LAUNCH_AGENT_LABEL / PLIST_PATH in
# pyworkon/interfaces/shell/commands/daemon.py.
LAUNCHD_LABEL := com.pyworkon.daemon
LAUNCHD_DOMAIN := gui/$(shell id -u)
LAUNCHD_PLIST := $(HOME)/Library/LaunchAgents/$(LAUNCHD_LABEL).plist

test:
	uv run ruff check
	uv run ruff format --check
	uv run mypy pyworkon/
	uv run pytest --cov=pyworkon --cov-report=term-missing

format:
	uv run ruff check --fix
	uv run ruff format

opencode-check:
	cd pyworkon/assets/opencode && bun install --frozen-lockfile
	cd pyworkon/assets/opencode && bun run typecheck
	cd pyworkon/assets/opencode && bun run test

# Temporarily stop the launchd-managed prod daemon (e.g. while hacking on
# daemon code locally) without uninstalling its LaunchAgent — it comes back
# automatically on next login/reboot regardless. Use `daemon-resume` to
# bring it back sooner.
daemon-pause:
	launchctl bootout $(LAUNCHD_DOMAIN)/$(LAUNCHD_LABEL) 2>/dev/null || true

daemon-resume:
	launchctl bootstrap $(LAUNCHD_DOMAIN) $(LAUNCHD_PLIST)
