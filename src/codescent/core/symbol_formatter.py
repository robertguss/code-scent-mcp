from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, TypedDict, cast

from codescent.core.models import EnvelopeMode, ResponseEnvelope
from codescent.core.preservation import estimate_token_usage

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

MAX_GROUPS: Final = 6
MAX_ITEMS_PER_GROUP: Final = 2
UNKNOWN_BUCKET: Final = "unknown"

_MATCH_TYPE_PRIORITY: Final[dict[str, int]] = {"exact": 0, "partial": 1}
_ROLE_PRIORITY: Final[dict[str, int]] = {"definition": 0, "reference": 1}
_KIND_PRIORITY: Final[dict[str, int]] = {
    "class": 0,
    "function": 1,
    "method": 2,
    "variable": 3,
    "module": 4,
}


class SymbolFormatterOptions(TypedDict, total=False):
    max_groups: int
    max_items_per_group: int
    original_result_id: str | None
    cursor: int
    next_cursor: int | None


class SymbolGroupPayload(TypedDict):
    match_type: str
    role: str
    path: str
    module: str
    kind: str
    symbol_types: tuple[str, ...]
    count: int
    best_score: float
    items: tuple[dict[str, object], ...]


def format_symbol_search_results(
    query: str,
    results: Sequence[Mapping[str, object]],
    *,
    options: SymbolFormatterOptions | None = None,
) -> ResponseEnvelope:
    formatter_options: SymbolFormatterOptions = options or {}
    if not results:
        return ResponseEnvelope(
            kind="symbol_search",
            mode=EnvelopeMode.EXACT,
            summary=f"No symbol results for {query!r}.",
            items=(),
            omitted_count=0,
            original_result_id=None,
            retrieval_available=False,
            retrieval_hints=(),
            stats={"total_results": 0, "returned_results": 0, "groups_returned": 0},
        )

    max_groups = _positive_limit(formatter_options.get("max_groups"), MAX_GROUPS)
    max_items_per_group = _positive_limit(
        formatter_options.get("max_items_per_group"),
        MAX_ITEMS_PER_GROUP,
    )
    normalized_results = tuple(_normalize_result(query, result) for result in results)
    groups = _group_results(normalized_results)
    visible_groups = groups[:max_groups]
    returned_count = sum(
        min(len(group["items"]), max_items_per_group) for group in visible_groups
    )
    omitted_count = max(len(results) - returned_count, 0)
    warnings = _semantic_warnings(normalized_results)
    original_result_id = formatter_options.get("original_result_id")
    retrieval_available = omitted_count > 0 or original_result_id is not None
    mode = EnvelopeMode.SUMMARIZED if omitted_count > 0 else EnvelopeMode.EXACT
    token_estimate = estimate_token_usage(str(results))

    return ResponseEnvelope(
        kind="symbol_search",
        mode=mode,
        summary=_summary(
            query,
            len(results),
            returned_count,
            len(groups),
            omitted_count,
        ),
        items=tuple(
            _bounded_group(group, max_items_per_group=max_items_per_group)
            for group in visible_groups
        ),
        omitted_count=omitted_count,
        original_result_id=original_result_id,
        retrieval_available=retrieval_available,
        retrieval_hints=_retrieval_hints(query, original_result_id, omitted_count),
        warnings=warnings,
        stats=_stats(
            formatter_options,
            {
                "total_results": len(results),
                "returned_results": returned_count,
                "total_groups": len(groups),
                "groups_returned": len(visible_groups),
                "raw_token_estimate": token_estimate.tokens,
            },
        ),
    )


def _normalize_result(query: str, result: Mapping[str, object]) -> dict[str, object]:
    name = _string_field(result, "name")
    qualified_name = _string_field(result, "qualified_name")
    path = _string_field(result, "path") or _string_field(result, "file_path")
    line = _int_field(result, "line") or _int_field(result, "start_line")
    end_line = _int_field(result, "end_line")
    score = _float_field(result, "score")
    if score == 0:
        score = _float_field(result, "confidence")

    return {
        "name": name,
        "qualified_name": qualified_name,
        "path": path,
        "line": line,
        "end_line": end_line,
        "kind": _optional_string_field(result, "kind"),
        "match_type": _optional_string_field(result, "match_type"),
        "role": _optional_string_field(result, "role"),
        "score": score,
        "rank_reason": _rank_reason(query, result, score),
        "module": _module_name(qualified_name, path),
        "snippet": _optional_string_field(result, "snippet"),
    }


