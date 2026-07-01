from __future__ import annotations

import builtins
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypedDict

from codescent.core.models import PageOptions
from codescent.core.paths import normalize_repo_path, resolve_repo_root
from codescent.engine.context import source_range
from codescent.services.cbm_backend import select_graph_backend
from codescent.services.context_support import (
    LOW_CONFIDENCE_THRESHOLD,
    MIN_RELATED_TERM_LENGTH,
    SOURCE_LINE_CAP,
    FileContextPayload,
    GraphResultPayload,
    GraphToolPayload,
    RelatedFilePayload,
    RelatedFilesPayload,
    SymbolContextPayload,
    SymbolMatchPayload,
    add_related_reason,
    ensure_graph_indexed,
    graph_payload,
    import_text,
    like,
    related_file_payload,
    same_directory,
)
from codescent.services.freshness import (
    CHANGED_FILE_LIMIT,
    AdvisoryConfidence,
    FreshnessMetadata,
    confidence_for_results,
    ensure_fresh_index,
    next_tools_with_refresh_recovery,
    warnings_for_results,
)
from codescent.services.git import (
    git_changed_paths,
    git_co_change_counts,
    git_related_paths,
)
from codescent.services.search_support import frecency_scores, recent_query_paths
from codescent.services.status import RepoStatusService
from codescent.services.symbols import (
    ensure_symbols_indexed,
    read_persisted_file_symbols,
    read_persisted_symbol,
    read_persisted_symbols,
)
from codescent.storage import RepositoryStorage

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from codescent.services.graph_backend import (
        CallEdge,
        GraphBackend,
        SymbolNode,
    )

type PersistedFileRow = tuple[str, int]
type CallerRow = tuple[str, str, int, float, str | None]
type PersistedImportRow = tuple[str, str | None]
type PersistedTextRow = tuple[str, str]
type GraphRow = tuple[str, str, int, float] | tuple[str, str, int, float, str | None]

# Cap `get_file_context.related_files` at the same page size `get_related_files`
# uses, so the tool stays "cheaper than reading the file" instead of dumping the
# whole repo. The tail is reachable via `related_files_next_cursor`.
RELATED_FILE_LIMIT = 20

# Common built-in-type methods that read as callee noise (`x.append(...)` stores
# call_text "append"). Unioned with `dir(builtins)` to filter language builtins
# out of `find_callees` (R8). This is a native-path floor, case-folded against
# `call_edges.call_text`; cbm's real call graph avoids builtins structurally.
_BUILTIN_CALLEE_METHODS = frozenset(
    {
        "append",
        "extend",
        "insert",
        "remove",
        "pop",
        "add",
        "update",
        "discard",
        "get",
        "setdefault",
        "items",
        "keys",
        "values",
        "join",
        "split",
        "rsplit",
        "splitlines",
        "strip",
        "lstrip",
        "rstrip",
        "format",
        "replace",
        "startswith",
        "endswith",
        "lower",
        "upper",
        "title",
        "encode",
        "decode",
        "count",
        "index",
        "sort",
        "copy",
        "clear",
    },
)
PYTHON_BUILTIN_CALLEES = (
    frozenset(name.lower() for name in dir(builtins)) | _BUILTIN_CALLEE_METHODS
)
_BUILTIN_CALLEE_PLACEHOLDERS = ", ".join("?" * len(PYTHON_BUILTIN_CALLEES))
_BUILTIN_CALLEE_PARAMS = tuple(sorted(PYTHON_BUILTIN_CALLEES))

__all__ = [
    "ContextService",
    "GraphResultPayload",
    "RelatedFilePayload",
    "SymbolMatchPayload",
]


class FreshnessFields(TypedDict):
    warnings: tuple[str, ...]
    confidence: AdvisoryConfidence
    index_fresh: bool
    index_was_stale: bool
    auto_refreshed: bool
    changed_files: tuple[str, ...]
    refresh_error: str | None


