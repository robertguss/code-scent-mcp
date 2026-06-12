from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from codescent.core.models import PageOptions
from codescent.core.paths import normalize_repo_path, resolve_repo_root
from codescent.engine.context import source_range
from codescent.services.context_support import (
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
    file_by_path,
    file_ranges,
    file_summary,
    find_qualified_symbol,
    graph_payload,
    import_text,
    imports_between,
    like,
    likely_tests,
    matches_symbol,
    related_file_payload,
    risk_notes,
    same_directory,
    similar_source_terms,
    symbol_payload,
)
from codescent.services.git import git_related_paths
from codescent.services.symbols import SymbolService
from codescent.storage import RepositoryStorage

if TYPE_CHECKING:
    from pathlib import Path

__all__ = [
    "ContextService",
    "GraphResultPayload",
    "RelatedFilePayload",
    "SymbolMatchPayload",
]


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
            symbol_payload(parsed, symbol)
            for parsed in files
            for symbol in parsed.symbols
            if matches_symbol(query, symbol)
        ]
        return tuple(matches[: min(max(limit, 1), 20)])

    def get_file_context(self, path: str) -> FileContextPayload:
        repo_root = resolve_repo_root(self.repo_root)
        relative_path = (
            normalize_repo_path(repo_root, path).relative_to(repo_root).as_posix()
        )
        files = SymbolService(repo_root).extract().files
        parsed = file_by_path(files, relative_path)
        tests = likely_tests(files, parsed)
        return {
            "path": parsed.path,
            "summary": file_summary(parsed),
            "symbols": tuple(symbol.name for symbol in parsed.symbols),
            "imports": tuple(
                import_text(imported.module, imported.name)
                for imported in parsed.imports
            ),
            "likely_tests": tests,
            "related_files": tests,
            "source_ranges": tuple(
                item.to_payload() for item in file_ranges(repo_root, parsed)
            ),
            "risk_notes": risk_notes(parsed),
            "next_tools": tuple(
                f"get_symbol_context:{symbol.qualified_name}"
                for symbol in parsed.symbols
            ),
        }

    def get_symbol_context(self, qualified_name: str) -> SymbolContextPayload:
        repo_root = resolve_repo_root(self.repo_root)
        files = SymbolService(repo_root).extract().files
        parsed, symbol = find_qualified_symbol(files, qualified_name)
        return {
            "symbol": symbol_payload(parsed, symbol),
            "likely_tests": likely_tests(files, parsed, symbol.name),
            "source_ranges": (
                source_range(
                    repo_root,
                    parsed.path,
                    start_line=symbol.start_line,
                    end_line=symbol.end_line,
                    line_cap=SOURCE_LINE_CAP,
                ).to_payload(),
            ),
            "risk_notes": risk_notes(parsed),
        }

    def find_references(
        self,
        query: str,
        *,
        limit: int = 20,
        cursor: int = 0,
    ) -> GraphToolPayload:
        page = PageOptions(limit=limit, offset=cursor)
        state = ensure_graph_indexed(self.repo_root)
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
        return graph_payload(query, rows, page)

    def find_callers(
        self,
        query: str,
        *,
        limit: int = 20,
        cursor: int = 0,
    ) -> GraphToolPayload:
        page = PageOptions(limit=limit, offset=cursor)
        state = ensure_graph_indexed(self.repo_root)
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
                (like(query), page.limit + 1, page.offset),
            ).fetchall()
        return graph_payload(query, rows, page)

    def find_callees(
        self,
        query: str,
        *,
        limit: int = 20,
        cursor: int = 0,
    ) -> GraphToolPayload:
        page = PageOptions(limit=limit, offset=cursor)
        state = ensure_graph_indexed(self.repo_root)
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
                (like(query), like(query), page.limit + 1, page.offset),
            ).fetchall()
        return graph_payload(query, rows, page)

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
        target = file_by_path(files, relative_path)
        reasons: dict[str, set[str]] = {}

        for related_path in likely_tests(files, target):
            add_related_reason(reasons, related_path, "test_match")
        for candidate in files:
            if candidate.path == target.path:
                continue
            if imports_between(target, candidate):
                add_related_reason(reasons, candidate.path, "import_graph")
            if same_directory(target.path, candidate.path):
                add_related_reason(reasons, candidate.path, "directory_proximity")
            if similar_source_terms(target, candidate):
                add_related_reason(reasons, candidate.path, "search_similarity")
        for related_path in git_related_paths(repo_root, target.path):
            add_related_reason(reasons, related_path, "git_history")

        rows = _related_rows(reasons, target.path)
        visible_rows = rows[page.offset : page.offset + page.limit]
        next_cursor = (
            page.offset + page.limit if page.offset + page.limit < len(rows) else None
        )
        return {
            "path": target.path,
            "results": tuple(visible_rows),
            "next_cursor": next_cursor,
        }


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
