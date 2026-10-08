"""Tests for installing bundled agent integrations and skills."""

from __future__ import annotations

import importlib
import importlib.resources
from collections.abc import Iterator
from importlib.resources.abc import Traversable
from pathlib import Path
from zipfile import Path as ZipPath
from zipfile import ZipFile

import pytest
import yaml
from click.testing import CliRunner

from pyworkon.interfaces.shell import PyworkonContext, cli

importlib.import_module("pyworkon.interfaces.shell.commands")


@pytest.fixture
def plugin_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("TMUX", raising=False)
    return tmp_path


def test_opencode_runtime_is_available_as_package_resources() -> None:
    resources = importlib.resources.files("pyworkon.assets").joinpath("opencode")

    assert resources.joinpath("tui.ts").is_file()
    assert resources.joinpath("status.ts").is_file()


@pytest.mark.parametrize("custom_xdg", [False, True])
def test_opencode_install_uses_bundled_resources(
    monkeypatch: pytest.MonkeyPatch, plugin_home: Path, *, custom_xdg: bool
) -> None:
    config_home = plugin_home / ("custom config" if custom_xdg else ".config")
    if custom_xdg:
        monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    config_dir = config_home / "opencode"
    config_dir.mkdir(parents=True)
    config_file = config_dir / "cli.json"
    config_file.write_text('{"terminal":{"title":false}}\n')

    result = CliRunner().invoke(
        cli, ["agentic", "opencode", "install"], obj=PyworkonContext()
    )

    assert result.exit_code == 0, result.output
    destination = config_dir / "plugins" / "pyworkon"
    resources = importlib.resources.files("pyworkon.assets").joinpath("opencode")
    assert sorted(path.name for path in destination.iterdir()) == [
        "status.ts",
        "tui.ts",
    ]
    for filename in ("status.ts", "tui.ts"):
        assert (destination / filename).read_bytes() == resources.joinpath(
            filename
        ).read_bytes()
    assert str(destination) in result.output
    assert config_file.read_text() == '{"terminal":{"title":false}}\n'


def test_opencode_install_refreshes_only_owned_plugin_files(plugin_home: Path) -> None:
    destination = plugin_home / ".config" / "opencode" / "plugins" / "pyworkon"
    destination.mkdir(parents=True)
    (destination / "tui.ts").write_text("old plugin")
    (destination / "notes.txt").write_text("user notes")

    result = CliRunner().invoke(
        cli, ["agentic", "opencode", "install"], obj=PyworkonContext()
    )

    assert result.exit_code == 0, result.output
    assert (destination / "tui.ts").read_bytes() == (
        importlib.resources
        .files("pyworkon.assets")
        .joinpath("opencode", "tui.ts")
        .read_bytes()
    )
    assert (destination / "notes.txt").read_text() == "user notes"


def test_opencode_install_reports_filesystem_errors(plugin_home: Path) -> None:
    (plugin_home / ".config").write_text("not a directory")

    result = CliRunner().invoke(
        cli, ["agentic", "opencode", "install"], obj=PyworkonContext()
    )

    assert result.exit_code == 1
    assert "Error: Could not install OpenCode plugin:" in result.output


