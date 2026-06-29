"""Output-mode shaping for the bounded search/grep tools (plan unit U5).

`output_mode` is orthogonal to U4's `expand`: `expand` controls how content is
rendered (collapsed signature vs full lines), while `output_mode` controls which
shape is returned (content, files, count, or usage). Each mode reuses the same
bounded result window, so none can grow past the configured limit.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from codescent.mcp.search_tools import (
    multi_search_content,
    search_content,
    search_files,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path


def _write(repo: Path, relative: str, text: str) -> None:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(text)


def _rows(results: tuple[object, ...]) -> tuple[Mapping[str, object], ...]:
    return tuple(cast("Mapping[str, object]", item) for item in results)


def _single_marker_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    _write(
        repo,
        "src/mod.py",
        """def handle(payload: str) -> str:
    result = needle_marker(payload)
    return result
""",
    )
    return repo


def _many_marker_repo(tmp_path: Path, *, files: int) -> Path:
    repo = tmp_path / "repo"
    for index in range(files):
        _write(
            repo,
            f"src/mod_{index:02d}.py",
            f"def handle_{index:02d}() -> int:\n    return needle_marker()\n",
        )
    return repo


def test_content_mode_is_collapse_aware_default(tmp_path: Path) -> None:
    repo = _single_marker_repo(tmp_path)

    payload = search_content("needle_marker", repo=str(repo), limit=20)
    rows = _rows(payload["results"])

    assert payload["output_mode"] == "content"
    assert payload["count"] is None
    assert len(rows) == 1
    assert rows[0]["path"] == "src/mod.py"
    assert rows[0]["snippet"] == "def handle(payload: str) -> str:"
    symbol = rows[0]["symbol"]
    assert symbol is not None
    assert cast("Mapping[str, object]", symbol)["name"] == "handle"
    assert "collapsed_to_symbol" in cast("tuple[str, ...]", rows[0]["reasons"])


def test_files_mode_returns_distinct_paths_only(tmp_path: Path) -> None:
    repo = _single_marker_repo(tmp_path)

    payload = search_content(
        "needle_marker", repo=str(repo), limit=20, output_mode="files"
    )
    rows = _rows(payload["results"])

    assert payload["output_mode"] == "files"
    assert payload["count"] is None
    assert rows == ({"path": "src/mod.py"},)
    # files mode is paths only: no snippet/symbol leakage.
    assert all(set(row) == {"path"} for row in rows)


def test_count_mode_returns_tally_not_content(tmp_path: Path) -> None:
    repo = _single_marker_repo(tmp_path)

    payload = search_content(
        "needle_marker", repo=str(repo), limit=20, output_mode="count"
    )
    count = payload["count"]

    assert payload["output_mode"] == "count"
    assert payload["results"] == ()
    assert count is not None
    assert count["total_matches"] == 1
    assert count["file_count"] == 1


def test_usage_mode_returns_minimal_match_sites(tmp_path: Path) -> None:
    repo = _single_marker_repo(tmp_path)

    payload = search_content(
        "needle_marker", repo=str(repo), limit=20, output_mode="usage"
    )
    rows = _rows(payload["results"])

    assert payload["output_mode"] == "usage"
    assert payload["count"] is None
    assert rows == ({"path": "src/mod.py", "line": 1, "symbol": "handle"},)


def test_each_mode_respects_the_bound(tmp_path: Path) -> None:
    repo = _many_marker_repo(tmp_path, files=8)
    limit = 3

    content = search_content("needle_marker", repo=str(repo), limit=limit)
    files = search_content(
        "needle_marker", repo=str(repo), limit=limit, output_mode="files"
    )
    usage = search_content(
        "needle_marker", repo=str(repo), limit=limit, output_mode="usage"
    )
    count = search_content(
        "needle_marker", repo=str(repo), limit=limit, output_mode="count"
    )

    assert len(content["results"]) == limit
    assert len(files["results"]) == limit
    assert len(usage["results"]) == limit
    count_tally = count["count"]
    assert count_tally is not None
    assert count_tally["file_count"] == limit
    assert count_tally["total_matches"] == limit


def test_output_mode_composes_with_expand(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(
        repo,
        "src/pipeline.py",
        """def pipeline(seed: str) -> str:
    first = transform_marker(seed)
    second = transform_marker(first)
    return second
""",
    )

    collapsed = search_content("transform_marker", repo=str(repo), limit=20)
    expanded = search_content("transform_marker", repo=str(repo), limit=20, expand=True)

    collapsed_rows = _rows(collapsed["results"])
    expanded_rows = _rows(expanded["results"])

    # content default collapses the two hits to a single symbol.
    assert len(collapsed_rows) == 1
    collapsed_symbol = collapsed_rows[0]["symbol"]
    assert collapsed_symbol is not None
    assert cast("Mapping[str, object]", collapsed_symbol)["match_count"] == 2

    # content + expand yields the full per-line snippets, one per hit.
    assert len(expanded_rows) == 2
    assert all(row["symbol"] is None for row in expanded_rows)
    assert all(
        "transform_marker" in cast("str", row["snippet"]) for row in expanded_rows
    )


def test_invalid_output_mode_degrades_to_content(tmp_path: Path) -> None:
    repo = _single_marker_repo(tmp_path)

    payload = search_content(
        "needle_marker", repo=str(repo), limit=20, output_mode="not-a-real-mode"
    )
    rows = _rows(payload["results"])

    # Defensive parsing: an unknown mode falls back to content, never crashes.
    assert payload["output_mode"] == "content"
    assert payload["count"] is None
    assert len(rows) == 1
    assert rows[0]["snippet"] == "def handle(payload: str) -> str:"
    assert rows[0]["symbol"] is not None


def test_multi_search_content_supports_modes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(repo, "src/billing.py", "def bill() -> int:\n    return needle_marker()\n")
    _write(repo, "src/payroll.py", "def pay() -> int:\n    return other_marker()\n")

    content = multi_search_content(("needle_marker", "other_marker"), repo=str(repo))
    files = multi_search_content(
        ("needle_marker", "other_marker"), repo=str(repo), output_mode="files"
    )
    count = multi_search_content(
        ("needle_marker", "other_marker"), repo=str(repo), output_mode="count"
    )

    assert content["output_mode"] == "content"
    assert {row["path"] for row in _rows(files["results"])} == {
        "src/billing.py",
        "src/payroll.py",
    }
    assert all(set(row) == {"path"} for row in _rows(files["results"]))
    count_tally = count["count"]
    assert count_tally is not None
    assert count_tally["file_count"] == 2


def test_search_files_supports_files_and_count_modes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(repo, "src/config.py", "value = 1\n")
    _write(repo, "src/configure.py", "value = 2\n")

    files = search_files("config", repo=str(repo), limit=20, output_mode="files")
    count = search_files("config", repo=str(repo), limit=20, output_mode="count")
    # usage is meaningless for path search and degrades to content.
    usage = search_files("config", repo=str(repo), limit=20, output_mode="usage")

    file_rows = _rows(files["results"])
    assert files["output_mode"] == "files"
    assert {row["path"] for row in file_rows} == {"src/config.py", "src/configure.py"}
    assert all(set(row) == {"path"} for row in file_rows)
    count_tally = count["count"]
    assert count_tally is not None
    assert count_tally["file_count"] == 2
    assert usage["output_mode"] == "content"
