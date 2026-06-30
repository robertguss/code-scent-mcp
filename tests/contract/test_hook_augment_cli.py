"""U4: the ``hook-augment`` PreToolUse entrypoint and its never-block contract.

The command must exit 0 with no stdout on every failure mode, emit valid
PreToolUse ``additionalContext`` JSON on a real search, and never create
``.codescent/`` state in an un-onboarded repo.
"""

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from codescent.cli.main import app
from codescent.services import hook_payload
from codescent.services.repo_index import RepoIndexService

RUNNER = CliRunner()


def _indexed_fixture(tmp_path: Path) -> Path:
    repo = tmp_path / "python-basic"
    _ = shutil.copytree(
        "tests/fixtures/python-basic",
        repo,
        ignore=shutil.ignore_patterns(".codescent"),
    )
    _ = RepoIndexService(repo).index_repo(full=True)
    return repo


def _invoke(payload: object) -> object:
    return RUNNER.invoke(app, ["hook-augment"], input=json.dumps(payload))


def test_non_search_bash_produces_no_output() -> None:
    # Covers AE1: a non-search Bash command yields no additionalContext.
    result = _invoke(
        {"tool_name": "Bash", "tool_input": {"command": "ls -la"}, "cwd": "."},
    )
    assert result.exit_code == 0
    assert result.output.strip() == ""


def test_grep_in_indexed_repo_emits_additional_context(tmp_path: Path) -> None:
    # Covers AE2: structured Grep in an indexed repo emits PreToolUse context.
    repo = _indexed_fixture(tmp_path)
    result = _invoke(
        {
            "tool_name": "Grep",
            "tool_input": {"pattern": "load_config"},
            "cwd": str(repo),
        },
    )
    assert result.exit_code == 0
    emitted = json.loads(result.output)
    assert emitted["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    assert emitted["hookSpecificOutput"]["additionalContext"]
    # Never-block: enrichment carries no permission decision (R11/AE6).
    assert "permissionDecision" not in result.output


def test_unindexed_repo_no_output_and_no_state(tmp_path: Path) -> None:
    # Covers AE4/R16: no index -> no output, and no .codescent/ is created.
    repo = tmp_path / "bare"
    (repo / "src").mkdir(parents=True)
    _ = (repo / "src" / "thing.py").write_text("def load_config():\n    return {}\n")
    result = _invoke(
        {
            "tool_name": "Grep",
            "tool_input": {"pattern": "load_config"},
            "cwd": str(repo),
        },
    )
    assert result.exit_code == 0
    assert result.output.strip() == ""
    assert not (repo / ".codescent").exists()


def test_malformed_and_oversized_stdin_are_silent_noops() -> None:
    # Covers R12/R23.
    for raw in ("not json at all", "", "{partial", "x" * (64 * 1024 + 10)):
        result = RUNNER.invoke(app, ["hook-augment"], input=raw)
        assert result.exit_code == 0
        assert result.output.strip() == ""


def test_internal_error_is_silent_noop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Covers R12: a forced failure past the gate still exits 0 with no output.
    repo = _indexed_fixture(tmp_path)

    def _boom(*_args: object, **_kwargs: object) -> str:
        message = "forced failure"
        raise RuntimeError(message)

    monkeypatch.setattr(hook_payload, "build_payload", _boom)
    result = _invoke(
        {
            "tool_name": "Grep",
            "tool_input": {"pattern": "load_config"},
            "cwd": str(repo),
        },
    )
    assert result.exit_code == 0
    assert result.output.strip() == ""
