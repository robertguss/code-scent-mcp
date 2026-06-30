"""Collapse-to-symbol wiring for content search.

Maps each content match line to its enclosing function/class via the language
parsers, then renders that symbol's signature instead of the bare line. This is
the per-file orchestration that sits between :class:`SearchService` and the
language-agnostic collapse engine in :mod:`codescent.core.symbol_formatter`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from codescent.core.symbol_formatter import (
    EXACT_CONFIDENCE,
    HEURISTIC_CONFIDENCE,
    SymbolSpan,
    collapse_file_matches,
)
from codescent.engine.packs_ts import parse_typescript_file
from codescent.engine.parsers.python import parse_python_file
from codescent.engine.search import apply_signals

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from codescent.core.models import IndexedFile
    from codescent.engine.parsers.python import ParsedPythonFile
    from codescent.engine.search import RankingSignals
    from codescent.services.search_support import SearchResultPayload

# Suffix-language -> (parser, collapse confidence label). Python is AST-exact;
# the TS/JS regex pack is heuristic. Go is not in the search inventory, so it
# never reaches this map. Languages absent here collapse to bounded raw lines.
_PARSERS_BY_LANGUAGE: Final[
    dict[str, tuple[Callable[[Path | str, str], ParsedPythonFile], str]]
] = {
    "python": (parse_python_file, EXACT_CONFIDENCE),
    "typescript": (parse_typescript_file, HEURISTIC_CONFIDENCE),
    "javascript": (parse_typescript_file, HEURISTIC_CONFIDENCE),
}


def content_signals(
    path: str,
    signals: RankingSignals,
) -> tuple[float, tuple[str, ...]]:
    return apply_signals(path, 100.0, ("content_match",), signals)


def collapsed_results(
    repo_root: Path,
    item: IndexedFile,
    lines: list[str],
    match_indexes: tuple[int, ...],
    signals: tuple[float, tuple[str, ...]],
) -> list[SearchResultPayload]:
    score, reasons = signals
    spans, confidence = symbols_for_file(repo_root, item)
    hits = collapse_file_matches(
        lines=lines,
        match_lines=tuple(index + 1 for index in match_indexes),
        symbols=spans,
        confidence=confidence,
    )
    results: list[SearchResultPayload] = []
    for hit in hits:
        marker = "collapsed_to_symbol" if hit["symbol"] is not None else "module_level"
        results.append(
            {
                "path": item.path,
                "score": score,
                "reasons": (*reasons, marker),
                "snippet": hit["snippet"],
                "symbol": hit["symbol"],
            },
        )
    return results


def file_spans(
    repo_root: Path,
    item: IndexedFile,
    *,
    expand: bool,
) -> tuple[tuple[SymbolSpan, ...], str]:
    if expand:
        return (), ""
    return symbols_for_file(repo_root, item)


def symbols_for_file(
    repo_root: Path,
    item: IndexedFile,
) -> tuple[tuple[SymbolSpan, ...], str]:
    entry = _PARSERS_BY_LANGUAGE.get(item.language)
    if entry is None:
        return (), ""
    parse, confidence = entry
    try:
        parsed = parse(repo_root / item.path, item.path)
    except (OSError, UnicodeDecodeError, ValueError):
        return (), confidence
    spans = tuple(
        SymbolSpan(
            name=symbol.name,
            qualified_name=symbol.qualified_name,
            kind=symbol.kind,
            start_line=symbol.start_line,
            end_line=symbol.end_line,
        )
        for symbol in parsed.symbols
    )
    return spans, confidence
