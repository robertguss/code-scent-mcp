from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from codescent.core.models import PageOptions, ProjectConfig
from codescent.engine.inventory import build_file_inventory
from codescent.engine.source_read import read_source_lines
from codescent.services.search_support import (
    TestSearchResultPayload,
    TodoSearchResultPayload,
    match_text,
    merge_reasons,
)

if TYPE_CHECKING:
    from pathlib import Path

TODO_PATTERN: Final = re.compile(r"\b(TODO|FIXME|HACK)\b:?\s*(.*)")
TEST_FILE_BONUS: Final = 40.0
TEST_NAME_BONUS: Final = 35.0
TEST_CONTENT_BONUS: Final = 20.0


@dataclass(frozen=True, slots=True)
class TestSearchRequest:
    query: str
    path: str | None
    symbol: str | None
    finding_id: str | None
    limit: int


def search_todos_for_repo(
    repo_root: Path,
    query: str,
    *,
    limit: int,
    config: ProjectConfig | None = None,
) -> tuple[TodoSearchResultPayload, ...]:
    page = PageOptions(limit=limit)
    project_config = config or ProjectConfig()
    results: list[TodoSearchResultPayload] = []
    for item in build_file_inventory(repo_root, config=project_config):
        source = read_source_lines(repo_root / item.path)
        if source.lines is None:
            continue
        lines = list(source.lines)
        for line_number, line in enumerate(lines, start=1):
            marker_match = TODO_PATTERN.search(line)
            if marker_match is None:
                continue
            if _todo_query_misses(item.path, line, query):
                continue
            marker = marker_match.group(1)
            results.append(
                {
                    "path": item.path,
                    "score": todo_score(item.path, line, marker, query),
                    "reasons": ("todo_marker", f"marker:{marker}"),
                    "snippet": line.strip(),
                    "marker": marker,
                    "line": line_number,
                },
            )
    return tuple(sort_todo_results(results)[: page.limit])


def search_tests_for_repo(
    repo_root: Path,
    request: TestSearchRequest,
    *,
    config: ProjectConfig | None = None,
) -> tuple[TestSearchResultPayload, ...]:
    page = PageOptions(limit=request.limit)
    project_config = config or ProjectConfig()
    terms = test_search_terms(request)
    results: list[TestSearchResultPayload] = []
    for item in build_file_inventory(repo_root, config=project_config):
        if not is_test_path(item.path):
            continue
        source = read_source_lines(repo_root / item.path)
        if source.lines is None:
            continue
        lines = list(source.lines)
        score, reasons, matched_snippet = rank_test_file(item.path, lines, terms)
        if score <= 0:
            continue
        results.append(
            {
                "path": item.path,
                "score": score,
                "reasons": reasons,
                "snippet": matched_snippet,
            },
        )
    return tuple(sort_test_results(results)[: page.limit])


def _todo_query_misses(path: str, line: str, query: str) -> bool:
    return bool(
        query and match_text(path, query) is None and match_text(line, query) is None
    )


def sort_todo_results(
    results: list[TodoSearchResultPayload],
) -> list[TodoSearchResultPayload]:
    return sorted(
        results,
        key=lambda result: (-result["score"], result["path"], result["line"]),
    )


def sort_test_results(
    results: list[TestSearchResultPayload],
) -> list[TestSearchResultPayload]:
    return sorted(results, key=lambda result: (-result["score"], result["path"]))


def todo_score(path: str, line: str, marker: str, query: str) -> float:
    marker_boost = {
        "FIXME": 12.0,
        "TODO": 10.0,
        "HACK": 8.0,
    }[marker]
    score = 80.0 + marker_boost
    if query and match_text(path, query) is not None:
        score += 15.0
    if query and match_text(line, query) is not None:
        score += 20.0
    return score


def is_test_path(path: str) -> bool:
    name = path.rsplit("/", maxsplit=1)[-1]
    return (
        path.startswith("tests/")
        or name.startswith("test_")
        or name.endswith("_test.py")
    )


def test_search_terms(request: TestSearchRequest) -> tuple[str, ...]:
    terms: list[str] = []
    for value in (request.query, request.path, request.symbol, request.finding_id):
        if value is None:
            continue
        terms.extend(split_test_terms(value))
    return tuple(dict.fromkeys(term for term in terms if term))


def split_test_terms(value: str) -> tuple[str, ...]:
    normalized = value.replace("\\", "/").replace(":", "/")
    parts = re.split(r"[^A-Za-z0-9_]+", normalized)
    terms: list[str] = []
    for part in parts:
        if not part or part in {"src", "tests", "test", "py", "python"}:
            continue
        terms.append(part)
        if "_" in part:
            terms.extend(piece for piece in part.split("_") if piece)
    return tuple(terms)


def rank_test_file(
    path: str,
    lines: list[str],
    terms: tuple[str, ...],
) -> tuple[float, tuple[str, ...], str | None]:
    score = TEST_FILE_BONUS
    reasons: list[str] = ["likely_test"]
    matched_snippet: str | None = None
    if not terms:
        return score, tuple(reasons), matched_snippet

    content = "\n".join(lines)
    for term in terms:
        if match_text(path, term) is not None:
            score += TEST_NAME_BONUS
            reasons.append("path_match")
        line_match = first_matching_line(lines, term)
        if line_match is not None:
            score += TEST_CONTENT_BONUS
            reasons.append("content_match")
            if matched_snippet is None:
                matched_snippet = line_match
        if match_text(content, term) is not None and looks_like_symbol(term):
            score += TEST_CONTENT_BONUS
            reasons.append("symbol_match")
    return score, merge_reasons(tuple(reasons), ()), matched_snippet


def first_matching_line(lines: list[str], term: str) -> str | None:
    for line in lines:
        if match_text(line, term) is not None:
            return line.strip()
    return None


def looks_like_symbol(term: str) -> bool:
    return "_" in term or term.isidentifier()