@dataclass(frozen=True, slots=True)
class ContextService:
    repo_root: Path | str
    auto_refresh: bool = True

    def find_symbol(
        self,
        query: str,
        *,
        limit: int = 20,
    ) -> tuple[SymbolMatchPayload, ...]:
        repo_root = resolve_repo_root(self.repo_root)
        _ = _freshness_for_service(repo_root, auto_refresh=self.auto_refresh)
        return read_persisted_symbols(repo_root, query, limit=limit)

    def get_file_context(
        self,
        path: str,
        *,
        related_cursor: int = 0,
    ) -> FileContextPayload:
        repo_root = resolve_repo_root(self.repo_root)
        freshness = _freshness_for_service(
            repo_root,
            auto_refresh=self.auto_refresh,
        )
        relative_path = (
            normalize_repo_path(repo_root, path).relative_to(repo_root).as_posix()
        )
        if not _persisted_file_exists(repo_root, relative_path):
            raise LookupError(relative_path)
        symbols = read_persisted_file_symbols(repo_root, relative_path)
        imports = _persisted_file_imports(repo_root, relative_path)
        tests = _persisted_file_likely_tests(repo_root, relative_path)
        related_rows = _related_rows(
            _persisted_related_reason_map(repo_root, relative_path, tests),
            relative_path,
        )
        related_page = related_rows[
            related_cursor : related_cursor + RELATED_FILE_LIMIT
        ]
        related_next_cursor = (
            related_cursor + RELATED_FILE_LIMIT
            if related_cursor + RELATED_FILE_LIMIT < len(related_rows)
            else None
        )
        return {
            "path": relative_path,
            "summary": _persisted_file_summary(relative_path, symbols),
            "symbols": tuple(symbol["name"] for symbol in symbols),
            "imports": tuple(import_text(module, name) for module, name in imports),
            "likely_tests": tests,
            "related_files": tuple(item["path"] for item in related_page),
            "related_files_next_cursor": related_next_cursor,
            "source_ranges": tuple(
                source_range(
                    repo_root,
                    symbol["path"],
                    start_line=symbol["start_line"],
                    end_line=symbol["end_line"],
                    line_cap=SOURCE_LINE_CAP,
                ).to_payload()
                for symbol in symbols[:2]
            ),
            "risk_notes": _persisted_risk_notes(repo_root, relative_path),
            "next_tools": tuple(
                f"get_symbol_context:{symbol['qualified_name']}" for symbol in symbols
            ),
            **_freshness_payload(freshness, has_results=bool(symbols)),
        }

    def get_symbol_context(self, qualified_name: str) -> SymbolContextPayload:
        repo_root = resolve_repo_root(self.repo_root)
        freshness = _freshness_for_service(
            repo_root,
            auto_refresh=self.auto_refresh,
        )
        symbol = read_persisted_symbol(repo_root, qualified_name)
        return {
            "symbol": symbol,
            "likely_tests": _persisted_likely_tests(repo_root, symbol["name"]),
            "source_ranges": (
                source_range(
                    repo_root,
                    symbol["path"],
                    start_line=symbol["start_line"],
                    end_line=symbol["end_line"],
                    line_cap=SOURCE_LINE_CAP,
                ).to_payload(),
            ),
            "risk_notes": _persisted_risk_notes(repo_root, symbol["path"]),
            **_freshness_payload(freshness, has_results=True),
        }

    def find_references(
        self,
        query: str,
        *,
        limit: int = 20,
        cursor: int = 0,
    ) -> GraphToolPayload:
        page = PageOptions(limit=limit, offset=cursor)
        repo_root = resolve_repo_root(self.repo_root)
        freshness = _freshness_for_service(
            repo_root,
            auto_refresh=self.auto_refresh,
        )
        state = ensure_graph_indexed(repo_root)
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
                (like(query), page.limit + 1, page.offset),
            ).fetchall()
        return _graph_payload(query, rows, page, freshness=freshness)

    def find_callers(
        self,
        query: str,
        *,
        limit: int = 20,
        cursor: int = 0,
    ) -> GraphToolPayload:
        page = PageOptions(limit=limit, offset=cursor)
        repo_root = resolve_repo_root(self.repo_root)
        freshness = _freshness_for_service(
            repo_root,
            auto_refresh=self.auto_refresh,
        )
        backend = select_graph_backend(repo_root)
        if backend.name() == "cbm":
            ranked = _cbm_caller_rows(backend, query)
            rows: list[CallerRow] = ranked[page.offset : page.offset + page.limit + 1]
        else:
            state = ensure_graph_indexed(repo_root)
            with RepositoryStorage(state).read_connection() as connection:
                rows = connection.execute(
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
                    (like(query), page.limit + 1, page.offset),
                ).fetchall()
        return _graph_payload(query, rows, page, freshness=freshness)

    def find_callees(
        self,
        query: str,
        *,
        limit: int = 20,
        cursor: int = 0,
    ) -> GraphToolPayload:
        page = PageOptions(limit=limit, offset=cursor)
        repo_root = resolve_repo_root(self.repo_root)
        freshness = _freshness_for_service(
            repo_root,
            auto_refresh=self.auto_refresh,
        )
        backend = select_graph_backend(repo_root)
        if backend.name() == "cbm":
            ranked = _cbm_callee_rows(backend, query)
            rows: list[CallerRow] = ranked[page.offset : page.offset + page.limit + 1]
        else:
            state = ensure_graph_indexed(repo_root)
            with RepositoryStorage(state).read_connection() as connection:
                rows = connection.execute(
                    f"""
                    select
                        call_edges.call_text,
                        files.path,
                        call_edges.start_line,
                        call_edges.confidence,
                        symbols.qualified_name
                    from call_edges
                    join files on files.id = call_edges.source_file_id
                    left join symbols on symbols.id = call_edges.caller_symbol_id
                    where (
                        lower(symbols.name) like ?
                        or lower(symbols.qualified_name) like ?
                    )
                    and lower(call_edges.call_text) not in (
                        {_BUILTIN_CALLEE_PLACEHOLDERS}
                    )
                    order by files.path, call_edges.start_line
                    limit ? offset ?
                    """,  # noqa: S608 - placeholders are a fixed builtins constant.
                    (
                        like(query),
                        like(query),
                        *_BUILTIN_CALLEE_PARAMS,
                        page.limit + 1,
                        page.offset,
                    ),
                ).fetchall()
        return _graph_payload(query, rows, page, freshness=freshness)

    def get_related_files(
        self,
        path: str,
        *,
        limit: int = 20,
        cursor: int = 0,
    ) -> RelatedFilesPayload:
        page = PageOptions(limit=limit, offset=cursor)
        repo_root = resolve_repo_root(self.repo_root)
        freshness = _freshness_for_service(
            repo_root,
            auto_refresh=self.auto_refresh,
        )
        relative_path = (
            normalize_repo_path(repo_root, path).relative_to(repo_root).as_posix()
        )
        if not _persisted_file_exists(repo_root, relative_path):
            raise LookupError(relative_path)
        reasons = _persisted_related_reason_map(
            repo_root,
            relative_path,
            _persisted_file_likely_tests(repo_root, relative_path),
        )
        _apply_personal_signals(repo_root, reasons)

        rows = _related_rows(reasons, relative_path)
        visible_rows = rows[page.offset : page.offset + page.limit]
        next_cursor = (
            page.offset + page.limit if page.offset + page.limit < len(rows) else None
        )
        return {
            "path": relative_path,
            "results": tuple(visible_rows),
            "next_cursor": next_cursor,
            "warnings": warnings_for_results(
                has_results=bool(visible_rows),
                result_kind="related files",
                freshness=freshness,
            ),
            "confidence": confidence_for_results(
                has_results=bool(visible_rows),
                freshness=freshness,
            ),
            "next_tools": next_tools_with_refresh_recovery(
                ("search_files", "search_content", "get_repo_map"),
                freshness,
            ),
            "index_fresh": freshness.index_fresh,
            "index_was_stale": freshness.index_was_stale,
            "auto_refreshed": freshness.auto_refreshed,
            "changed_files": freshness.changed_files,
            "refresh_error": freshness.refresh_error,
        }


