from __future__ import annotations

import hashlib
import math
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final, NotRequired, TypedDict

from codescent.core.models import PageOptions
from codescent.core.symbol_formatter import CollapsedSymbol  # noqa: TC001
from codescent.engine.inventory import build_file_inventory
from codescent.engine.search import RankingSignals
from codescent.engine.search.ranking import (
    CHANGED_FILE_BONUS as CHANGED_FILE_BONUS,  # noqa: PLC0414 - re-export for search.
)
from codescent.engine.source_read import read_source_lines
from codescent.services.config import ConfigService
from codescent.services.git import detect_git_state, git_changed_paths
from codescent.services.quality_signals import QualityAnnotation, quality_signals_for
from codescent.storage import RepositoryStorage, initialize_storage

if TYPE_CHECKING:
    from pathlib import Path

DEFAULT_LIMIT: Final = 20
MAX_LIMIT: Final = 20
DEFAULT_LINE_BUDGET: Final = 3
MAX_LINE_BUDGET: Final = 20
# Frecency decay: an access loses half its weight every week, so recent touches
# dominate and stale ones fade toward neutral without ever being deleted.
FRECENCY_HALF_LIFE_SECONDS: Final = 7 * 24 * 60 * 60.0
# Query-history window: a path a query surfaced within this span is "recent".
RECENT_QUERY_WINDOW_SECONDS: Final = 24 * 60 * 60.0


class SearchResultPayload(TypedDict):
    path: str
    score: float
    reasons: tuple[str, ...]
    snippet: str | None
    # Enclosing function/class for content/grep hits (collapse-to-symbol).
    # None for path-only results and module-level matches.
    symbol: CollapsedSymbol | None
    # Inline code-quality annotation: hotspot/dead/duplicate/complex flags
    # plus the duplicate's twin. Absent when the path carries no quality signal.
    quality: NotRequired[QualityAnnotation | None]


class TodoSearchResultPayload(TypedDict):
    path: str
    score: float
    reasons: tuple[str, ...]
    snippet: str
    marker: str
    line: int


class TestSearchResultPayload(TypedDict):
    path: str
    score: float
    reasons: tuple[str, ...]
    snippet: str | None


class SearchPagePayload(TypedDict):
    results: tuple[SearchResultPayload, ...]
    next_cursor: str | None


def searchable_lines(repo_root: Path, relative_path: str) -> list[str]:
    source = read_source_lines(repo_root / relative_path)
    return list(source.lines or ())


def sort_results(
    results: list[SearchResultPayload],
) -> list[SearchResultPayload]:
    return sorted(results, key=lambda result: (-result["score"], result["path"]))


def page_results(
    results: tuple[SearchResultPayload, ...],
    *,
    limit: int,
    offset: int,
) -> SearchPagePayload:
    page = PageOptions(limit=limit, offset=offset)
    selected = results[page.offset : page.offset + page.limit]
    next_offset = page.offset + len(selected)
    next_cursor = str(next_offset) if next_offset < len(results) else None
    return {"results": selected, "next_cursor": next_cursor}


def cursor_to_offset(cursor: str | None) -> int:
    if cursor is None or cursor == "":
        return 0
    try:
        return max(int(cursor), 0)
    except ValueError:
        return 0


def merge_reasons(
    current: tuple[str, ...],
    incoming: tuple[str, ...],
) -> tuple[str, ...]:
    return tuple(dict.fromkeys((*current, *incoming)))


def match_text(line: str, query: str) -> str | None:
    if any(character.isupper() for character in query):
        if query in line:
            return line
        return None
    if query.lower() in line.lower():
        return line
    return None


