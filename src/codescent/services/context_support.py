from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

from pydantic import TypeAdapter

from codescent.engine.context import source_range
from codescent.services.repo_index import RepoIndexService
from codescent.storage import RepositoryStorage, StorageState, initialize_storage

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Sequence
    from pathlib import Path

    from codescent.core.models import PageOptions
    from codescent.engine.context.ranges import SourceRange
    from codescent.engine.parsers.python import ParsedPythonFile, ParsedSymbol
    from codescent.services.freshness import AdvisoryConfidence

SOURCE_LINE_CAP = 8
LOW_CONFIDENCE_THRESHOLD = 0.6
HIGH_CONFIDENCE_THRESHOLD = 0.85
CALLER_ROW_LENGTH = 5
MIN_RELATED_TERM_LENGTH = 3
RELATED_REASON_WEIGHTS = {
    "test_match": 0.7,
    "import_graph": 0.65,
    "git_history": 0.6,
    "co_change": 0.62,
    "directory_proximity": 0.35,
    "search_similarity": 0.3,
}
COUNT_ROW: TypeAdapter[tuple[int] | None] = TypeAdapter(tuple[int] | None)


class SymbolMatchPayload(TypedDict):
    name: str
    qualified_name: str
    kind: str
    path: str
    start_line: int
    end_line: int
    confidence: float


class FileContextPayload(TypedDict):
    path: str
    summary: str
    symbols: tuple[str, ...]
    imports: tuple[str, ...]
    likely_tests: tuple[str, ...]
    related_files: tuple[str, ...]
    source_ranges: tuple[dict[str, str | int], ...]
    risk_notes: tuple[str, ...]
    next_tools: tuple[str, ...]
    warnings: tuple[str, ...]
    confidence: AdvisoryConfidence
    index_fresh: bool
    index_was_stale: bool
    auto_refreshed: bool
    changed_files: tuple[str, ...]
    refresh_error: str | None


class SymbolContextPayload(TypedDict):
    symbol: SymbolMatchPayload
    likely_tests: tuple[str, ...]
    source_ranges: tuple[dict[str, str | int], ...]
    risk_notes: tuple[str, ...]
    warnings: tuple[str, ...]
    confidence: AdvisoryConfidence
    index_fresh: bool
    index_was_stale: bool
    auto_refreshed: bool
    changed_files: tuple[str, ...]
    refresh_error: str | None


class GraphResultPayload(TypedDict):
    text: str
    path: str
    start_line: int
    confidence: float
    certainty: str
    caller: str | None


class BaseGraphToolPayload(TypedDict):
    query: str
    results: tuple[GraphResultPayload, ...]
    next_cursor: int | None


class GraphToolPayload(BaseGraphToolPayload):
    warnings: tuple[str, ...]
    confidence: AdvisoryConfidence
    next_tools: tuple[str, ...]
    index_fresh: bool
    index_was_stale: bool
    auto_refreshed: bool
    changed_files: tuple[str, ...]
    refresh_error: str | None


class RelatedFilePayload(TypedDict):
    path: str
    reasons: tuple[str, ...]
    confidence: float


class RelatedFilesPayload(TypedDict):
    path: str
    results: tuple[RelatedFilePayload, ...]
    next_cursor: int | None
    warnings: tuple[str, ...]
    confidence: AdvisoryConfidence
    next_tools: tuple[str, ...]
    index_fresh: bool
    index_was_stale: bool
    auto_refreshed: bool
    changed_files: tuple[str, ...]
    refresh_error: str | None


def symbol_payload(
    parsed: ParsedPythonFile,
    symbol: ParsedSymbol,
) -> SymbolMatchPayload:
    return {
        "name": symbol.name,
        "qualified_name": symbol.qualified_name,
        "kind": symbol.kind,
        "path": parsed.path,
        "start_line": symbol.start_line,
        "end_line": symbol.end_line,
        "confidence": symbol.confidence,
    }


def matches_symbol(query: str, symbol: ParsedSymbol) -> bool:
    folded_query = query.lower()
    return (
        folded_query in symbol.name.lower()
        or folded_query in symbol.qualified_name.lower()
    )


def file_by_path(files: tuple[ParsedPythonFile, ...], path: str) -> ParsedPythonFile:
    return next(parsed for parsed in files if parsed.path == path)


def find_qualified_symbol(
    files: tuple[ParsedPythonFile, ...],
    qualified_name: str,
) -> tuple[ParsedPythonFile, ParsedSymbol]:
    return next(
        (parsed, symbol)
        for parsed in files
        for symbol in parsed.symbols
        if symbol.qualified_name == qualified_name
    )


def file_ranges(repo_root: Path, parsed: ParsedPythonFile) -> tuple[SourceRange, ...]:
    return tuple(
        source_range(
            repo_root,
            parsed.path,
            start_line=symbol.start_line,
            end_line=symbol.end_line,
            line_cap=SOURCE_LINE_CAP,
        )
        for symbol in parsed.symbols[:2]
    )


