.PHONY: test lint format typecheck ci daemon-pause daemon-resume

test:
	uv run pytest

lint:
	uv run ruff check

format:
	uv run ruff format

typecheck:
	uv run mypy pyworkon/

ci: lint typecheck test

# Must match LAUNCH_AGENT_LABEL / PLIST_PATH in
# pyworkon/interfaces/shell/commands/daemon.py.
LAUNCHD_LABEL := com.pyworkon.daemon
LAUNCHD_DOMAIN := gui/$(shell id -u)
LAUNCHD_PLIST := $(HOME)/Library/LaunchAgents/$(LAUNCHD_LABEL).plist

# Temporarily stop the launchd-managed prod daemon (e.g. while hacking on
# daemon code locally) without uninstalling its LaunchAgent — it comes back
# automatically on next login/reboot regardless. Use `daemon-resume` to
# bring it back sooner.
daemon-pause:
	launchctl bootout $(LAUNCHD_DOMAIN)/$(LAUNCHD_LABEL) 2>/dev/null || true

daemon-resume:
	launchctl bootstrap $(LAUNCHD_DOMAIN) $(LAUNCHD_PLIST)
