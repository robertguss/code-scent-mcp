from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from codescent.core.errors import CodeScentError, ErrorCode, ErrorSeverity
from codescent.core.paths import resolve_repo_root
from codescent.storage.schema import SCHEMA_VERSION, migrate

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

ACTIVE_WRITERS: Final[set[Path]] = set()
ACTIVE_READERS: Final[dict[Path, int]] = {}
ACTIVE_STORAGE_GUARD: Final = threading.Condition()
CONFIG_TEXT: Final = f"[project]\nschema_version = {SCHEMA_VERSION}\n"


@dataclass(frozen=True, slots=True)
class StorageState:
    repo_root: Path
    state_dir: Path
    database_path: Path
    config_path: Path


def initialize_storage(root: Path | str) -> StorageState:
    repo_root = resolve_repo_root(root)
    state = _state_for(repo_root)
    state.state_dir.mkdir(exist_ok=True)

    storage = RepositoryStorage(state)
    try:
        with storage.write_transaction() as connection:
            migrate(connection)
            quick_check_cursor: sqlite3.Cursor = connection.execute(
                "pragma quick_check",
            )
            quick_check_cursor.close()
    except sqlite3.DatabaseError as exc:
        raise CodeScentError(
            code=ErrorCode.CORRUPT_DATABASE,
            message=(
                "CodeScent database is corrupt; delete "
                ".codescent/index.sqlite to rebuild."
            ),
            severity=ErrorSeverity.ERROR,
            details={"database": str(state.database_path)},
        ) from exc

    _write_config_schema_version(state.config_path)
    return state


@dataclass(frozen=True, slots=True)
class RepositoryStorage:
    state: StorageState

    @contextmanager
    def read_connection(self) -> Generator[sqlite3.Connection, None, None]:
        self._claim_reader()
        connection = _connect(self.state.database_path)
        try:
            yield connection
        finally:
            connection.close()
            self._release_reader()

    @contextmanager
    def write_transaction(self) -> Generator[sqlite3.Connection, None, None]:
        self._claim_writer()
        connection = _connect(self.state.database_path)
        try:
            _ = connection.execute("begin immediate")
            yield connection
            connection.commit()
        except sqlite3.OperationalError as exc:
            connection.rollback()
            raise _concurrent_write_error(self.state.database_path) from exc
        except sqlite3.DatabaseError:
            connection.rollback()
            raise
        finally:
            connection.close()
            self._release_writer()

    def _claim_writer(self) -> None:
        with ACTIVE_STORAGE_GUARD:
            if (
                self.state.database_path in ACTIVE_WRITERS
                or ACTIVE_READERS.get(self.state.database_path, 0) > 0
            ):
                raise _concurrent_write_error(self.state.database_path)
            ACTIVE_WRITERS.add(self.state.database_path)

    def _release_writer(self) -> None:
        with ACTIVE_STORAGE_GUARD:
            ACTIVE_WRITERS.discard(self.state.database_path)
            ACTIVE_STORAGE_GUARD.notify_all()

    def _claim_reader(self) -> None:
        with ACTIVE_STORAGE_GUARD:
            while self.state.database_path in ACTIVE_WRITERS:
                _ = ACTIVE_STORAGE_GUARD.wait()
            ACTIVE_READERS[self.state.database_path] = (
                ACTIVE_READERS.get(self.state.database_path, 0) + 1
            )

    def _release_reader(self) -> None:
        with ACTIVE_STORAGE_GUARD:
            reader_count = ACTIVE_READERS.get(self.state.database_path, 0)
            if reader_count <= 1:
                _ = ACTIVE_READERS.pop(self.state.database_path, None)
                ACTIVE_STORAGE_GUARD.notify_all()
                return
            ACTIVE_READERS[self.state.database_path] = reader_count - 1


def _state_for(repo_root: Path) -> StorageState:
    state_dir = repo_root / ".codescent"
    return StorageState(
        repo_root=repo_root,
        state_dir=state_dir,
        database_path=state_dir / "index.sqlite",
        config_path=state_dir / "config.toml",
    )


def _write_config_schema_version(config_path: Path) -> None:
    if not config_path.exists():
        _ = config_path.write_text(CONFIG_TEXT)
        return

    lines = config_path.read_text().splitlines()
    updated_lines: list[str] = []
    found = False
    for line in lines:
        if line.startswith("schema_version = "):
            updated_lines.append(f"schema_version = {SCHEMA_VERSION}")
            found = True
        else:
            updated_lines.append(line)
    if not found:
        updated_lines.append(f"schema_version = {SCHEMA_VERSION}")
    _ = config_path.write_text("\n".join(updated_lines) + "\n")


def _connect(database_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path, timeout=5.0)
    _ = connection.execute("pragma foreign_keys = on")
    _ = connection.execute("pragma busy_timeout = 5000")
    return connection


def _concurrent_write_error(database_path: Path) -> CodeScentError:
    return CodeScentError(
        code=ErrorCode.CONCURRENT_WRITE,
        message="Another CodeScent write transaction is already active.",
        severity=ErrorSeverity.ERROR,
        details={"database": str(database_path)},
    )