def _symbols_by_path(
    symbols: tuple[SymbolNode, ...],
) -> dict[str, list[SymbolNode]]:
    grouped: dict[str, list[SymbolNode]] = {}
    for symbol in symbols:
        grouped.setdefault(symbol.path, []).append(symbol)
    return grouped


def _enclosing_symbol(
    edge: CallEdge,
    symbols_by_path: dict[str, list[SymbolNode]],
) -> SymbolNode | None:
    """The innermost symbol whose line range contains ``edge``'s call site.

    cbm ``CallEdge`` records the calling *file* and line but not the calling
    symbol; the enclosing symbol is recovered from the symbol table's line
    ranges (innermost wins for nested defs).
    """
    candidates = [
        symbol
        for symbol in symbols_by_path.get(edge.caller_path, ())
        if symbol.start_line <= edge.start_line <= symbol.end_line
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda symbol: symbol.start_line)


def _cbm_caller_rows(backend: GraphBackend, query: str) -> list[CallerRow]:
    """cbm-sourced "who calls ``query``" rows, shaped like the native payload."""
    needle = query.lower()
    symbols_by_path = _symbols_by_path(backend.symbols())
    rows: list[CallerRow] = []
    for edge in backend.call_edges():
        if needle not in edge.callee_name.lower():
            continue
        caller = _enclosing_symbol(edge, symbols_by_path)
        rows.append(
            (
                edge.callee_name,
                edge.caller_path,
                edge.start_line,
                edge.confidence,
                caller.qualified_name if caller is not None else None,
            ),
        )
    rows.sort(key=lambda row: (row[1], row[2]))
    return rows


