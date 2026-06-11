from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, TypedDict, cast

from codescent.core.models import PageOptions
from codescent.core.paths import normalize_repo_path, resolve_repo_root
from codescent.engine.context import source_range
from codescent.services.git import git_related_paths
from codescent.services.repo_index import RepoIndexService
from codescent.services.symbols import SymbolService
from codescent.storage import RepositoryStorage, StorageState, initialize_storage

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Sequence
    from pathlib import Path

    from codescent.engine.context.ranges import SourceRange
    from codescent.engine.parsers.python import ParsedPythonFile, ParsedSymbol

SOURCE_LINE_CAP = 8
LOW_CONFIDENCE_THRESHOLD = 0.6
HIGH_CONFIDENCE_THRESHOLD = 0.85
CALLER_ROW_LENGTH = 5
MIN_RELATED_TERM_LENGTH = 3
RELATED_REASON_WEIGHTS = {
    "test_match": 0.7,
    "import_graph": 0.65,
    "git_history": 0.6,
    "directory_proximity": 0.35,
    "search_similarity": 0.3,
}


class SymbolMatchPayload(TypedDict):
    name: str
    qualified_name: str
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


class SymbolContextPayload(TypedDict):
    symbol: SymbolMatchPayload
    likely_tests: tuple[str, ...]
    source_ranges: tuple[dict[str, str | int], ...]
    risk_notes: tuple[str, ...]


class GraphResultPayload(TypedDict):
    text: str
    path: str
    start_line: int
    confidence: float
    certainty: str
    caller: str | None


class GraphToolPayload(TypedDict):
    query: str
    results: tuple[GraphResultPayload, ...]
    next_cursor: int | None


class RelatedFilePayload(TypedDict):
    path: str
    reasons: tuple[str, ...]
    confidence: float


class RelatedFilesPayload(TypedDict):
    path: str
    results: tuple[RelatedFilePayload, ...]
    next_cursor: int | None


