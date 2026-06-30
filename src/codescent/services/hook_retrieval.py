"""Read-only ranked retrieval for the grep-injection hook (U1).

The hook search path must surface ranked matches with their *line number* (R7)
and write nothing — no frecency, no index mutation (R10/AE5). It delegates the
content scan to the ``fff`` engine (an in-process, frecency-aware, git-annotated
file searcher), then maps each hit back to its enclosing symbol with codescent's
own parsers so the rendered ``symbol path:line`` stays consistent with the rest
of the product. ``fff`` replaced an all-files Python grep whose per-call cost
(re-reading every source file plus a full ``ranking_signals_for`` build over the
whole findings store) blew the hook's sub-second deadline on any real repo.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from codescent.core.models import IndexedFile
from codescent.core.paths import resolve_repo_root
from codescent.core.symbol_formatter import collapse_file_matches
from codescent.engine.inventory import LANGUAGE_BY_SUFFIX
from codescent.services.fff_shared import CODE_CONSTRAINT, build_finder
from codescent.services.quality_signals import quality_flags_for_paths
from codescent.services.search_collapse import file_spans
from codescent.services.search_support import searchable_lines

if TYPE_CHECKING:
    from collections.abc import Sequence

# A few hits per file is enough to collapse to a representative symbol line.
_MAX_MATCHES_PER_FILE = 3


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

    Delegates the content scan to ``fff`` (which records nothing here — only
    ``track_query`` would, and it is never called), then collapses each hit to
    its enclosing symbol. Returns ``()`` when the pattern is empty or has no
    matches.
    """
    if not pattern:
        return ()
    root = resolve_repo_root(repo_root)

    finder = build_finder(root)
    result = finder.multi_grep(
        [pattern],
        constraints=CODE_CONSTRAINT,
        smart_case=True,
        max_matches_per_file=_MAX_MATCHES_PER_FILE,
        page_limit=max(limit * 8, 40),
    )

    # Group hit lines per file, preserving fff's rank as first-seen order.
    order: list[str] = []
    lines_by_file: dict[str, list[int]] = {}
    git_modified: set[str] = set()
    for match in result.items:
        path = match.relative_path
        if path not in lines_by_file:
            lines_by_file[path] = []
            order.append(path)
        lines_by_file[path].append(match.line_number)
        if _is_git_modified(match.git_status):
            git_modified.add(path)
    if not order:
        return ()

    health_by_path = quality_flags_for_paths(root, git_modified)
    total = len(order)
    matches: list[HookMatch] = []
    for rank, path in enumerate(order):
        # fff rank → descending score so the final sort keeps fff's ordering.
        score = float(total - rank)
        matches.extend(
            _collapse_file(
                root,
                path,
                tuple(sorted(set(lines_by_file[path]))),
                score=score,
                git_modified=path in git_modified,
                health=health_by_path.get(path, ()),
            ),
        )
        # Files are processed best-rank-first, so once we hold `limit` matches no
        # lower-ranked file can enter the top slice — stop reading files early.
        if len(matches) >= limit:
            break
    matches.sort(key=lambda match: (-match.score, match.path, match.line))
    return tuple(matches[:limit])


def _collapse_file(  # noqa: PLR0913 - cohesive per-file collapse inputs
    root: Path,
    path: str,
    match_lines: Sequence[int],
    *,
    score: float,
    git_modified: bool,
    health: tuple[str, ...],
) -> list[HookMatch]:
    """Collapse one file's hit lines to enclosing-symbol matches (read-only)."""
    item = _indexed_file(path)
    if item is None:
        return []
    lines = searchable_lines(root, path)
    spans, confidence = file_spans(root, item, expand=False)
    hits = collapse_file_matches(
        lines=lines,
        match_lines=tuple(match_lines),
        symbols=spans,
        confidence=confidence,
    )
    return [
        HookMatch(
            path=path,
            line=hit["match_lines"][0],
            symbol_name=hit["symbol"]["name"] if hit["symbol"] else None,
            symbol_kind=hit["symbol"]["kind"] if hit["symbol"] else None,
            score=score,
            git_modified=git_modified,
            health=health if git_modified else (),
        )
        for hit in hits
    ]


def _indexed_file(path: str) -> IndexedFile | None:
    """Minimal IndexedFile for symbol parsing; language inferred from suffix."""
    language = LANGUAGE_BY_SUFFIX.get(Path(path).suffix)
    if language is None:
        return None
    return IndexedFile(
        path=path,
        language=language,
        hash="",
        size_bytes=0,
        line_count=0,
    )


def _is_git_modified(git_status: str) -> bool:
    return bool(git_status) and git_status != "clean"
