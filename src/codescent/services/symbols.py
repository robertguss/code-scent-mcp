from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from codescent.core.paths import normalize_repo_path, resolve_repo_root
from codescent.engine.inventory import build_file_inventory
from codescent.engine.packs import build_pack_registry
from codescent.services.config import ConfigService
from codescent.services.repo_index import RepoIndexService
from codescent.storage import RepositoryStorage, StorageState, initialize_storage

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Sequence
    from pathlib import Path

    from codescent.engine.parsers.python import ParsedPythonFile
    from codescent.services.context_support import SymbolMatchPayload

type PersistedSymbolRow = tuple[str, str, str, str, int, int, float]


@dataclass(frozen=True, slots=True)
class SymbolExtraction:
    files: tuple[ParsedPythonFile, ...]


@dataclass(frozen=True, slots=True)
class SymbolService:
    repo_root: Path | str

    def extract(self) -> SymbolExtraction:
        repo_root = resolve_repo_root(self.repo_root)
        config = ConfigService(repo_root).load()
        registry = build_pack_registry(config)
        parsed_files = tuple(
            parser(repo_root / item.path, item.path)
            for item in build_file_inventory(repo_root, config=config)
            for parser in (registry.parser_for_language(item.language),)
            if parser is not None
        )
        return SymbolExtraction(files=parsed_files)


def read_persisted_symbols(
    repo_root: Path | str,
    query: str,
    *,
    limit: int = 20,
) -> tuple[SymbolMatchPayload, ...]:
    bounded_limit = min(max(limit, 1), 20)
    state = ensure_symbols_indexed(repo_root)
    folded_query = f"%{query.lower()}%"
    with RepositoryStorage(state).read_connection() as connection:
        rows: list[PersistedSymbolRow] = connection.execute(
            """
            select
                symbols.name,
                symbols.qualified_name,
                symbols.kind,
                files.path,
                symbols.start_line,
                symbols.end_line,
                symbols.confidence
            from symbols
            join files on files.id = symbols.file_id
            where
                lower(symbols.name) like ?
                or lower(symbols.qualified_name) like ?
            order by files.path, symbols.start_line, symbols.qualified_name
            limit ?
            """,
            (folded_query, folded_query, bounded_limit),
        ).fetchall()
    return _symbol_rows_payload(rows)


def read_persisted_symbol(
    repo_root: Path | str,
    qualified_name: str,
) -> SymbolMatchPayload:
    state = ensure_symbols_indexed(repo_root)
    with RepositoryStorage(state).read_connection() as connection:
        row = cast(
            "PersistedSymbolRow | None",
            connection.execute(
                """
                select
                    symbols.name,
                    symbols.qualified_name,
                    symbols.kind,
                    files.path,
                    symbols.start_line,
                    symbols.end_line,
                    symbols.confidence
                from symbols
                join files on files.id = symbols.file_id
                where symbols.qualified_name = ?
                order by files.path, symbols.start_line
                limit 1
                """,
                (qualified_name,),
            ).fetchone(),
        )
    if row is None:
        raise LookupError(qualified_name)
    return _symbol_row_payload(row)


def read_persisted_file_symbols(
    repo_root: Path | str,
    path: str,
) -> tuple[SymbolMatchPayload, ...]:
    repo_path = resolve_repo_root(repo_root)
    relative_path = (
        normalize_repo_path(repo_path, path).relative_to(repo_path).as_posix()
    )
    state = ensure_symbols_indexed(repo_path)
    with RepositoryStorage(state).read_connection() as connection:
        rows: list[PersistedSymbolRow] = connection.execute(
            """
            select
                symbols.name,
                symbols.qualified_name,
                symbols.kind,
                files.path,
                symbols.start_line,
                symbols.end_line,
                symbols.confidence
            from symbols
            join files on files.id = symbols.file_id
            where files.path = ?
            order by symbols.start_line, symbols.qualified_name
            """,
            (relative_path,),
        ).fetchall()
    return _symbol_rows_payload(rows)


def ensure_symbols_indexed(repo_root: Path | str) -> StorageState:
    state = initialize_storage(repo_root)
    with RepositoryStorage(state).read_connection() as connection:
        if _indexed_file_count(connection) > 0:
            return state
    _ = RepoIndexService(state.repo_root).index_repo()
    return initialize_storage(state.repo_root)


def _indexed_file_count(connection: sqlite3.Connection) -> int:
    row = cast(
        "tuple[int] | None",
        connection.execute("select count(*) from files").fetchone(),
    )
    if row is None:
        return 0
    return int(row[0])


def _symbol_rows_payload(
    rows: Sequence[PersistedSymbolRow],
) -> tuple[SymbolMatchPayload, ...]:
    return tuple(_symbol_row_payload(row) for row in rows)


def _symbol_row_payload(row: PersistedSymbolRow) -> SymbolMatchPayload:
    name, qualified_name, kind, path, start_line, end_line, confidence = row
    return {
        "name": name,
        "qualified_name": qualified_name,
        "kind": kind,
        "path": path,
        "start_line": start_line,
        "end_line": end_line,
        "confidence": confidence,
    }