@dataclass(frozen=True, slots=True)
class ContextService:
    repo_root: Path | str

    def find_symbol(
        self,
        query: str,
        *,
        limit: int = 20,
    ) -> tuple[SymbolMatchPayload, ...]:
        files = SymbolService(self.repo_root).extract().files
        matches = [
            _symbol_payload(parsed, symbol)
            for parsed in files
            for symbol in parsed.symbols
            if _matches_symbol(query, symbol)
        ]
        return tuple(matches[: min(max(limit, 1), 20)])

    def get_file_context(self, path: str) -> FileContextPayload:
        repo_root = resolve_repo_root(self.repo_root)
        relative_path = (
            normalize_repo_path(repo_root, path).relative_to(repo_root).as_posix()
        )
        files = SymbolService(repo_root).extract().files
        parsed = _file_by_path(files, relative_path)
        ranges = _file_ranges(repo_root, parsed)
        likely_tests = _likely_tests(files, parsed)
        return {
            "path": parsed.path,
            "summary": _file_summary(parsed),
            "symbols": tuple(symbol.name for symbol in parsed.symbols),
            "imports": tuple(
                _import_text(imported.module, imported.name)
                for imported in parsed.imports
            ),
            "likely_tests": likely_tests,
            "related_files": likely_tests,
            "source_ranges": tuple(item.to_payload() for item in ranges),
            "risk_notes": _risk_notes(parsed),
            "next_tools": tuple(
                f"get_symbol_context:{symbol.qualified_name}"
                for symbol in parsed.symbols
            ),
        }

    def get_symbol_context(self, qualified_name: str) -> SymbolContextPayload:
        repo_root = resolve_repo_root(self.repo_root)
        files = SymbolService(repo_root).extract().files
        parsed, symbol = _find_qualified_symbol(files, qualified_name)
        return {
            "symbol": _symbol_payload(parsed, symbol),
            "likely_tests": _likely_tests(files, parsed, symbol.name),
            "source_ranges": (
                source_range(
                    repo_root,
                    parsed.path,
                    start_line=symbol.start_line,
                    end_line=symbol.end_line,
                    line_cap=SOURCE_LINE_CAP,
                ).to_payload(),
            ),
            "risk_notes": _risk_notes(parsed),
        }

    def find_references(
        self,
        query: str,
        *,
        limit: int = 20,
        cursor: int = 0,
    ) -> GraphToolPayload:
        page = PageOptions(limit=limit, offset=cursor)
        state = _ensure_graph_indexed(self.repo_root)
        with RepositoryStorage(state).read_connection() as connection:
            rows: list[tuple[str, str, int, float]] = connection.execute(
                """
                select
                    symbol_references.reference_text,
                    files.path,
                    symbol_references.start_line,
                    symbol_references.confidence
                from symbol_references
                join files on files.id = symbol_references.source_file_id
                where lower(symbol_references.reference_text) like ?
                order by files.path, symbol_references.start_line
                limit ? offset ?
                """,
                (_like(query), page.limit + 1, page.offset),
            ).fetchall()
        return _graph_payload(query, rows, page)

    def find_callers(
        self,
        query: str,
        *,
        limit: int = 20,
        cursor: int = 0,
    ) -> GraphToolPayload:
        page = PageOptions(limit=limit, offset=cursor)
        state = _ensure_graph_indexed(self.repo_root)
        with RepositoryStorage(state).read_connection() as connection:
            rows: list[tuple[str, str, int, float, str | None]] = connection.execute(
                """
                select
                    call_edges.call_text,
                    files.path,
                    call_edges.start_line,
                    call_edges.confidence,
                    symbols.qualified_name
                from call_edges
                join files on files.id = call_edges.source_file_id
                left join symbols on symbols.id = call_edges.caller_symbol_id
                where lower(call_edges.call_text) like ?
                order by files.path, call_edges.start_line
                limit ? offset ?
                """,
                (_like(query), page.limit + 1, page.offset),
            ).fetchall()
        return _graph_payload(query, rows, page)

    def find_callees(
        self,
        query: str,
        *,
        limit: int = 20,
        cursor: int = 0,
    ) -> GraphToolPayload:
        page = PageOptions(limit=limit, offset=cursor)
        state = _ensure_graph_indexed(self.repo_root)
        with RepositoryStorage(state).read_connection() as connection:
            rows: list[tuple[str, str, int, float, str | None]] = connection.execute(
                """
                select
                    call_edges.call_text,
                    files.path,
                    call_edges.start_line,
                    call_edges.confidence,
                    symbols.qualified_name
                from call_edges
                join files on files.id = call_edges.source_file_id
                left join symbols on symbols.id = call_edges.caller_symbol_id
                where
                    lower(symbols.name) like ?
                    or lower(symbols.qualified_name) like ?
                order by files.path, call_edges.start_line
                limit ? offset ?
                """,
                (_like(query), _like(query), page.limit + 1, page.offset),
            ).fetchall()
        return _graph_payload(query, rows, page)

    def get_related_files(
        self,
        path: str,
        *,
        limit: int = 20,
        cursor: int = 0,
    ) -> RelatedFilesPayload:
        page = PageOptions(limit=limit, offset=cursor)
        repo_root = resolve_repo_root(self.repo_root)
        relative_path = (
            normalize_repo_path(repo_root, path).relative_to(repo_root).as_posix()
        )
        files = SymbolService(repo_root).extract().files
        target = _file_by_path(files, relative_path)
        reasons: dict[str, set[str]] = {}

        for related_path in _likely_tests(files, target):
            _add_related_reason(reasons, related_path, "test_match")

        for candidate in files:
            if candidate.path == target.path:
                continue
            if _imports_between(target, candidate):
                _add_related_reason(reasons, candidate.path, "import_graph")
            if _same_directory(target.path, candidate.path):
                _add_related_reason(reasons, candidate.path, "directory_proximity")
            if _similar_source_terms(target, candidate):
                _add_related_reason(reasons, candidate.path, "search_similarity")

        for related_path in git_related_paths(repo_root, target.path):
            _add_related_reason(reasons, related_path, "git_history")

        rows = sorted(
            (
                _related_file_payload(path=item_path, reasons=item_reasons)
                for item_path, item_reasons in reasons.items()
                if item_path != target.path
            ),
            key=lambda item: (-item["confidence"], item["path"]),
        )
        visible_rows = rows[page.offset : page.offset + page.limit]
        next_cursor = (
            page.offset + page.limit
            if page.offset + page.limit < len(rows)
            else None
        )
        return {
            "path": target.path,
            "results": tuple(visible_rows),
            "next_cursor": next_cursor,
        }


def _symbol_payload(
    parsed: ParsedPythonFile,
    symbol: ParsedSymbol,
) -> SymbolMatchPayload:
    return {
        "name": symbol.name,
        "qualified_name": symbol.qualified_name,
        "path": parsed.path,
        "start_line": symbol.start_line,
        "end_line": symbol.end_line,
        "confidence": symbol.confidence,
    }


