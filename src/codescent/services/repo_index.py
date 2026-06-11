from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from codescent.engine.inventory import build_file_inventory
from codescent.services.git import detect_git_state
from codescent.storage import RepositoryStorage, initialize_storage

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True, slots=True)
class IndexResult:
    indexed_files: int
    changed_files: tuple[str, ...]
    file_hashes: dict[str, str]
    git_available: bool
    git_status: str


@dataclass(frozen=True, slots=True)
class RepoIndexService:
    repo_root: Path | str

    def index_repo(self) -> IndexResult:
        state = initialize_storage(self.repo_root)
        inventory = build_file_inventory(state.repo_root)
        previous_hashes = _load_hashes(RepositoryStorage(state))
        now = datetime.now(UTC).isoformat()

        changed_files = tuple(
            item.path
            for item in inventory
            if previous_hashes.get(item.path) != item.hash
        )
        file_hashes = {item.path: item.hash for item in inventory}
        git_state = detect_git_state(state.repo_root)

        with RepositoryStorage(state).write_transaction() as connection:
            _ = connection.execute("delete from files")
            for item in inventory:
                _ = connection.execute(
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

        return IndexResult(
            indexed_files=len(inventory),
            changed_files=changed_files,
            file_hashes=file_hashes,
            git_available=git_state.available,
            git_status=git_state.status,
        )


def _load_hashes(storage: RepositoryStorage) -> dict[str, str]:
    with storage.read_connection() as connection:
        rows: list[tuple[str, str]] = connection.execute(
            "select path, hash from files",
        ).fetchall()
    return dict(rows)