def likely_tests(
    files: tuple[ParsedPythonFile, ...],
    parsed: ParsedPythonFile,
    symbol_name: str | None = None,
) -> tuple[str, ...]:
    candidates: list[str] = []
    module_tail = parsed.module.rsplit(".", maxsplit=1)[-1]
    for candidate in files:
        if not candidate.is_test:
            continue
        import_modules = {imported.module for imported in candidate.imports}
        reference_names = {reference.name for reference in candidate.references}
        if parsed.module in import_modules or module_tail in candidate.path:
            candidates.append(candidate.path)
            continue
        if symbol_name is not None and symbol_name in reference_names:
            candidates.append(candidate.path)
    return tuple(sorted(dict.fromkeys(candidates)))


def file_summary(parsed: ParsedPythonFile) -> str:
    symbol_names = ", ".join(symbol.name for symbol in parsed.symbols) or "no symbols"
    return f"{parsed.path} defines {symbol_names}."


def import_text(module: str, name: str | None) -> str:
    if name is None:
        return module
    return f"{module}:{name}"


def risk_notes(parsed: ParsedPythonFile) -> tuple[str, ...]:
    notes: list[str] = []
    if parsed.parse_error is not None:
        notes.append(f"parse-error: {parsed.parse_error}")
    if any(
        reference.confidence < LOW_CONFIDENCE_THRESHOLD
        for reference in parsed.references
    ):
        notes.append("low-confidence references omitted from caller/callee claims")
    return tuple(notes)


def ensure_graph_indexed(repo_root: Path | str) -> StorageState:
    state = initialize_storage(repo_root)
    with RepositoryStorage(state).read_connection() as connection:
        if graph_row_count(connection) > 0:
            return state
    _ = RepoIndexService(state.repo_root).index_repo()
    return initialize_storage(state.repo_root)


def graph_row_count(connection: sqlite3.Connection) -> int:
    reference_count = count_rows(
        connection,
        "select count(*) from symbol_references",
    )
    call_count = count_rows(connection, "select count(*) from call_edges")
    return reference_count + call_count


def count_rows(connection: sqlite3.Connection, sql: str) -> int:
    row = COUNT_ROW.validate_python(connection.execute(sql).fetchone())
    if row is None:
        return 0
    return row[0]


def like(query: str) -> str:
    return f"%{query.lower()}%"


def graph_payload(
    query: str,
    rows: Sequence[
        tuple[str, str, int, float] | tuple[str, str, int, float, str | None]
    ],
    page: PageOptions,
) -> BaseGraphToolPayload:
    visible_rows = rows[: page.limit]
    results: list[GraphResultPayload] = []
    for row in visible_rows:
        text, path, start_line, confidence = row[:4]
        caller = row[4] if len(row) == CALLER_ROW_LENGTH else None
        results.append(
            {
                "text": text,
                "path": path,
                "start_line": start_line,
                "confidence": confidence,
                "certainty": certainty(confidence),
                "caller": caller,
            },
        )
    next_cursor = page.offset + page.limit if len(rows) > page.limit else None
    return {
        "query": query,
        "results": tuple(results),
        "next_cursor": next_cursor,
    }


def certainty(confidence: float) -> str:
    if confidence >= HIGH_CONFIDENCE_THRESHOLD:
        return "high"
    if confidence >= LOW_CONFIDENCE_THRESHOLD:
        return "medium"
    return "low"


def add_related_reason(
    reasons: dict[str, set[str]],
    path: str,
    reason: str,
) -> None:
    reasons.setdefault(path, set()).add(reason)


def imports_between(target: ParsedPythonFile, candidate: ParsedPythonFile) -> bool:
    target_imports = imported_modules(target)
    candidate_imports = imported_modules(candidate)
    return candidate.module in target_imports or target.module in candidate_imports


def imported_modules(parsed: ParsedPythonFile) -> set[str]:
    modules: set[str] = set()
    for imported in parsed.imports:
        modules.add(imported.module.lstrip("."))
    return modules


def same_directory(left: str, right: str) -> bool:
    return left.rsplit("/", maxsplit=1)[0] == right.rsplit("/", maxsplit=1)[0]


def similar_source_terms(
    target: ParsedPythonFile,
    candidate: ParsedPythonFile,
) -> bool:
    return bool(source_terms(target) & source_terms(candidate))


def source_terms(parsed: ParsedPythonFile) -> set[str]:
    terms: set[str] = set(parsed.module.replace(".", "_").split("_"))
    for symbol in parsed.symbols:
        terms.update(symbol.name.lower().split("_"))
    for reference in parsed.references:
        terms.update(reference.name.lower().split("_"))
    return {term for term in terms if len(term) >= MIN_RELATED_TERM_LENGTH}


def related_file_payload(
    *,
    path: str,
    reasons: set[str],
) -> RelatedFilePayload:
    confidence = min(
        sum(RELATED_REASON_WEIGHTS[reason] for reason in reasons),
        1.0,
    )
    return {
        "path": path,
        "reasons": tuple(sorted(reasons)),
        "confidence": confidence,
    }