def _cbm_callee_rows(backend: GraphBackend, query: str) -> list[CallerRow]:
    """cbm-sourced "what ``query`` calls" rows, builtins filtered (U6 floor).

    Each edge is attributed to its single innermost enclosing symbol (mirroring
    the native path's join on one ``caller_symbol_id``); matching the query
    against every *containing* symbol instead would emit a nested method's call
    once per enclosing class too, over-reporting and diverging from native.
    """
    needle = query.lower()
    symbols_by_path = _symbols_by_path(backend.symbols())
    rows: list[CallerRow] = []
    for edge in backend.call_edges():
        if edge.callee_name.lower() in PYTHON_BUILTIN_CALLEES:
            continue
        caller = _enclosing_symbol(edge, symbols_by_path)
        if caller is None:
            continue
        if (
            needle not in caller.name.lower()
            and needle not in caller.qualified_name.lower()
        ):
            continue
        rows.append(
            (
                edge.callee_name,
                edge.caller_path,
                edge.start_line,
                edge.confidence,
                caller.qualified_name,
            ),
        )
    rows.sort(key=lambda row: (row[1], row[2]))
    return rows


def _freshness_for_service(repo_root: Path, *, auto_refresh: bool) -> FreshnessMetadata:
    if auto_refresh:
        return ensure_fresh_index(repo_root)
    status = RepoStatusService(repo_root).get_status()
    return FreshnessMetadata(
        index_fresh=status.index_fresh,
        index_was_stale=not status.index_fresh,
        auto_refreshed=False,
        changed_files=status.changed_files[:CHANGED_FILE_LIMIT],
    )


def _freshness_payload(
    freshness: FreshnessMetadata,
    *,
    has_results: bool,
) -> FreshnessFields:
    return {
        "warnings": warnings_for_results(
            has_results=has_results,
            result_kind="context results",
            freshness=freshness,
        ),
        "confidence": confidence_for_results(
            has_results=has_results,
            freshness=freshness,
        ),
        "index_fresh": freshness.index_fresh,
        "index_was_stale": freshness.index_was_stale,
        "auto_refreshed": freshness.auto_refreshed,
        "changed_files": freshness.changed_files,
        "refresh_error": freshness.refresh_error,
    }


def _graph_payload(
    query: str,
    rows: Sequence[GraphRow],
    page: PageOptions,
    *,
    freshness: FreshnessMetadata,
) -> GraphToolPayload:
    payload = graph_payload(query, rows, page)
    has_results = bool(payload["results"])
    return {
        **payload,
        "warnings": warnings_for_results(
            has_results=has_results,
            result_kind="graph results",
            freshness=freshness,
        ),
        "confidence": confidence_for_results(
            has_results=has_results,
            freshness=freshness,
        ),
        "next_tools": next_tools_with_refresh_recovery(
            ("search_files", "search_content", "get_repo_map"),
            freshness,
        ),
        "index_fresh": freshness.index_fresh,
        "index_was_stale": freshness.index_was_stale,
        "auto_refreshed": freshness.auto_refreshed,
        "changed_files": freshness.changed_files,
        "refresh_error": freshness.refresh_error,
    }


def _persisted_file_exists(repo_root: Path, path: str) -> bool:
    state = ensure_symbols_indexed(repo_root)
    with RepositoryStorage(state).read_connection() as connection:
        rows: list[tuple[int]] = connection.execute(
            """
            select 1
            from files
            where path = ?
            limit 1
            """,
            (path,),
        ).fetchall()
    return bool(rows)


