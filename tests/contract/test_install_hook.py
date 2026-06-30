"""U6: the ``install-hook`` command and the non-destructive settings merge."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from codescent.cli.main import app
from codescent.services.hook_install import (
    codescent_hook_groups,
    merge_codescent_hooks,
    remove_codescent_hooks,
)

RUNNER = CliRunner()


def test_merge_preserves_unrelated_hooks_and_keys() -> None:
    # Covers R17.
    original = {
        "model": "opus",
        "hooks": {
            "PreToolUse": [
                {"matcher": "Write", "hooks": [{"type": "command", "command": "fmt"}]},
            ],
        },
    }

    merged = merge_codescent_hooks(original, "codescent")

    assert merged["model"] == "opus"  # unrelated top-level key preserved
    pre = merged["hooks"]["PreToolUse"]
    assert {"type": "command", "command": "fmt"} in pre[0]["hooks"]  # unrelated kept
    commands = [h["command"] for group in pre for h in group["hooks"]]
    assert any("hook-augment" in command for command in commands)  # ours added
    assert "PostToolUse" in merged["hooks"]
    assert "SessionStart" in merged["hooks"]
    # The original object is not mutated.
    assert "PostToolUse" not in original["hooks"]


def test_install_then_remove_round_trips() -> None:
    # Covers R18: remove restores the pre-install settings.
    original = {
        "permissions": {"allow": ["Bash"]},
        "hooks": {
            "PreToolUse": [
                {"matcher": "Write", "hooks": [{"type": "command", "command": "fmt"}]},
            ],
        },
    }

    merged = merge_codescent_hooks(original, "codescent")
    restored = remove_codescent_hooks(merged)

    assert restored == original


def test_bash_entries_are_if_gated_and_reindex_is_async() -> None:
    # Covers KTD3/KTD6 wiring.
    groups = codescent_hook_groups("codescent")
    bash_group = next(g for g in groups["PreToolUse"] if g["matcher"] == "Bash")
    assert all("if" in handler for handler in bash_group["hooks"])
    assert {h["if"] for h in bash_group["hooks"]} == {
        "Bash(rg *)",
        "Bash(grep *)",
        "Bash(ripgrep *)",
        "Bash(ag *)",
    }
    reindex_handler = groups["PostToolUse"][0]["hooks"][0]
    assert reindex_handler["async"] is True
    assert "hook-reindex" in reindex_handler["command"]


def test_remove_without_codescent_entries_is_noop() -> None:
    original = {"hooks": {"PreToolUse": [{"matcher": "Edit", "hooks": []}]}}
    assert remove_codescent_hooks(original) == original


def test_install_command_creates_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = RUNNER.invoke(app, ["install-hook"])

    assert result.exit_code == 0
    settings_file = tmp_path / ".claude" / "settings.json"
    assert settings_file.exists()
    settings = json.loads(settings_file.read_text())
    commands = [
        handler["command"]
        for groups in settings["hooks"].values()
        for group in groups
        for handler in group["hooks"]
    ]
    assert any("hook-augment" in command for command in commands)
    assert any("hook-reindex" in command for command in commands)


def test_install_command_global_targets_home(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    result = RUNNER.invoke(app, ["install-hook", "--global"])

    assert result.exit_code == 0
    assert (tmp_path / ".claude" / "settings.json").exists()


def test_install_command_remove_round_trips_on_disk(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    settings_dir = tmp_path / ".claude"
    settings_dir.mkdir()
    original = {"hooks": {"PreToolUse": [{"matcher": "Write", "hooks": []}]}}
    _ = (settings_dir / "settings.json").write_text(json.dumps(original))

    assert RUNNER.invoke(app, ["install-hook"]).exit_code == 0
    assert RUNNER.invoke(app, ["install-hook", "--remove"]).exit_code == 0

    restored = json.loads((settings_dir / "settings.json").read_text())
    assert restored == original