def _group_results(results: tuple[dict[str, object], ...]) -> list[SymbolGroupPayload]:
    grouped: dict[tuple[str, str, str, str], list[dict[str, object]]] = {}
    for result in sorted(results, key=_result_sort_key):
        key = (
            cast("str", result["match_type"] or UNKNOWN_BUCKET),
            cast("str", result["role"] or UNKNOWN_BUCKET),
            cast("str", result["path"] or UNKNOWN_BUCKET),
            cast("str", result["module"] or UNKNOWN_BUCKET),
        )
        grouped.setdefault(key, []).append(result)

    groups: list[SymbolGroupPayload] = []
    for (match_type, role, path, module), items in grouped.items():
        symbol_types = _symbol_types(items)
        groups.append(
            {
                "match_type": match_type,
                "role": role,
                "path": path,
                "module": module,
                "kind": symbol_types[0] if len(symbol_types) == 1 else "mixed",
                "symbol_types": symbol_types,
                "count": len(items),
                "best_score": max(cast("float", item["score"]) for item in items),
                "items": tuple(_public_item(item) for item in items),
            },
        )
    return sorted(groups, key=_group_sort_key)


def _bounded_group(
    group: SymbolGroupPayload,
    *,
    max_items_per_group: int,
) -> SymbolGroupPayload:
    visible_items = group["items"][:max_items_per_group]
    return {
        "match_type": group["match_type"],
        "role": group["role"],
        "path": group["path"],
        "module": group["module"],
        "kind": group["kind"],
        "symbol_types": group["symbol_types"],
        "count": group["count"],
        "best_score": group["best_score"],
        "items": visible_items,
    }


def _public_item(item: Mapping[str, object]) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": item["name"],
        "qualified_name": item["qualified_name"],
        "path": item["path"],
        "line": item["line"],
        "end_line": item["end_line"],
        "kind": item["kind"] or UNKNOWN_BUCKET,
        "score": item["score"],
        "rank_reason": item["rank_reason"],
    }
    if item.get("snippet"):
        payload["snippet"] = item["snippet"]
    return payload


def _semantic_warnings(results: tuple[dict[str, object], ...]) -> tuple[str, ...]:
    missing_fields = tuple(
        field
        for field in ("match_type", "role", "kind")
        if any(result[field] is None for result in results)
    )
    if not missing_fields:
        return ()
    return tuple(
        f"semantic classification missing: {field}; grouped under 'unknown'"
        for field in missing_fields
    )


def _summary(
    query: str,
    total_count: int,
    returned_count: int,
    group_count: int,
    omitted_count: int,
) -> str:
    if omitted_count == 0:
        return (
            f"Grouped {total_count} symbol results for {query!r} into "
            f"{group_count} groups."
        )
    return (
        f"Grouped {total_count} symbol results for {query!r}; returned "
        f"{returned_count} compact items across {group_count} groups and omitted "
        f"{omitted_count}."
    )


def _retrieval_hints(
    query: str,
    original_result_id: str | None,
    omitted_count: int,
) -> tuple[str, ...]:
    if omitted_count == 0 and original_result_id is None:
        return ()
    hints = [
        f"Refine symbol query {query!r} or request a narrower limit/cursor window.",
    ]
    if original_result_id is not None:
        hints.append(f"Use retrieve_result({original_result_id!r}) for full results.")
    else:
        hints.append("No storage attached; preserve original payload upstream.")
    return tuple(hints)


def _stats(
    options: SymbolFormatterOptions,
    base_stats: dict[str, int],
) -> dict[str, int | float]:
    stats: dict[str, int | float] = dict(base_stats)
    cursor = options.get("cursor")
    if isinstance(cursor, int):
        stats["cursor"] = cursor
    next_cursor = options.get("next_cursor")
    if isinstance(next_cursor, int):
        stats["next_cursor"] = next_cursor
    return stats


def _rank_reason(query: str, result: Mapping[str, object], score: float) -> str:
    existing_reason = _optional_string_field(
        result, "rank_reason"
    ) or _optional_string_field(result, "reason")
    if existing_reason is not None:
        return existing_reason
    match_type = _optional_string_field(result, "match_type") or UNKNOWN_BUCKET
    role = _optional_string_field(result, "role") or UNKNOWN_BUCKET
    return f"{match_type} {role} match for {query!r} with score={score:.2f}"


