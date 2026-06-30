"""Frecency + git-status + query-history ranking (plan unit U12 / bead P3.1).

The personal-first edge: rank by what THIS developer actually touches. These
tests cover the three signals end to end -- time-decayed frecency, git working-
tree status, and recent query history -- plus their explainable reasons and the
wiring into search and ``get_related_files``. The clock is injected (never
``time.sleep``) so decay is deterministic.
"""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from codescent.services.context import ContextService
from codescent.services.git import git_changed_paths
from codescent.services.search import SearchService
from codescent.services.search_support import (
    frecency_scores,
    ranking_signals_for,
    recent_query_paths,
    record_frecency,
)

if TYPE_CHECKING:
    from pathlib import Path

_EPOCH = datetime(2026, 6, 1, tzinfo=UTC)


def _run_git(repo: Path, *args: str) -> None:
    _ = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _git_repo_with_file(tmp_path: Path, relative: str, body: str) -> Path:
    repo = tmp_path / "repo"
    source = repo / relative
    source.parent.mkdir(parents=True)
    _ = source.write_text(body)
    _run_git(repo, "init")
    _run_git(repo, "config", "user.email", "codescent@example.test")
    _run_git(repo, "config", "user.name", "CodeScent Test")
    _run_git(repo, "add", relative)
    _run_git(repo, "commit", "-m", "initial")
    return repo


def test_record_frecency_increments_score(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    record_frecency(repo, "alpha", ("src/a.py",))
    first = frecency_scores(repo)["src/a.py"]
    record_frecency(repo, "alpha", ("src/a.py",))
    second = frecency_scores(repo)["src/a.py"]

    assert first > 0
    assert second > first


def test_frecency_decays_so_old_access_scores_lower(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    record_frecency(repo, "q", ("old.py",), now=_EPOCH)
    record_frecency(repo, "q", ("new.py",), now=_EPOCH + timedelta(days=21))
    scores = frecency_scores(repo, now=_EPOCH + timedelta(days=21))

    # Same single access each; the older one has decayed below the recent one.
    assert scores["new.py"] > scores["old.py"] > 0


def test_recent_query_window_is_query_history(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    record_frecency(repo, "q", ("fresh.py",), now=_EPOCH)
    record_frecency(repo, "q", ("stale.py",), now=_EPOCH - timedelta(days=3))
    recent = recent_query_paths(repo, now=_EPOCH)

    assert "fresh.py" in recent
    assert "stale.py" not in recent


def test_touched_path_outranks_equally_relevant_untouched(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    _ = (repo / "src" / "alpha_target.py").write_text("marker = 1\n")
    _ = (repo / "src" / "beta_target.py").write_text("marker = 1\n")
    service = SearchService(repo)

    cold = service.search_files("target", limit=2)
    _ = service.search_files("beta_target", limit=1)
    _ = service.search_files("beta_target", limit=1)
    warm = service.search_files("target", limit=2)

    # Cold: equal text relevance, alphabetical tie-break.
    assert cold[0]["path"] == "src/alpha_target.py"
    # Warm: the touched path floats above the untouched one, with a named reason.
    assert warm[0]["path"] == "src/beta_target.py"
    assert "frecency" in warm[0]["reasons"]
    assert "recent_query" in warm[0]["reasons"]


def test_git_modified_path_floats_up_with_reason(tmp_path: Path) -> None:
    repo = _git_repo_with_file(tmp_path, "src/app.py", "def run() -> None:\n    pass\n")
    _ = (repo / "src" / "app.py").write_text("def run() -> None:\n    return\n")

    results = SearchService(repo).search_files("app", limit=1)

    assert results[0]["path"] == "src/app.py"
    assert "git_modified" in results[0]["reasons"]


def test_store_lives_under_codescent_and_is_invisible_to_git(tmp_path: Path) -> None:
    repo = _git_repo_with_file(tmp_path, "src/app.py", "x = 1\n")
    _ = (repo / ".gitignore").write_text(".codescent/\n")

    record_frecency(repo, "q", ("src/app.py",))

    assert (repo / ".codescent" / "index.sqlite").exists()
    # The per-user store never reaches the git-status ranking signal.
    assert not any(path.startswith(".codescent") for path in git_changed_paths(repo))


def test_missing_and_corrupt_store_degrade_to_neutral(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    # Missing store: neutral, no crash.
    assert frecency_scores(repo) == {}
    assert recent_query_paths(repo) == frozenset()
    assert ranking_signals_for(repo).frecency == {}

    # Corrupt store: still neutral, no crash.
    (repo / ".codescent").mkdir()
    _ = (repo / ".codescent" / "index.sqlite").write_bytes(b"not a database")
    assert frecency_scores(repo) == {}
    assert recent_query_paths(repo) == frozenset()


def test_get_related_files_floats_touched_sibling(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    _ = (repo / "src" / "a.py").write_text("def a() -> int:\n    return 1\n")
    _ = (repo / "src" / "b.py").write_text("def b() -> int:\n    return 2\n")
    _ = (repo / "src" / "c.py").write_text("def c() -> int:\n    return 3\n")
    context = ContextService(repo)

    # Index first, then touch a sibling, so the frecency row survives indexing.
    _ = context.get_related_files("src/a.py")
    record_frecency(repo, "c work", ("src/c.py",))
    payload = context.get_related_files("src/a.py")

    rows = {row["path"]: row for row in payload["results"]}
    assert "src/c.py" in rows
    assert "recent_query" in rows["src/c.py"]["reasons"]
    assert "frecency" in rows["src/c.py"]["reasons"]

    # The touched sibling outranks the equally-related untouched one.
    order = [row["path"] for row in payload["results"]]
    assert order.index("src/c.py") < order.index("src/b.py")
