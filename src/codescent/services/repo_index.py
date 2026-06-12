from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from codescent.engine.inventory import build_file_inventory
from codescent.engine.packs import build_pack_registry
from codescent.services.config import ConfigService
from codescent.services.git import detect_git_state
from codescent.storage import RepositoryStorage, initialize_storage

if TYPE_CHECKING:
    import sqlite3
    from pathlib import Path

    from codescent.engine.parsers.python import ParsedPythonFile, ParsedSymbol


@dataclass(frozen=True, slots=True)
class IndexResult:
    indexed_files: int
    changed_files: tuple[str, ...]
    file_hashes: dict[str, str]
    git_available: bool
    git_status: str


class MissingRowIdError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RepoIndexService:
    repo_root: Path | str

    def index_repo(self) -> IndexResult:
        state = initialize_storage(self.repo_root)
        config = ConfigService(state.repo_root).load()
        inventory = build_file_inventory(state.repo_root, config=config)
        previous_hashes = _load_hashes(RepositoryStorage(state))
        now = datetime.now(UTC).isoformat()

        changed_files = tuple(
            item.path
            for item in inventory
            if previous_hashes.get(item.path) != item.hash
        )
        file_hashes = {item.path: item.hash for item in inventory}
        git_state = detect_git_state(state.repo_root)
        registry = build_pack_registry(config)

        with RepositoryStorage(state).write_transaction() as connection:
            _ = connection.execute("delete from files")
            _ = connection.execute("delete from symbols")
            _ = connection.execute("delete from symbol_references")
            _ = connection.execute("delete from call_edges")
            for item in inventory:
                cursor = connection.execute(
                    """
                    insert into files (
                        path,
                        language,
                        hash,
                        size_bytes,
                        line_count,
                        git_status,
                        is_generated,
                        is_test,
                        last_indexed_at
                    ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item.path,
                        item.language,
                        item.hash,
                        item.size_bytes,
                        item.line_count,
                        git_state.status,
                        int(item.is_generated),
                        int(item.is_test),
                        now,
                    ),
                )
                file_id = _lastrowid(cursor)
                parser = registry.parser_for_language(item.language)
                if parser is not None:
                    parsed = parser(state.repo_root / item.path, item.path)
                    _persist_python_graph(
                        connection=connection,
                        file_id=file_id,
                        parsed=parsed,
                    )

        return IndexResult(
            indexed_files=len(inventory),
            changed_files=changed_files,
            file_hashes=file_hashes,
            git_available=git_state.available,
            git_status=git_state.status,
        )


def _persist_python_graph(
    *,
    connection: sqlite3.Connection,
    file_id: int,
    parsed: ParsedPythonFile,
) -> None:
    symbol_ids: dict[str, int] = {}
    for symbol in parsed.symbols:
        cursor = connection.execute(
            """
            insert into symbols (
                file_id,
                name,
                qualified_name,
                kind,
                start_line,
                end_line,
                confidence
            ) values (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                file_id,
                symbol.name,
                symbol.qualified_name,
                symbol.kind,
                symbol.start_line,
                symbol.end_line,
                symbol.confidence,
            ),
        )
        symbol_ids[symbol.qualified_name] = _lastrowid(cursor)

    for reference in parsed.references:
        _ = connection.execute(
            """
            insert into symbol_references (
                source_file_id,
                target_file_id,
                reference_text,
                start_line,
                end_line,
                confidence
            ) values (?, ?, ?, ?, ?, ?)
            """,
            (
                file_id,
                file_id,
                reference.name,
                reference.line,
                reference.line,
                reference.confidence,
            ),
        )
        caller_symbol_id = _caller_symbol_id(parsed.symbols, symbol_ids, reference.line)
        _ = connection.execute(
            """
            insert into call_edges (
                caller_symbol_id,
                source_file_id,
                target_file_id,
                call_text,
                start_line,
                confidence
            ) values (?, ?, ?, ?, ?, ?)
            """,
            (
                caller_symbol_id,
                file_id,
                file_id,
                reference.name,
                reference.line,
                reference.confidence,
            ),
        )


def _caller_symbol_id(
    symbols: tuple[ParsedSymbol, ...],
    symbol_ids: dict[str, int],
    line: int,
) -> int | None:
    matching = [
        symbol for symbol in symbols if symbol.start_line <= line <= symbol.end_line
    ]
    if not matching:
        return None
    symbol = sorted(matching, key=lambda item: item.start_line, reverse=True)[0]
    return symbol_ids.get(symbol.qualified_name)


def _lastrowid(cursor: sqlite3.Cursor) -> int:
    row_id = cursor.lastrowid
    if row_id is None:
        raise MissingRowIdError
    return row_id


def _load_hashes(storage: RepositoryStorage) -> dict[str, str]:
    with storage.read_connection() as connection:
        rows: list[tuple[str, str]] = connection.execute(
            "select path, hash from files",
        ).fetchall()
    return dict(rows)
