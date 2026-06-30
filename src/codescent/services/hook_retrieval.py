"""Read-only ranked retrieval for the grep-injection hook (U1).

The hook search path must rank exactly like :class:`SearchService` but write
nothing — no frecency, no index mutation (R10/AE5) — and it must surface the
match *line number* that ``SearchResultPayload`` drops (R7). This helper
assembles the same primitives ``SearchService.multi_search_content`` uses
(``ranking_signals_for`` + ``content_signals`` + ``multi_grep`` +
``collapse_file_matches``), but keeps line numbers and never calls
``record_frecency``. Read-only is a property of *construction* here, not a flag.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from codescent.core.paths import resolve_repo_root
from codescent.core.symbol_formatter import collapse_file_matches
from codescent.engine.inventory import build_file_inventory
from codescent.engine.search.multi_grep import multi_grep
from codescent.services.config import ConfigService
from codescent.services.quality_signals import quality_annotation_for
from codescent.services.search_collapse import content_signals, file_spans
from codescent.services.search_support import ranking_signals_for, searchable_lines

if TYPE_CHECKING:
    from pathlib import Path

    from codescent.core.models import IndexedFile
    from codescent.engine.search import RankingSignals


@dataclass(frozen=True, slots=True)
class HookMatch:
    """One ranked hook match: enough to render ``symbol path:line`` + tags."""

    path: str
    line: int
    symbol_name: str | None
    symbol_kind: str | None
    score: float
    git_modified: bool
    # Read-only quality flags (hotspot/dead_code/duplicate/complex), populated
    # only for git-modified matches — the v1 health surface (R8). Empty otherwise.
    health: tuple[str, ...]


def ranked_matches(
    repo_root: Path | str,
    pattern: str,
    *,
    limit: int = 5,
) -> tuple[HookMatch, ...]:
    """Top ``limit`` frecency/git-ranked matches for ``pattern``, read-only.

    Mirrors content search ranking but retains each hit's representative line and
    records nothing. Returns ``()`` when the pattern is empty or has no matches.
    """
    if not pattern:
        return ()
    root = resolve_repo_root(repo_root)
    config = ConfigService(root).load()
    signals = ranking_signals_for(root)

    matches: list[HookMatch] = []
    for item in build_file_inventory(root, config=config):
        matches.extend(_file_matches(root, item, pattern, signals))
    matches.sort(key=lambda match: (-match.score, match.path, match.line))
    return tuple(matches[:limit])


def _file_matches(
    root: Path,
    item: IndexedFile,
    pattern: str,
    signals: RankingSignals,
) -> list[HookMatch]:
    """Collapsed, ranked hits for ``pattern`` within one file (read-only)."""
    lines = searchable_lines(root, item.path)
    indexes = multi_grep((pattern,), lines).get(pattern, ())
    if not indexes:
        return []
    spans, confidence = file_spans(root, item, expand=False)
    score, _reasons = content_signals(item.path, signals)
    git_modified = item.path in signals.git_modified
    health: tuple[str, ...] = ()
    if git_modified:
        annotation = quality_annotation_for(item.path, signals.quality)
        health = annotation["flags"] if annotation is not None else ()
    hits = collapse_file_matches(
        lines=lines,
        match_lines=tuple(index + 1 for index in indexes),
        symbols=spans,
        confidence=confidence,
    )
    return [
        HookMatch(
            path=item.path,
            line=hit["match_lines"][0],
            symbol_name=hit["symbol"]["name"] if hit["symbol"] else None,
            symbol_kind=hit["symbol"]["kind"] if hit["symbol"] else None,
            score=score,
            git_modified=git_modified,
            health=health,
        )
        for hit in hits
    ]
