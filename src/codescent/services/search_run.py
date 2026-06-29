"""Backend-aware retrieval: route through fff when present, native floor else.

``SearchService.search_files`` / ``search_content`` delegate the candidate-
generation step here. When ``backend`` is a present-and-healthy fff engine that
exposes the needed capability, fff supplies the raw candidates (fuzzy paths /
grep hits) and CodeScent re-applies its existing bounding, collapse-to-symbol
and freshness shaping on the way out, so the result envelope is byte-identical
to the native path. When ``backend`` is ``None`` (the common case: fff absent),
lacks the capability, or errors, the native rapidfuzz floor runs unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from codescent.engine.inventory import build_file_inventory
from codescent.engine.search import apply_signals, rank_path
from codescent.engine.search.constraints import GitPaths, parse_constraints
from codescent.engine.search.constraints_filter import build_predicate
from codescent.services.fff_backend import probe_capabilities
from codescent.services.git import git_changed_paths, git_untracked_paths
from codescent.services.search_collapse import collapsed_results, content_signals
from codescent.services.search_support import (
    SearchResultPayload,
    match_text,
    searchable_lines,
    snippet,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from codescent.core.models import IndexedFile, ProjectConfig
    from codescent.engine.search import RankingSignals
    from codescent.engine.search.constraints import ConstraintSet
    from codescent.services.fff_backend import FffClient

_FFF_BASE_SCORE: Final = 100.0


@dataclass(frozen=True, slots=True)
class RetrievalContext:
    """The repo signals every retrieval path needs, passed around as one unit."""

    repo_root: Path
    config: ProjectConfig
    # Personal-first ranking signals (frecency, git-status, query-history).
    signals: RankingSignals
    # Constraints DSL prefilter (U9): keep(path) gate applied to candidates
    # BEFORE ranking/collapse and the result bound. None means no constraint.
    allow: Callable[[str], bool] | None = None


def build_constraint_filter(
    repo_root: Path,
    constraints: str,
) -> Callable[[str], bool] | None:
    """Resolve a ``constraints`` string into a path prefilter, or None if empty."""
    parsed = parse_constraints(constraints)
    if parsed.is_empty:
        return None
    return build_predicate(parsed, repo_root, git=_resolve_git_paths(repo_root, parsed))


def _resolve_git_paths(repo_root: Path, parsed: ConstraintSet) -> GitPaths | None:
    if not parsed.git_kinds:
        return None
    empty: frozenset[str] = frozenset()
    modified = git_changed_paths(repo_root) if "modified" in parsed.git_kinds else empty
    untracked = (
        git_untracked_paths(repo_root) if "untracked" in parsed.git_kinds else empty
    )
    return GitPaths(modified=modified, untracked=untracked)


def file_results(
    context: RetrievalContext,
    query: str,
    *,
    backend: FffClient | None,
) -> list[SearchResultPayload]:
    """Path search: fff ``fuzzy_paths`` when available, native rapidfuzz else."""
    if backend is not None:
        routed = _fff_path_results(backend, context, query)
        if routed is not None:
            return routed
    return _native_file_results(context, query)


def content_results(
    context: RetrievalContext,
    query: str,
    *,
    backend: FffClient | None,
    line_budget: int,
    expand: bool,
) -> list[SearchResultPayload]:
    """Content search: fff ``grep_content`` when available, native scan else."""
    items = build_file_inventory(context.repo_root, config=context.config)
    if context.allow is not None:
        items = tuple(item for item in items if context.allow(item.path))
    if backend is not None:
        routed = _fff_content_results(
            backend,
            context,
            query,
            items_by_path={item.path: item for item in items},
            line_budget=line_budget,
            expand=expand,
        )
        if routed is not None:
            return routed
    return _native_content_results(
        context,
        items,
        query,
        line_budget=line_budget,
        expand=expand,
    )


def _native_file_results(
    context: RetrievalContext,
    query: str,
) -> list[SearchResultPayload]:
    results: list[SearchResultPayload] = []
    for item in build_file_inventory(context.repo_root, config=context.config):
        if context.allow is not None and not context.allow(item.path):
            continue
        rank = rank_path(item.path, query)
        if rank is None:
            continue
        score, reasons = apply_signals(
            item.path,
            rank.score,
            rank.reasons,
            context.signals,
        )
        results.append(
            {
                "path": item.path,
                "score": score,
                "reasons": reasons,
                "snippet": None,
                "symbol": None,
            },
        )
    return results


def _native_content_results(
    context: RetrievalContext,
    items: tuple[IndexedFile, ...],
    query: str,
    *,
    line_budget: int,
    expand: bool,
) -> list[SearchResultPayload]:
    results: list[SearchResultPayload] = []
    for item in items:
        lines = searchable_lines(context.repo_root, item.path)
        match_indexes = tuple(
            index
            for index, line in enumerate(lines)
            if match_text(line, query) is not None
        )
        if not match_indexes:
            continue
        signals = content_signals(item.path, context.signals)
        results.extend(
            _shape_content_matches(
                context,
                item,
                lines,
                match_indexes,
                signals=signals,
                line_budget=line_budget,
                expand=expand,
            ),
        )
    return results


def _fff_path_results(
    backend: FffClient,
    context: RetrievalContext,
    query: str,
) -> list[SearchResultPayload] | None:
    if "fuzzy_paths" not in probe_capabilities(backend):
        return None
    try:
        paths = backend.fuzzy_paths(query)
    except Exception:  # noqa: BLE001 - optional backend must never reach the caller.
        return None
    results: list[SearchResultPayload] = []
    for position, path in enumerate(paths):
        if context.allow is not None and not context.allow(path):
            continue
        score, reasons = apply_signals(
            path,
            _FFF_BASE_SCORE - position,
            ("fff_path",),
            context.signals,
        )
        results.append(
            {
                "path": path,
                "score": score,
                "reasons": reasons,
                "snippet": None,
                "symbol": None,
            },
        )
    return results


def _fff_content_results(  # noqa: PLR0913 - fff grep candidates plus shaping knobs.
    backend: FffClient,
    context: RetrievalContext,
    query: str,
    *,
    items_by_path: dict[str, IndexedFile],
    line_budget: int,
    expand: bool,
) -> list[SearchResultPayload] | None:
    if "grep_content" not in probe_capabilities(backend):
        return None
    try:
        hits = backend.grep_content(query)
    except Exception:  # noqa: BLE001 - optional backend must never reach the caller.
        return None
    indexes_by_path: dict[str, list[int]] = {}
    for hit in hits:
        if hit.path in items_by_path:
            indexes_by_path.setdefault(hit.path, []).append(hit.line - 1)
    results: list[SearchResultPayload] = []
    for path, raw_indexes in indexes_by_path.items():
        item = items_by_path[path]
        lines = searchable_lines(context.repo_root, path)
        match_indexes = tuple(
            sorted({index for index in raw_indexes if 0 <= index < len(lines)}),
        )
        if not match_indexes:
            continue
        signals = content_signals(path, context.signals)
        results.extend(
            _shape_content_matches(
                context,
                item,
                lines,
                match_indexes,
                signals=signals,
                line_budget=line_budget,
                expand=expand,
            ),
        )
    return results


def _shape_content_matches(  # noqa: PLR0913 - per-file match data plus shaping knobs.
    context: RetrievalContext,
    item: IndexedFile,
    lines: list[str],
    match_indexes: tuple[int, ...],
    *,
    signals: tuple[float, tuple[str, ...]],
    line_budget: int,
    expand: bool,
) -> list[SearchResultPayload]:
    if expand:
        score, reasons = signals
        return [
            {
                "path": item.path,
                "score": score,
                "reasons": reasons,
                "snippet": snippet(lines, index, line_budget),
                "symbol": None,
            }
            for index in match_indexes
        ]
    return collapsed_results(context.repo_root, item, lines, match_indexes, signals)