def _result_sort_key(
    item: Mapping[str, object],
) -> tuple[int, int, float, str, int, int, str]:
    match_type = cast("str | None", item["match_type"])
    role = cast("str | None", item["role"])
    kind = cast("str | None", item["kind"])
    return (
        _MATCH_TYPE_PRIORITY.get(match_type or "", 99),
        _ROLE_PRIORITY.get(role or "", 99),
        -cast("float", item["score"]),
        cast("str", item["path"]),
        cast("int", item["line"]),
        _KIND_PRIORITY.get(kind or "", 99),
        cast("str", item["qualified_name"]),
    )


def _group_sort_key(
    group: SymbolGroupPayload,
) -> tuple[int, int, float, str, int, str]:
    return (
        _MATCH_TYPE_PRIORITY.get(group["match_type"], 99),
        _ROLE_PRIORITY.get(group["role"], 99),
        -group["best_score"],
        group["path"],
        _KIND_PRIORITY.get(group["kind"], 99),
        group["module"],
    )


def _symbol_types(items: list[dict[str, object]]) -> tuple[str, ...]:
    kinds = {cast("str | None", item["kind"]) or UNKNOWN_BUCKET for item in items}
    return tuple(
        sorted(kinds, key=lambda kind: (_KIND_PRIORITY.get(kind, 99), kind)),
    )


def _module_name(qualified_name: str, path: str) -> str:
    if "." in qualified_name:
        return qualified_name.rsplit(".", maxsplit=1)[0]
    if path.endswith(".py"):
        return path.removesuffix(".py").replace("/", ".")
    return path or UNKNOWN_BUCKET


def _positive_limit(value: object, fallback: int) -> int:
    if isinstance(value, int) and value > 0:
        return value
    return fallback


def _optional_string_field(result: Mapping[str, object], key: str) -> str | None:
    value = result.get(key)
    if isinstance(value, str) and value != "":
        return value
    return None


def _string_field(result: Mapping[str, object], key: str) -> str:
    return _optional_string_field(result, key) or ""


def _int_field(result: Mapping[str, object], key: str) -> int:
    value = result.get(key)
    if isinstance(value, int):
        return value
    return 0


def _float_field(result: Mapping[str, object], key: str) -> float:
    value = result.get(key)
    if isinstance(value, int | float):
        return float(value)
    return 0.0


# --- Collapse-to-symbol engine ------------------------------------------------
#
# Map a content/grep match line to its enclosing function/class and return that
# symbol's signature instead of the bare line. Python ranges come from the AST
# (confidence="exact"); TS/Go ranges come from the regex packs, so those hits are
# labelled confidence="heuristic". A match with no enclosing symbol (module level)
# degrades gracefully to the bounded raw line.

EXACT_CONFIDENCE: Final = "exact"
HEURISTIC_CONFIDENCE: Final = "heuristic"
MAX_COLLAPSE_LINE_CHARS: Final = 200
_TRUNCATION_MARKER: Final = "..."
_IMPORT_LINE_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?:import\b|from\s+\S+\s+import\b)",
)


@dataclass(frozen=True, slots=True)
class SymbolSpan:
    """Minimal enclosing-symbol record (kept core-local to avoid an engine dep)."""

    name: str
    qualified_name: str
    kind: str
    start_line: int
    end_line: int


class CollapsedSymbol(TypedDict):
    # Lean on purpose: the signature lives in the result's ``snippet`` (collapsed
    # results set snippet = signature), so it is not duplicated here. This keeps
    # the per-hit metadata small, which is the whole point of the unit.
    name: str
    kind: str
    start_line: int
    end_line: int
    confidence: str
    match_count: int


class CollapsedHit(TypedDict):
    snippet: str
    symbol: CollapsedSymbol | None
    match_lines: tuple[int, ...]


def truncate_line(text: str, *, char_bound: int = MAX_COLLAPSE_LINE_CHARS) -> str:
    stripped = text.strip()
    if len(stripped) <= char_bound:
        return stripped
    keep = max(char_bound - len(_TRUNCATION_MARKER), 0)
    return stripped[:keep] + _TRUNCATION_MARKER


def is_import_only_line(text: str) -> bool:
    return _IMPORT_LINE_RE.match(text) is not None