def snippet(lines: list[str], line_number: int, line_budget: int) -> str:
    budget = min(max(line_budget, 1), MAX_LINE_BUDGET)
    start = max(line_number - (budget // 2), 0)
    selected = lines[start : start + budget]
    return "\n".join(line.strip() for line in selected)


def ranking_signals_for(repo_root: Path) -> RankingSignals:
    """Bundle the personal-first signals one retrieval pass needs.

    Shared by search, ``get_related_files`` and the task brief so every surface
    floats the same recently/frequently-touched and git-modified files.
    """
    frecency, recent_queries = _frecency_pass(repo_root, datetime.now(UTC))
    return RankingSignals(
        changed=changed_files(repo_root),
        git_modified=git_changed_paths(repo_root),
        frecency=frecency,
        recent_queries=recent_queries,
        quality=quality_signals_for(repo_root),
    )


def frecency_scores(
    repo_root: Path,
    *,
    now: datetime | None = None,
) -> dict[str, float]:
    """Time-decayed access score per path; older touches weigh less.

    A missing or corrupt store yields ``{}`` (neutral ranking), never a crash.
    """
    scores, _ = _frecency_pass(repo_root, now or datetime.now(UTC))
    return scores


def recent_query_paths(
    repo_root: Path,
    *,
    now: datetime | None = None,
) -> frozenset[str]:
    """Paths a query surfaced within the recency window (query-history signal)."""
    _, recent = _frecency_pass(repo_root, now or datetime.now(UTC))
    return recent


def record_frecency(
    repo_root: Path,
    query: str,
    paths: tuple[str, ...],
    *,
    now: datetime | None = None,
) -> None:
    if not paths:
        return
    signal = query_signal(query)
    updated_at = (now or datetime.now(UTC)).isoformat()
    state = initialize_storage(repo_root)
    with RepositoryStorage(state).write_transaction() as connection:
        for path in paths:
            _ = connection.execute(
                """
                insert into frecency_signals (path, signal, weight, updated_at)
                values (?, ?, ?, ?)
                """,
                (path, signal, 1.0, updated_at),
            )


def _frecency_pass(
    repo_root: Path,
    reference: datetime,
) -> tuple[dict[str, float], frozenset[str]]:
    # One aged-rows pass feeding both the frecency map and the recent-query set.
    scores: dict[str, float] = {}
    recent: set[str] = set()
    for path, weight, updated_at in _frecency_rows(repo_root):
        recorded = _parse_timestamp(updated_at)
        if recorded is None:
            continue
        age_seconds = (reference - recorded).total_seconds()
        scores[path] = scores.get(path, 0.0) + _decayed_weight(weight, age_seconds)
        if age_seconds <= RECENT_QUERY_WINDOW_SECONDS:
            recent.add(path)
    return scores, frozenset(recent)


def _frecency_rows(repo_root: Path) -> list[tuple[str, float, str]]:
    database_path = repo_root / ".codescent" / "index.sqlite"
    if not database_path.exists():
        return []
    try:
        with closing(sqlite3.connect(database_path)) as connection:
            rows: list[tuple[str, float, str]] = connection.execute(
                "select path, weight, updated_at from frecency_signals",
            ).fetchall()
    except sqlite3.DatabaseError:
        return []
    return rows


def _decayed_weight(weight: float, age_seconds: float) -> float:
    if age_seconds <= 0:
        return weight
    return weight * math.pow(0.5, age_seconds / FRECENCY_HALF_LIFE_SECONDS)


def _parse_timestamp(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def query_signal(query: str) -> str:
    digest = hashlib.sha256(query.encode("utf-8")).hexdigest()
    return f"search:{digest}"


def changed_files(repo_root: Path) -> frozenset[str]:
    return frozenset(changed_file_reasons(repo_root))


def changed_file_reasons(repo_root: Path) -> dict[str, tuple[str, ...]]:
    config = ConfigService(repo_root).load()
    inventory_hashes = {
        item.path: item.hash for item in build_file_inventory(repo_root, config=config)
    }
    inventory_paths = frozenset(inventory_hashes)
    git_paths = git_changed_paths(repo_root) & inventory_paths
    index_paths = index_changed_files(
        repo_root,
        inventory_hashes,
        include_unindexed=not detect_git_state(repo_root).available,
    )
    reasons: dict[str, tuple[str, ...]] = {}
    for path in sorted(git_paths | index_paths):
        path_reasons = ["changed_file"]
        if path in git_paths:
            path_reasons.append("git_changed")
        if path in index_paths:
            path_reasons.append("index_changed")
        reasons[path] = tuple(path_reasons)
    return reasons


def index_changed_files(
    repo_root: Path,
    inventory_hashes: dict[str, str],
    *,
    include_unindexed: bool,
) -> frozenset[str]:
    database_path = repo_root / ".codescent" / "index.sqlite"
    if not database_path.exists():
        return frozenset(inventory_hashes) if include_unindexed else frozenset()
    stored_hashes = stored_hashes_for(database_path)
    if not stored_hashes:
        return frozenset(inventory_hashes) if include_unindexed else frozenset()
    changed = {
        path
        for path, file_hash in inventory_hashes.items()
        if stored_hashes.get(path) != file_hash
    }
    changed.update(path for path in stored_hashes if path not in inventory_hashes)
    return frozenset(changed)


def stored_hashes_for(database_path: Path) -> dict[str, str]:
    try:
        with closing(sqlite3.connect(database_path)) as connection:
            rows: list[tuple[str, str]] = connection.execute(
                "select path, hash from files",
            ).fetchall()
    except sqlite3.DatabaseError:
        return {}
    return dict(rows)
