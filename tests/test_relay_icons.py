"""Tests for the relay dashboard's icon reuse of interfaces/tui/icons.py."""

from __future__ import annotations

import subprocess
import sys

from pyworkon.interfaces.relay.icons import DASHBOARD_ICONS
from pyworkon.interfaces.tui import icons as tui_icons


def test_dashboard_icons_match_tui_glyphs() -> None:
    assert DASHBOARD_ICONS["branch"] == tui_icons.ICON_BRANCH
    assert DASHBOARD_ICONS["pr"] == tui_icons.ICON_PR
    assert DASHBOARD_ICONS["agent"] == tui_icons.ICON_AGENT
    assert DASHBOARD_ICONS["github"] == tui_icons.ICON_GITHUB
    assert DASHBOARD_ICONS["gitlab"] == tui_icons.ICON_GITLAB
    assert DASHBOARD_ICONS["agentIdle"] == tui_icons.AGENT_IDLE
    assert DASHBOARD_ICONS["agentWaiting"] == tui_icons.AGENT_WAITING
    assert DASHBOARD_ICONS["reviewRequest"] == tui_icons.ICON_REVIEW_REQUEST


def test_dashboard_icons_strip_rich_markup() -> None:
    # Source constants wrap the glyph in Rich color tags; the web dashboard
    # colors via CSS instead, so no "[" / "]" should survive.
    for value in DASHBOARD_ICONS.values():
        assert "[" not in value
        assert "]" not in value


def test_dashboard_icons_are_single_glyphs() -> None:
    for key, value in DASHBOARD_ICONS.items():
        assert len(value) == 1, f"{key!r} should be a single glyph, got {value!r}"


def test_importing_relay_icons_does_not_pull_in_pyworkon_config() -> None:
    # pyworkon.config runs pwd.getpwnam()/mkdir() at import time, which can
    # crash the relay container under an arbitrary non-root UID. Run in a
    # subprocess so this module's own import doesn't poison later tests'
    # sys.modules cache.
    check_script = (
        "import sys; import pyworkon.interfaces.relay.icons; "
        "assert 'pyworkon.config' not in sys.modules; "
        "assert 'pyworkon.daemon.protocol' not in sys.modules"
    )
    result = subprocess.run(
        [sys.executable, "-c", check_script],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