def _persisted_file_imports(
    repo_root: Path, path: str
) -> tuple[PersistedImportRow, ...]:
    state = ensure_symbols_indexed(repo_root)
    with RepositoryStorage(state).read_connection() as connection:
        rows: list[PersistedImportRow] = connection.execute(
            """
            select imports.imported_path, imports.imported_symbol
            from imports
            join files on files.id = imports.source_file_id
            where files.path = ?
            order by imports.id
            """,
            (path,),
        ).fetchall()
    return tuple(rows)


def _persisted_file_summary(
    path: str,
    symbols: tuple[SymbolMatchPayload, ...],
) -> str:
    symbol_names = ", ".join(symbol["name"] for symbol in symbols) or "no symbols"
    return f"{path} defines {symbol_names}."


def _persisted_file_likely_tests(repo_root: Path, path: str) -> tuple[str, ...]:
    module = _module_name(path)
    module_tail = module.rsplit(".", maxsplit=1)[-1]
    candidates: list[str] = []
    for candidate_path, imported_modules in _persisted_imports_by_path(
        repo_root,
        test_only=True,
    ).items():
        if module in imported_modules or module_tail in candidate_path:
            candidates.append(candidate_path)
    return tuple(sorted(dict.fromkeys(candidates)))


def _persisted_related_reason_map(
    repo_root: Path,
    target_path: str,
    likely_test_paths: tuple[str, ...],
) -> dict[str, set[str]]:
    reasons: dict[str, set[str]] = {}
    target_module = _module_name(target_path)
    imports_by_path = _persisted_imports_by_path(repo_root)
    target_imports = imports_by_path.get(target_path, set())
    symbols_by_path = _persisted_symbols_by_path(repo_root)
    references_by_path = _persisted_references_by_path(repo_root)
    target_terms = _persisted_source_terms(
        target_path,
        symbols_by_path=symbols_by_path,
        references_by_path=references_by_path,
    )

    for related_path in likely_test_paths:
        add_related_reason(reasons, related_path, "test_match")
    for candidate_path, _is_test in _persisted_file_rows(repo_root):
        if candidate_path == target_path:
            continue
        candidate_imports = imports_by_path.get(candidate_path, set())
        if (
            _module_name(candidate_path) in target_imports
            or target_module in candidate_imports
        ):
            add_related_reason(reasons, candidate_path, "import_graph")
        if same_directory(target_path, candidate_path):
            add_related_reason(reasons, candidate_path, "directory_proximity")
        candidate_terms = _persisted_source_terms(
            candidate_path,
            symbols_by_path=symbols_by_path,
            references_by_path=references_by_path,
        )
        if target_terms & candidate_terms:
            add_related_reason(reasons, candidate_path, "search_similarity")
    for related_path in git_related_paths(repo_root, target_path):
        add_related_reason(reasons, related_path, "git_history")
    for related_path, _count in git_co_change_counts(repo_root, target_path):
        add_related_reason(reasons, related_path, "co_change")

    return reasons


def _persisted_file_rows(repo_root: Path) -> tuple[PersistedFileRow, ...]:
    state = ensure_symbols_indexed(repo_root)
    with RepositoryStorage(state).read_connection() as connection:
        rows: list[PersistedFileRow] = connection.execute(
            """
            select path, is_test
            from files
            order by path
            """,
        ).fetchall()
    return tuple(rows)


def _persisted_imports_by_path(
    repo_root: Path,
    *,
    test_only: bool = False,
) -> dict[str, set[str]]:
    state = ensure_symbols_indexed(repo_root)
    with RepositoryStorage(state).read_connection() as connection:
        if test_only:
            rows: list[PersistedTextRow] = connection.execute(
                """
                select files.path, imports.imported_path
                from imports
                join files on files.id = imports.source_file_id
                where files.is_test = 1
                order by files.path, imports.id
                """,
            ).fetchall()
        else:
            rows = connection.execute(
                """
                select files.path, imports.imported_path
                from imports
                join files on files.id = imports.source_file_id
                order by files.path, imports.id
                """,
            ).fetchall()
    imports_by_path: dict[str, set[str]] = {}
    for source_path, imported_path in rows:
        imports_by_path.setdefault(source_path, set()).add(
            _normalized_import_module(imported_path),
        )
    return imports_by_path


def _persisted_symbols_by_path(repo_root: Path) -> dict[str, set[str]]:
    state = ensure_symbols_indexed(repo_root)
    with RepositoryStorage(state).read_connection() as connection:
        rows: list[PersistedTextRow] = connection.execute(
            """
            select files.path, symbols.name
            from symbols
            join files on files.id = symbols.file_id
            order by files.path, symbols.name
            """,
        ).fetchall()
    symbols_by_path: dict[str, set[str]] = {}
    for path, symbol_name in rows:
        symbols_by_path.setdefault(path, set()).add(symbol_name)
    return symbols_by_path


