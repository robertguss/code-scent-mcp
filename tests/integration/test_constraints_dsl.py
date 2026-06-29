"""Constraints DSL prefilter (plan unit U9 / bead P2.2).

Covers each constraint kind parsing + filtering, AND-composition, graceful
degradation of malformed tokens, the get_schema surface, and the back-compat
default. Git and mtime state are injected/controlled so the assertions stay
deterministic without depending on real working-tree or wall-clock state.
"""

from __future__ import annotations

import os
from pathlib import Path

from codescent.engine.search.constraints import (
    CONSTRAINT_KINDS,
    GitPaths,
    parse_constraints,
)
from codescent.engine.search.constraints_filter import filter_paths
from codescent.mcp.schema import build_schema
from codescent.services.search import SearchService

_PATHS = (
    "src/acme/config.py",
    "src/acme/cli.py",
    "src/acme/cli.ts",
    "tests/test_config.py",
    "README.md",
)


def _filter(
    constraints: str,
    *,
    git: GitPaths | None = None,
) -> tuple[str, ...]:
    return filter_paths(_PATHS, parse_constraints(constraints), Path(), git=git)


def test_glob_keeps_only_matching_extension() -> None:
    kept = _filter("*.py")

    assert set(kept) == {
        "src/acme/config.py",
        "src/acme/cli.py",
        "tests/test_config.py",
    }
    assert "src/acme/cli.ts" not in kept


def test_path_prefix_keeps_only_subtree() -> None:
    kept = _filter("src/")

    assert set(kept) == {"src/acme/config.py", "src/acme/cli.py", "src/acme/cli.ts"}
    assert all(path.startswith("src/") for path in kept)


def test_negation_drops_matching_paths() -> None:
    kept = _filter("!tests/")

    assert "tests/test_config.py" not in kept
    assert "src/acme/config.py" in kept


def test_negation_glob_drops_matching_extension() -> None:
    kept = _filter("!*.ts")

    assert "src/acme/cli.ts" not in kept
    assert "src/acme/cli.py" in kept


def test_git_modified_keeps_only_changed_paths() -> None:
    git = GitPaths(modified=frozenset({"src/acme/cli.py"}))

    kept = _filter("git:modified", git=git)

    assert kept == ("src/acme/cli.py",)


def test_git_untracked_keeps_only_untracked_paths() -> None:
    git = GitPaths(untracked=frozenset({"src/acme/config.py"}))

    kept = _filter("git:untracked", git=git)

    assert kept == ("src/acme/config.py",)


def test_combined_constraints_and_together() -> None:
    # src/ AND *.py -> only python files under src (the .ts and the test drop out).
    kept = _filter("src/ *.py")

    assert set(kept) == {"src/acme/config.py", "src/acme/cli.py"}


def test_size_constraint_filters_by_file_size(tmp_path: Path) -> None:
    small = tmp_path / "small.py"
    large = tmp_path / "large.py"
    _ = small.write_text("x = 1\n")
    _ = large.write_text("y = 2\n" * 1000)
    paths = ("small.py", "large.py")

    under = filter_paths(paths, parse_constraints("size:<1kb"), tmp_path)
    over = filter_paths(paths, parse_constraints("size:>1kb"), tmp_path)

    assert under == ("small.py",)
    assert over == ("large.py",)


def test_time_constraint_filters_by_mtime(tmp_path: Path) -> None:
    recent = tmp_path / "recent.py"
    stale = tmp_path / "stale.py"
    _ = recent.write_text("a = 1\n")
    _ = stale.write_text("b = 2\n")
    now = 1_000_000.0
    day = 86400.0
    os.utime(recent, (now - day, now - day))  # 1 day old
    os.utime(stale, (now - 30 * day, now - 30 * day))  # 30 days old
    paths = ("recent.py", "stale.py")

    within = filter_paths(paths, parse_constraints("mtime:<7d"), tmp_path, now=now)
    older = filter_paths(paths, parse_constraints("mtime:>7d"), tmp_path, now=now)

    assert within == ("recent.py",)
    assert older == ("stale.py",)


def test_malformed_token_is_ignored_not_raised() -> None:
    # An unknown scheme and a malformed size both degrade to no-op tokens, so the
    # only effective constraint is the valid prefix.
    kept = _filter("src/ bogus:value size:notasize")

    assert set(kept) == {"src/acme/config.py", "src/acme/cli.py", "src/acme/cli.ts"}


def test_empty_constraints_is_a_noop() -> None:
    assert _filter("") == _PATHS
    assert _filter("   ") == _PATHS


def test_get_schema_advertises_constraint_kinds() -> None:
    payload = build_schema()

    assert "constraints" in payload
    tokens = {kind["token"] for kind in payload["constraints"]}
    assert {"git:modified", "*.py", "!tests/", "src/", "size:<10kb", "mtime:<7d"} <= (
        tokens
    )
    assert len(payload["constraints"]) == len(CONSTRAINT_KINDS)
    for kind in payload["constraints"]:
        assert kind["description"]


def test_search_content_prefilters_before_bound(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "lib").mkdir(parents=True)
    _ = (repo / "src" / "a.py").write_text("marker = 1\n")
    _ = (repo / "src" / "b.py").write_text("marker = 2\n")
    _ = (repo / "lib" / "c.py").write_text("marker = 3\n")
    service = SearchService(repo)

    unconstrained = service.search_content("marker", limit=20)
    scoped = service.search_content("marker", limit=20, constraints="src/")

    assert {result["path"] for result in unconstrained} == {
        "src/a.py",
        "src/b.py",
        "lib/c.py",
    }
    assert {result["path"] for result in scoped} == {"src/a.py", "src/b.py"}


def test_search_files_prefilters_candidates(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "lib").mkdir(parents=True)
    _ = (repo / "src" / "target.py").write_text("x = 1\n")
    _ = (repo / "lib" / "target.py").write_text("y = 2\n")
    service = SearchService(repo)

    scoped = service.search_files("target", limit=20, constraints="lib/")

    assert tuple(result["path"] for result in scoped) == ("lib/target.py",)


def test_multi_search_content_respects_constraints(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "tests").mkdir(parents=True)
    _ = (repo / "src" / "app.py").write_text("alpha = 1\nbeta = 2\n")
    _ = (repo / "tests" / "test_app.py").write_text("alpha = 1\nbeta = 2\n")
    service = SearchService(repo)

    scoped = service.multi_search_content(("alpha", "beta"), constraints="!tests/")

    assert tuple(result["path"] for result in scoped) == ("src/app.py",)
