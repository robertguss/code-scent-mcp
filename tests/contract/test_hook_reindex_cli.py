"""U5: the ``hook-reindex`` SessionStart / PostToolUse entrypoint.

It must reindex incrementally when an index exists, no-op (and create no state)
when one does not (R16), and never surface an error to the agent.
"""

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from codescent.cli.main import app
from codescent.services.repo_index import RepoIndexService
from codescent.services.search_support import stored_hashes_for

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


def _invoke(cwd: str) -> object:
    return RUNNER.invoke(app, ["hook-reindex"], input=json.dumps({"cwd": cwd}))


def test_reindex_unindexed_repo_no_op_no_state(tmp_path: Path) -> None:
    # Covers R16: no index -> no work, no .codescent/ created.
    repo = tmp_path / "bare"
    (repo / "src").mkdir(parents=True)
    _ = (repo / "src" / "thing.py").write_text("def f():\n    return 1\n")

    result = _invoke(str(repo))

    assert result.exit_code == 0
    assert not (repo / ".codescent").exists()


def test_reindex_picks_up_edits(tmp_path: Path) -> None:
    # Covers R14/R15: an incremental reindex updates the stored hash of an edit.
    repo = _indexed_fixture(tmp_path)
    database = repo / ".codescent" / "index.sqlite"
    target = "src/acme_tasks/config.py"
    before = stored_hashes_for(database)[target]

    edited = repo / target
    addition = "\n\ndef brand_new_symbol():\n    return 1\n"
    _ = edited.write_text(edited.read_text() + addition)
    result = _invoke(str(repo))

    assert result.exit_code == 0
    assert stored_hashes_for(database)[target] != before


def test_reindex_is_idempotent(tmp_path: Path) -> None:
    repo = _indexed_fixture(tmp_path)

    first = _invoke(str(repo))
    second = _invoke(str(repo))

    assert first.exit_code == 0
    assert second.exit_code == 0


def test_reindex_swallows_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Covers background-safety: a failing reindex still exits 0.
    repo = _indexed_fixture(tmp_path)

    def _boom(self: object, *, full: bool = False) -> object:
        message = "forced reindex failure"
        raise RuntimeError(message)

    monkeypatch.setattr(RepoIndexService, "index_repo", _boom)
    result = _invoke(str(repo))

    assert result.exit_code == 0