def enclosing_symbol(
    symbols: Sequence[SymbolSpan],
    line_number: int,
) -> SymbolSpan | None:
    best: SymbolSpan | None = None
    for symbol in symbols:
        if symbol.start_line <= line_number <= symbol.end_line and (
            best is None or _is_inner(symbol, best)
        ):
            best = symbol
    return best


def _is_inner(candidate: SymbolSpan, current: SymbolSpan) -> bool:
    candidate_span = candidate.end_line - candidate.start_line
    current_span = current.end_line - current.start_line
    if candidate_span != current_span:
        return candidate_span < current_span
    return candidate.start_line > current.start_line


def signature_for(
    lines: Sequence[str],
    symbol: SymbolSpan,
    *,
    char_bound: int = MAX_COLLAPSE_LINE_CHARS,
) -> str:
    return truncate_line(_line_text(lines, symbol.start_line), char_bound=char_bound)


def build_collapsed_symbol(
    symbol: SymbolSpan,
    confidence: str,
    *,
    match_count: int = 1,
) -> CollapsedSymbol:
    return {
        "name": symbol.name,
        "kind": symbol.kind,
        "start_line": symbol.start_line,
        "end_line": symbol.end_line,
        "confidence": confidence,
        "match_count": match_count,
    }


def collapse_line(
    lines: Sequence[str],
    line_number: int,
    symbols: Sequence[SymbolSpan],
    confidence: str,
    *,
    char_bound: int = MAX_COLLAPSE_LINE_CHARS,
) -> CollapsedHit:
    """Collapse a single match line to its enclosing symbol (or a bounded line)."""
    symbol = enclosing_symbol(symbols, line_number)
    if symbol is None:
        return {
            "snippet": truncate_line(
                _line_text(lines, line_number),
                char_bound=char_bound,
            ),
            "symbol": None,
            "match_lines": (line_number,),
        }
    return {
        "snippet": signature_for(lines, symbol, char_bound=char_bound),
        "symbol": build_collapsed_symbol(symbol, confidence),
        "match_lines": (line_number,),
    }


def collapse_file_matches(
    *,
    lines: Sequence[str],
    match_lines: Sequence[int],
    symbols: Sequence[SymbolSpan],
    confidence: str,
    char_bound: int = MAX_COLLAPSE_LINE_CHARS,
) -> tuple[CollapsedHit, ...]:
    """Collapse every match line in one file to its enclosing symbol.

    Multiple matches inside the same definition collapse to a single hit (the
    token win). Module-level matches degrade to bounded raw lines, and any
    import-only module-level match is dropped once a real definition is shown.

    Args:
        lines: The file's lines (0-indexed; ``match_lines`` are 1-based).
        match_lines: 1-based line numbers that matched the query.
        symbols: Enclosing-symbol spans for the file.
        confidence: ``"exact"`` (Python AST) or ``"heuristic"`` (regex packs).
        char_bound: Per-line character cap for signatures and raw lines.

    Returns:
        Ordered, deduped collapsed hits for the file.
    """
    ordered = sorted(dict.fromkeys(match_lines))
    has_symbol_hit = any(
        enclosing_symbol(symbols, line) is not None for line in ordered
    )
    hits: list[CollapsedHit] = []
    position_by_symbol: dict[tuple[int, str], int] = {}
    for line in ordered:
        symbol = enclosing_symbol(symbols, line)
        if symbol is None:
            if has_symbol_hit and is_import_only_line(_line_text(lines, line)):
                continue
            hits.append(
                collapse_line(lines, line, symbols, confidence, char_bound=char_bound)
            )
            continue
        key = (symbol.start_line, symbol.qualified_name)
        position = position_by_symbol.get(key)
        if position is None:
            position_by_symbol[key] = len(hits)
            hits.append(
                collapse_line(lines, line, symbols, confidence, char_bound=char_bound),
            )
            continue
        _append_match(hits[position], line)
    return tuple(hits)


def _append_match(hit: CollapsedHit, line_number: int) -> None:
    hit["match_lines"] = (*hit["match_lines"], line_number)
    payload = hit["symbol"]
    if payload is not None:
        payload["match_count"] = len(hit["match_lines"])


def _line_text(lines: Sequence[str], line_number: int) -> str:
    index = line_number - 1
    if 0 <= index < len(lines):
        return lines[index]
    return ""
