"""Collapse-to-symbol behavior for content search (plan unit U4 / bead P1.1).

Each content/grep match line is mapped to its enclosing function/class and the
symbol's signature is returned instead of the bare line. Python is AST-exact;
TS/JS goes through the regex pack and is labelled heuristic. Module-level matches
degrade to a bounded raw line.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import typer

from codescent.core.symbol_formatter import MAX_COLLAPSE_LINE_CHARS
from codescent.core.token_estimate import estimate_tokens
from codescent.services.search import SearchService

if TYPE_CHECKING:
    from pathlib import Path


def _write(repo: Path, relative: str, text: str) -> None:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(text)


def test_python_match_collapses_to_enclosing_function(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(
        repo,
        "src/mod.py",
        """def handle_request(payload: str) -> str:
    result = needle_marker(payload)
    return result
""",
    )

    results = SearchService(repo).search_content("needle_marker", limit=20)

    assert len(results) == 1
    result = results[0]
    assert result["path"] == "src/mod.py"
    assert result["snippet"] == "def handle_request(payload: str) -> str:"
    assert "collapsed_to_symbol" in result["reasons"]
    symbol = result["symbol"]
    assert symbol is not None
    assert symbol["name"] == "handle_request"
    assert symbol["kind"] == "function"
    assert symbol["confidence"] == "exact"


def test_method_match_collapses_to_innermost_method_not_class(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(
        repo,
        "src/repo.py",
        """class Repository:
    def save(self, value: int) -> None:
        stored = persist_marker(value)
        return stored
""",
    )

    results = SearchService(repo).search_content("persist_marker", limit=20)

    assert len(results) == 1
    symbol = results[0]["symbol"]
    assert symbol is not None
    # The innermost enclosing symbol is the method, not the surrounding class.
    assert symbol["name"] == "save"
    assert symbol["kind"] == "method"
    assert results[0]["snippet"] == "def save(self, value: int) -> None:"


def test_nested_def_resolves_to_innermost_symbol(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(
        repo,
        "src/nested.py",
        """def outer_fn() -> int:
    def inner_fn() -> int:
        return deepest_marker
    return inner_fn()
""",
    )

    results = SearchService(repo).search_content("deepest_marker", limit=20)

    assert len(results) == 1
    symbol = results[0]["symbol"]
    assert symbol is not None
    assert symbol["name"] == "inner_fn"
    assert results[0]["snippet"] == "def inner_fn() -> int:"


def test_import_only_lines_suppressed_once_symbol_shown(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(
        repo,
        "src/imports.py",
        """import osmarker

def consume() -> str:
    return osmarker_value()
""",
    )

    results = SearchService(repo).search_content("osmarker", limit=20)

    # The `import osmarker` line also matches but is dropped because a real
    # definition (consume) is shown for the file.
    assert len(results) == 1
    symbol = results[0]["symbol"]
    assert symbol is not None
    assert symbol["name"] == "consume"
    assert all("import" not in (result["snippet"] or "") for result in results)


def test_overlong_matched_line_truncated_to_bound(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    long_value = "z" * 400
    _write(repo, "src/long.py", f"data_marker = '{long_value}'\n")

    results = SearchService(repo).search_content("data_marker", limit=20)

    assert len(results) == 1
    snippet = results[0]["snippet"]
    assert snippet is not None
    assert len(snippet) <= MAX_COLLAPSE_LINE_CHARS
    assert snippet.endswith("...")


def test_module_level_match_degrades_to_bounded_raw_line(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(repo, "src/top.py", "simple_marker = 42\n")

    results = SearchService(repo).search_content("simple_marker", limit=20)

    assert len(results) == 1
    result = results[0]
    # No enclosing symbol at module level: graceful degrade to a bounded line.
    assert result["symbol"] is None
    assert result["snippet"] == "simple_marker = 42"
    assert "module_level" in result["reasons"]


def test_typescript_match_collapses_with_heuristic_confidence(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(
        repo,
        "src/widget.ts",
        """export function renderWidget(): string {
  const value = collectToken();
  return value;
}
""",
    )

    results = SearchService(repo).search_content("collectToken", limit=20)

    assert len(results) == 1
    result = results[0]
    assert result["path"] == "src/widget.ts"
    symbol = result["symbol"]
    assert symbol is not None
    assert symbol["name"] == "renderWidget"
    assert symbol["confidence"] == "heuristic"
    assert (result["snippet"] or "").startswith("export function renderWidget")


def test_collapsed_output_uses_fewer_tokens_than_raw_lines(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    body = "\n".join(
        f"    step_{i} = transform_marker(step_{i - 1})" for i in range(1, 9)
    )
    _write(
        repo,
        "src/pipeline.py",
        f"""def run_pipeline(seed: str) -> str:
    step_0 = seed
{body}
    return step_8
""",
    )

    service = SearchService(repo)
    collapsed = service.search_content("transform_marker", limit=20)
    raw = service.search_content("transform_marker", limit=20, expand=True)

    collapsed_tokens = estimate_tokens(json.dumps(collapsed, default=str))
    raw_tokens = estimate_tokens(json.dumps(raw, default=str))
    tokens = f"collapsed_tokens={collapsed_tokens} raw_tokens={raw_tokens}"
    counts = f"collapsed={len(collapsed)} raw={len(raw)}"
    typer.echo(f"collapse e2e: {tokens} ({counts})")

    # Eight matches in one function collapse to a single symbol hit.
    assert len(collapsed) == 1
    assert len(raw) == 8
    collapsed_symbol = collapsed[0]["symbol"]
    assert collapsed_symbol is not None
    assert collapsed_symbol["match_count"] == 8
    assert collapsed_tokens < raw_tokens
