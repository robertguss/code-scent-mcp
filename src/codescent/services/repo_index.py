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

    from codescent.core.models import IndexedFile
    from codescent.engine.parsers.python import ParsedPythonFile, ParsedSymbol


@dataclass(frozen=True, slots=True)
class IndexResult:
    indexed_files: int
    changed_files: tuple[str, ...]
    file_hashes: dict[str, str]
    git_available: bool
    git_status: str
    deleted_files: tuple[str, ...] = ()
    reindexed_files: int = 0
    full: bool = False


@dataclass(slots=True)
class ReindexDebouncer:
    """Coalesce a burst of file changes into a single incremental reindex.

    Fed the current changed-file set on every poll, it fires (returns True)
    only once the set has stayed identical for ``window_seconds`` -- so a
    burst of edits collapses into one reindex instead of one per poll. An
    empty set (index already fresh) resets the window.
    """

    window_seconds: float
    _signature: tuple[str, ...] | None = None
    _stable_since: float | None = None

    def observe(self, changed: tuple[str, ...], now: float) -> bool:
        if not changed:
            self._signature = None
            self._stable_since = None
            return False
        if changed != self._signature:
            self._signature = changed
            self._stable_since = now
            return False
        if self._stable_since is not None and now - self._stable_since >= (
            self.window_seconds
        ):
            self._signature = None
            self._stable_since = None
            return True
        return False


class MissingRowIdError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RepoIndexService:
    repo_root: Path | str

    def index_repo(self, *, full: bool = False) -> IndexResult:
        """Persist the file graph for the repo.

        Incremental by default: only added/modified files are re-parsed and
        re-inserted, and rows for modified/deleted files are removed (FK
        cascade clears their symbols/imports/references/edges). Pass
        ``full=True`` to rebuild the whole index from scratch. Both paths
        produce an equivalent index for the same on-disk state — every graph
        row references only its own file, so per-file reindex == full reindex.
        """
        state = initialize_storage(self.repo_root)
        config = ConfigService(state.repo_root).load()
        inventory = build_file_inventory(state.repo_root, config=config)
        previous_hashes = _load_hashes(RepositoryStorage(state))
        now = datetime.now(UTC).isoformat()

        file_hashes = {item.path: item.hash for item in inventory}
        changed_files = tuple(
            item.path
            for item in inventory
            if previous_hashes.get(item.path) != item.hash
        )
        deleted_files = tuple(
            path for path in previous_hashes if path not in file_hashes
        )
        git_state = detect_git_state(state.repo_root)
        registry = build_pack_registry(config)

        if full:
            to_index: tuple[IndexedFile, ...] = inventory
        else:
            changed_set = set(changed_files)
            to_index = tuple(item for item in inventory if item.path in changed_set)

        with RepositoryStorage(state).write_transaction() as connection:
            if full:
                # FK on-delete-cascade clears symbols/imports/references/edges.
                _ = connection.execute("delete from files")
            else:
                # Stale rows = modified + deleted files; cascade clears their
                # graph. Unchanged files are left untouched; added files have
                # no prior row to remove.
                for path in previous_hashes:
                    if previous_hashes[path] != file_hashes.get(path):
                        _ = connection.execute(
                            "delete from files where path = ?",
                            (path,),
                        )
            for item in to_index:
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
            deleted_files=deleted_files,
            reindexed_files=len(to_index),
            full=full,
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

    for imported in parsed.imports:
        _ = connection.execute(
            """
            insert into imports (
                source_file_id,
                imported_path,
                imported_symbol,
                resolved_file_id,
                confidence
            ) values (?, ?, ?, ?, ?)
            """,
            (
                file_id,
                imported.module,
                imported.name,
                None,
                imported.confidence,
            ),
        )

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
