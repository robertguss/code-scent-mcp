"""U1: read-only ranked-match retrieval for the grep-injection hook.

The hook path must rank like ``SearchService`` but write nothing (R10/AE5) and
expose the match line number (R7) that ``SearchResultPayload`` drops.
"""

import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

from codescent.services.hook_retrieval import ranked_matches
from codescent.services.repo_index import RepoIndexService


def _copy_fixture(tmp_path: Path) -> Path:
    repo = tmp_path / "python-basic"
    _ = shutil.copytree(
        "tests/fixtures/python-basic",
        repo,
        ignore=shutil.ignore_patterns(".codescent"),
    )
    _ = RepoIndexService(repo).index_repo(full=True)
    return repo


def _frecency_row_count(repo: Path) -> int:
    database = repo / ".codescent" / "index.sqlite"
    with closing(sqlite3.connect(database)) as connection:
        (count,) = connection.execute(
            "select count(*) from frecency_signals",
        ).fetchone()
    return int(count)


def test_ranked_matches_returns_symbol_and_line(tmp_path: Path) -> None:
    repo = _copy_fixture(tmp_path)

    matches = ranked_matches(repo, "load_config", limit=5)

    assert matches, "expected at least one match for load_config"
    top = matches[0]
    assert top.path == "src/acme_tasks/config.py"
    assert top.line >= 1
    assert top.symbol_name == "load_config"


def test_ranked_matches_is_read_only(tmp_path: Path) -> None:
    # Covers AE5: ranking the hook payload must not record frecency.
    repo = _copy_fixture(tmp_path)
    before = _frecency_row_count(repo)

    _ = ranked_matches(repo, "load_config", limit=5)

    assert _frecency_row_count(repo) == before


def test_ranked_matches_respects_limit(tmp_path: Path) -> None:
    repo = _copy_fixture(tmp_path)

    matches = ranked_matches(repo, "def", limit=3)

    assert len(matches) <= 3


def test_ranked_matches_empty_on_no_hits(tmp_path: Path) -> None:
    repo = _copy_fixture(tmp_path)

    assert ranked_matches(repo, "zzz_no_such_symbol_zzz", limit=5) == ()


def test_ranked_matches_flags_git_modified(tmp_path: Path) -> None:
    # git_modified is derived read-only from RankingSignals; without a git repo
    # the flag is simply False, but the field must always be present.
    repo = _copy_fixture(tmp_path)

    matches = ranked_matches(repo, "load_config", limit=5)

    assert all(isinstance(match.git_modified, bool) for match in matches)