def _matches_symbol(query: str, symbol: ParsedSymbol) -> bool:
    folded_query = query.lower()
    return (
        folded_query in symbol.name.lower()
        or folded_query in symbol.qualified_name.lower()
    )


def _file_by_path(files: tuple[ParsedPythonFile, ...], path: str) -> ParsedPythonFile:
    return next(parsed for parsed in files if parsed.path == path)


def _find_qualified_symbol(
    files: tuple[ParsedPythonFile, ...],
    qualified_name: str,
) -> tuple[ParsedPythonFile, ParsedSymbol]:
    return next(
        (parsed, symbol)
        for parsed in files
        for symbol in parsed.symbols
        if symbol.qualified_name == qualified_name
    )


def _file_ranges(repo_root: Path, parsed: ParsedPythonFile) -> tuple[SourceRange, ...]:
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


def _likely_tests(
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


def _file_summary(parsed: ParsedPythonFile) -> str:
    symbol_names = ", ".join(symbol.name for symbol in parsed.symbols) or "no symbols"
    return f"{parsed.path} defines {symbol_names}."


def _import_text(module: str, name: str | None) -> str:
    if name is None:
        return module
    return f"{module}:{name}"


def _risk_notes(parsed: ParsedPythonFile) -> tuple[str, ...]:
    notes: list[str] = []
    if parsed.parse_error is not None:
        notes.append(f"parse-error: {parsed.parse_error}")
    if any(
        reference.confidence < LOW_CONFIDENCE_THRESHOLD
        for reference in parsed.references
    ):
        notes.append("low-confidence references omitted from caller/callee claims")
    return tuple(notes)


def _ensure_graph_indexed(repo_root: Path | str) -> StorageState:
    state = initialize_storage(repo_root)
    with RepositoryStorage(state).read_connection() as connection:
        if _graph_row_count(connection) > 0:
            return state
    _ = RepoIndexService(state.repo_root).index_repo()
    return initialize_storage(state.repo_root)


def _graph_row_count(connection: sqlite3.Connection) -> int:
    reference_count = _count_rows(
        connection,
        "select count(*) from symbol_references",
    )
    call_count = _count_rows(connection, "select count(*) from call_edges")
    return reference_count + call_count


def _count_rows(connection: sqlite3.Connection, sql: str) -> int:
    row = cast("tuple[int] | None", connection.execute(sql).fetchone())
    if row is None:
        return 0
    return row[0]


def _like(query: str) -> str:
    return f"%{query.lower()}%"


def _graph_payload(
    query: str,
    rows: Sequence[
        tuple[str, str, int, float] | tuple[str, str, int, float, str | None]
    ],
    page: PageOptions,
) -> GraphToolPayload:
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
                "certainty": _certainty(confidence),
                "caller": caller,
            },
        )
    next_cursor = page.offset + page.limit if len(rows) > page.limit else None
    return {
        "query": query,
        "results": tuple(results),
        "next_cursor": next_cursor,
    }


def _certainty(confidence: float) -> str:
    if confidence >= HIGH_CONFIDENCE_THRESHOLD:
        return "high"
    if confidence >= LOW_CONFIDENCE_THRESHOLD:
        return "medium"
    return "low"


def _add_related_reason(
    reasons: dict[str, set[str]],
    path: str,
    reason: str,
) -> None:
    reasons.setdefault(path, set()).add(reason)


def _imports_between(target: ParsedPythonFile, candidate: ParsedPythonFile) -> bool:
    target_imports = _imported_modules(target)
    candidate_imports = _imported_modules(candidate)
    return candidate.module in target_imports or target.module in candidate_imports


def _imported_modules(parsed: ParsedPythonFile) -> set[str]:
    modules: set[str] = set()
    for imported in parsed.imports:
        modules.add(imported.module.lstrip("."))
    return modules


def _same_directory(left: str, right: str) -> bool:
    return left.rsplit("/", maxsplit=1)[0] == right.rsplit("/", maxsplit=1)[0]


def _similar_source_terms(
    target: ParsedPythonFile,
    candidate: ParsedPythonFile,
) -> bool:
    return bool(_source_terms(target) & _source_terms(candidate))


def _source_terms(parsed: ParsedPythonFile) -> set[str]:
    terms: set[str] = set(parsed.module.replace(".", "_").split("_"))
    for symbol in parsed.symbols:
        terms.update(symbol.name.lower().split("_"))
    for reference in parsed.references:
        terms.update(reference.name.lower().split("_"))
    return {term for term in terms if len(term) >= MIN_RELATED_TERM_LENGTH}


def _related_file_payload(
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