def _persisted_references_by_path(repo_root: Path) -> dict[str, set[str]]:
    state = ensure_symbols_indexed(repo_root)
    with RepositoryStorage(state).read_connection() as connection:
        rows: list[PersistedTextRow] = connection.execute(
            """
            select files.path, symbol_references.reference_text
            from symbol_references
            join files on files.id = symbol_references.source_file_id
            order by files.path, symbol_references.reference_text
            """,
        ).fetchall()
    references_by_path: dict[str, set[str]] = {}
    for path, reference_text in rows:
        references_by_path.setdefault(path, set()).add(reference_text)
    return references_by_path


def _persisted_source_terms(
    path: str,
    *,
    symbols_by_path: dict[str, set[str]],
    references_by_path: dict[str, set[str]],
) -> set[str]:
    terms: set[str] = set(_module_name(path).replace(".", "_").split("_"))
    for symbol_name in symbols_by_path.get(path, set()):
        terms.update(symbol_name.lower().split("_"))
    for reference_text in references_by_path.get(path, set()):
        terms.update(reference_text.lower().split("_"))
    return {term for term in terms if len(term) >= MIN_RELATED_TERM_LENGTH}


def _module_name(path: str) -> str:
    without_suffix = path.rsplit(".", maxsplit=1)[0]
    raw_parts = tuple(part for part in without_suffix.split("/") if part)
    if path.endswith((".py", ".pyi")):
        python_parts = tuple(part for part in raw_parts if part != "__init__")
        parts = python_parts[1:] if python_parts[:1] == ("src",) else python_parts
        return ".".join(parts)
    return ".".join(raw_parts)


def _normalized_import_module(module: str) -> str:
    return module.lstrip(".")


def _persisted_likely_tests(repo_root: Path, symbol_name: str) -> tuple[str, ...]:
    state = ensure_symbols_indexed(repo_root)
    with RepositoryStorage(state).read_connection() as connection:
        rows: list[tuple[str]] = connection.execute(
            """
            select distinct files.path
            from files
            join symbol_references
                on symbol_references.source_file_id = files.id
            where files.is_test = 1
                and symbol_references.reference_text = ?
            order by files.path
            """,
            (symbol_name,),
        ).fetchall()
    return tuple(path for (path,) in rows)


def _persisted_risk_notes(repo_root: Path, path: str) -> tuple[str, ...]:
    state = ensure_symbols_indexed(repo_root)
    with RepositoryStorage(state).read_connection() as connection:
        low_confidence_rows: list[tuple[int]] = connection.execute(
            """
            select 1
            from symbol_references
            join files on files.id = symbol_references.source_file_id
            where files.path = ?
                and symbol_references.confidence < ?
            limit 1
            """,
            (path, LOW_CONFIDENCE_THRESHOLD),
        ).fetchall()
    if low_confidence_rows:
        return ("low-confidence references omitted from caller/callee claims",)
    return ()


def _apply_personal_signals(repo_root: Path, reasons: dict[str, set[str]]) -> None:
    """Float up already-related files THIS developer is touching.

    Adds the frecency / query-history / git-status reasons to existing related
    paths so a recently or frequently touched (or git-modified) related file
    ranks above an equally-related untouched one. Never introduces unrelated
    paths; a cold/missing store is a no-op (neutral).
    """
    if not reasons:
        return
    git_modified = git_changed_paths(repo_root)
    recent_queries = recent_query_paths(repo_root)
    frecency = frecency_scores(repo_root)
    for path in list(reasons):
        if path in git_modified:
            add_related_reason(reasons, path, "git_modified")
        if path in recent_queries:
            add_related_reason(reasons, path, "recent_query")
        if frecency.get(path, 0.0) > 0:
            add_related_reason(reasons, path, "frecency")


def _related_rows(
    reasons: dict[str, set[str]],
    target_path: str,
) -> list[RelatedFilePayload]:
    return sorted(
        (
            related_file_payload(path=item_path, reasons=item_reasons)
            for item_path, item_reasons in reasons.items()
            if item_path != target_path
        ),
        key=lambda item: (-item["confidence"], item["path"]),
    )