@pytest.fixture(params=("directory", "zip"))
def bundled_skills(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> Iterator[Path]:
    assets = tmp_path / "package-assets"
    skills = assets / "skills"
    for name in ("first-skill", "second-skill"):
        directory = skills / name
        directory.mkdir(parents=True)
        (directory / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: Test skill\n---\nInstructions.\n",
            encoding="utf-8",
        )
    references = skills / "first-skill" / "references" / "nested"
    references.mkdir(parents=True)
    (references / "guide.md").write_text("Supporting instructions.\n", encoding="utf-8")
    (skills / "second-skill" / "asset.bin").write_bytes(b"\x00\xff\x01")
    (skills / "second-skill" / "empty-directory").mkdir()
    (skills / "not-a-skill").mkdir()
    (skills / "README.md").write_text("Not a skill.\n", encoding="utf-8")

    def package_files(anchor: str) -> Traversable:
        assert anchor == "pyworkon.assets"
        return assets

    if request.param == "directory":
        monkeypatch.setattr(importlib.resources, "files", package_files)
        yield skills
        return

    archive_path = tmp_path / "package-assets.zip"
    with ZipFile(archive_path, "w") as archive:
        for path in assets.rglob("*"):
            archive.write(path, arcname=str(path.relative_to(assets)))

    with ZipFile(archive_path) as archive:

        def zipped_package_files(anchor: str) -> Traversable:
            assert anchor == "pyworkon.assets"
            return ZipPath(archive)

        monkeypatch.setattr(importlib.resources, "files", zipped_package_files)
        yield skills


def test_agentic_command_structure_replaces_top_level_opencode() -> None:
    context = cli.make_context("pyworkon", [], resilient_parsing=True)
    assert "agentic" in cli.list_commands(context)
    assert "opencode" not in cli.list_commands(context)

    result = CliRunner().invoke(cli, ["agentic", "--help"], obj=PyworkonContext())

    assert result.exit_code == 0, result.output
    assert "opencode" in result.output
    assert "skills-install" in result.output


def test_workspace_skill_is_available_as_package_resources() -> None:
    skill = (
        importlib.resources
        .files("pyworkon.assets")
        .joinpath("skills", "pyworkon-workspace", "SKILL.md")
        .read_text(encoding="utf-8")
    )

    metadata = yaml.safe_load(skill.split("---", 2)[1])
    assert metadata["name"] == "pyworkon-workspace"
    assert metadata["description"]
    assert "~/workspace/<provider-name>/<owner-or-namespace>/<repo>" in skill
    assert "workspace_dir" in skill
    assert "pyworkon provider ls" in skill
    assert "PYWORKON_PROJECT_HOME" in skill


@pytest.mark.parametrize("existing_claude_path", [None, ".claude", ".claude/skills"])
def test_skills_install_copies_all_skills_and_supporting_files(
    plugin_home: Path, bundled_skills: Path, existing_claude_path: str | None
) -> None:
    if existing_claude_path:
        (plugin_home / existing_claude_path).mkdir(parents=True)

    result = CliRunner().invoke(
        cli, ["agentic", "skills-install"], obj=PyworkonContext()
    )

    assert result.exit_code == 0, result.output
    destinations = [plugin_home / ".agents" / "skills"]
    if existing_claude_path == ".claude/skills":
        destinations.append(plugin_home / ".claude" / "skills")
    else:
        assert not (plugin_home / ".claude" / "skills").exists()
    for destination in destinations:
        assert sorted(path.name for path in destination.iterdir()) == [
            "first-skill",
            "second-skill",
        ]
        for name in ("first-skill", "second-skill"):
            for path in (bundled_skills / name).rglob("*"):
                installed = destination / path.relative_to(bundled_skills)
                if path.is_file():
                    assert installed.read_bytes() == path.read_bytes()
                else:
                    assert installed.is_dir()
            assert str(destination / name) in result.output


def test_skills_install_refreshes_bundled_files_and_preserves_unrelated_files(
    plugin_home: Path, bundled_skills: Path
) -> None:
    destinations = [
        plugin_home / ".agents" / "skills",
        plugin_home / ".claude" / "skills",
    ]
    for destination in destinations:
        (destination / "first-skill").mkdir(parents=True)
        (destination / "first-skill" / "SKILL.md").write_text(
            "Old skill.", encoding="utf-8"
        )
        (destination / "first-skill" / "notes.txt").write_text(
            "User notes.", encoding="utf-8"
        )
        (destination / "unrelated-skill").mkdir()
        (destination / "unrelated-skill" / "SKILL.md").write_text(
            "Unrelated skill.", encoding="utf-8"
        )

    for attempt in range(2):
        result = CliRunner().invoke(
            cli, ["agentic", "skills-install"], obj=PyworkonContext()
        )
        assert result.exit_code == 0, f"Attempt {attempt}: {result.output}"

    for destination in destinations:
        assert (destination / "first-skill" / "SKILL.md").read_bytes() == (
            bundled_skills / "first-skill" / "SKILL.md"
        ).read_bytes()
        assert (destination / "first-skill" / "notes.txt").read_text(
            encoding="utf-8"
        ) == "User notes."
        assert (destination / "unrelated-skill" / "SKILL.md").read_text(
            encoding="utf-8"
        ) == "Unrelated skill."


def test_skills_install_supports_a_shared_claude_destination(
    plugin_home: Path, bundled_skills: Path
) -> None:
    shared = plugin_home / ".agents" / "skills"
    shared.mkdir(parents=True)
    (plugin_home / ".claude").mkdir()
    (plugin_home / ".claude" / "skills").symlink_to(shared, target_is_directory=True)

    result = CliRunner().invoke(
        cli, ["agentic", "skills-install"], obj=PyworkonContext()
    )

    assert result.exit_code == 0, result.output
    assert (shared / "second-skill" / "asset.bin").read_bytes() == (
        bundled_skills / "second-skill" / "asset.bin"
    ).read_bytes()


@pytest.mark.parametrize("symlink_kind", ["skill-directory", "skill-file"])
@pytest.mark.usefixtures("bundled_skills")
def test_skills_install_does_not_overwrite_symlinked_skill_content(
    plugin_home: Path, symlink_kind: str
) -> None:
    outside = plugin_home / "outside"
    outside.mkdir()
    original = outside / "SKILL.md"
    original.write_text("User-owned content.", encoding="utf-8")
    destination = plugin_home / ".agents" / "skills" / "first-skill"
    if symlink_kind == "skill-directory":
        destination.parent.mkdir(parents=True)
        destination.symlink_to(outside, target_is_directory=True)
    else:
        destination.mkdir(parents=True)
        (destination / "SKILL.md").symlink_to(original)

    result = CliRunner().invoke(
        cli, ["agentic", "skills-install"], obj=PyworkonContext()
    )

    assert result.exit_code == 1
    assert "Error: Could not install agent skills:" in result.output
    assert "symlink" in result.output
    assert original.read_text(encoding="utf-8") == "User-owned content."


@pytest.mark.usefixtures("bundled_skills")
def test_skills_install_reports_filesystem_errors(plugin_home: Path) -> None:
    (plugin_home / ".agents").write_text("Not a directory.", encoding="utf-8")

    result = CliRunner().invoke(
        cli, ["agentic", "skills-install"], obj=PyworkonContext()
    )

    assert result.exit_code == 1
    assert "Error: Could not install agent skills:" in result.output


def test_skills_install_reports_an_empty_package_skill_directory(
    plugin_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assets = plugin_home / "empty-package-assets"
    (assets / "skills").mkdir(parents=True)

    def package_files(anchor: str) -> Traversable:
        assert anchor == "pyworkon.assets"
        return assets

    monkeypatch.setattr(importlib.resources, "files", package_files)

    result = CliRunner().invoke(
        cli, ["agentic", "skills-install"], obj=PyworkonContext()
    )

    assert result.exit_code == 1
    assert "No bundled agent skills found" in result.output
    assert not (plugin_home / ".agents").exists()
