"""Tests for configuring the default tmux AI pane command."""

from __future__ import annotations

import importlib
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest
import yaml
from click.testing import CliRunner
from pydantic import ValidationError

from pyworkon.config import Config, config
from pyworkon.daemon import project_mgr, tmux_mgr
from pyworkon.daemon.client import DaemonClient
from pyworkon.daemon.project_mgr import Project

workon_cli = importlib.import_module("pyworkon.interfaces.shell.commands.workon")

_COMMANDS = (
    ("opencode", "opencode"),
    ("claude --model sonnet --resume 'a session'", "claude"),
    (
        "codex exec \"Bob's question\" '$HOME; echo nope' 'a \"quoted\" argument'",
        "codex",
    ),
    ("'/Applications/My Agent/bin/opencode' --model 'test model'", "opencode"),
)


@pytest.fixture
def settings_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "config.yaml"
    monkeypatch.setitem(Config.model_config, "yaml_file", path)
    monkeypatch.delenv("PYWORKON_AI_AGENT_COMMAND", raising=False)
    return path


@pytest.fixture
def local_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Project:
    monkeypatch.setattr(config, "workspace_dir", tmp_path)
    project = Project(id="test-project")
    project.project_home.mkdir()
    return project


@pytest.fixture
def tmux_load(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock(
        return_value=subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )
    )
    monkeypatch.setattr(tmux_mgr, "run_cmd", mock)
    return mock


def test_ai_agent_command_defaults_to_opencode(settings_file: Path) -> None:
    settings_file.write_text("{}\n", encoding="utf-8")

    assert Config().ai_agent_command == "opencode"


@pytest.mark.parametrize("command", tuple(item[0] for item in _COMMANDS))
def test_ai_agent_command_loads_from_yaml(settings_file: Path, command: str) -> None:
    settings_file.write_text(
        yaml.safe_dump({"ai_agent_command": command}), encoding="utf-8"
    )

    assert Config().ai_agent_command == command


def test_ai_agent_command_loads_from_environment(
    settings_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings_file.write_text("{}\n", encoding="utf-8")
    monkeypatch.setenv("PYWORKON_AI_AGENT_COMMAND", "claude --model sonnet")

    assert Config().ai_agent_command == "claude --model sonnet"


@pytest.mark.parametrize("command", ["", "  ", "'' --model test", "claude --model '"])
def test_ai_agent_command_rejects_missing_executable_or_unbalanced_quotes(
    settings_file: Path, command: str
) -> None:
    settings_file.write_text(
        yaml.safe_dump({"ai_agent_command": command}), encoding="utf-8"
    )

    with pytest.raises(ValidationError, match="ai_agent_command"):
        Config()


@pytest.mark.parametrize(("command", "title"), _COMMANDS)
async def test_default_tmux_layout_preserves_complete_ai_command(
    local_project: Project,
    tmux_load: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    command: str,
    title: str,
) -> None:
    monkeypatch.setattr(config, "ai_agent_command", command)
    monkeypatch.setenv("PYWORKON_TMUX_AI_AGENT_COMMAND", "stale value")

    await tmux_mgr.TmuxManager().create_session("test-session", local_project)

    tmux_load.assert_awaited_once()
    assert tmux_load.call_args.args == (
        "tmuxp",
        "load",
        "-d",
        "-s",
        "test-session",
        str(tmux_mgr._DEFAULT_TMUXP_CONFIG),
    )
    assert tmux_load.call_args.kwargs["cwd"] == local_project.project_home
    for key, value in local_project.env_vars.items():
        assert tmux_load.call_args.kwargs["env"][key] == value
    assert _ai_pane_arguments(tmux_load) == [
        "pyworkon",
        "workon",
        "--command",
        command,
        "--title",
        title,
        local_project.id,
    ]


async def test_project_tmux_layout_still_overrides_default(
    local_project: Project, tmux_load: AsyncMock
) -> None:
    layout = local_project.project_home / ".tmuxp.yml"
    original = (
        "windows:\n  - window_name: custom\n    panes:\n      - custom-agent --flag\n"
    )
    layout.write_text(original, encoding="utf-8")

    await tmux_mgr.TmuxManager().create_session("test-session", local_project)

    assert tmux_load.call_args.args[-1] == str(layout)
    assert layout.read_text(encoding="utf-8") == original


async def test_ai_command_arguments_survive_tmux_layout_and_project_entry(
    local_project: Project,
    tmux_load: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    arguments = [
        "--model",
        "test model",
        "--resume",
        "Bob's session",
        'Say "hello"',
        "$HOME",
        "$(printf unsafe)",
        "; echo nope",
        r"a\path",
    ]
    command = shlex.join([
        sys.executable,
        "-c",
        "import json, sys; print(json.dumps(sys.argv[1:]))",
        *arguments,
    ])
    monkeypatch.setattr(config, "ai_agent_command", command)
    monkeypatch.setattr(config, "workon_pre_command", "")
    run = Mock()
    monkeypatch.setattr(project_mgr, "run", run)
    client = Mock(spec=DaemonClient)
    client.get_project.return_value = local_project
    monkeypatch.setattr(workon_cli, "require_daemon", lambda: client)

    await tmux_mgr.TmuxManager().create_session("test-session", local_project)
    cli_result = CliRunner().invoke(
        workon_cli.workon, _ai_pane_arguments(tmux_load)[2:]
    )
    assert cli_result.exit_code == 0, cli_result.output
    run.assert_called_once()
    result = subprocess.run(
        run.call_args.args[0],
        shell=True,
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(result.stdout.split("\x07", 1)[1]) == arguments


def _ai_pane_arguments(tmux_load: AsyncMock) -> list[str]:
    layout = yaml.safe_load(
        Path(tmux_load.call_args.args[-1]).read_text(encoding="utf-8")
    )
    with patch.dict(os.environ, tmux_load.call_args.kwargs["env"], clear=True):
        return shlex.split(os.path.expandvars(layout["windows"][1]["panes"][0]))
