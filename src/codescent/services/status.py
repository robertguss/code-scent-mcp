from dataclasses import dataclass
from pathlib import Path

from pydantic import TypeAdapter

from codescent.engine.inventory import build_file_inventory
from codescent.services.git import detect_git_state
from codescent.storage import RepositoryStorage, initialize_storage

COUNT_ROW: TypeAdapter[tuple[int] | None] = TypeAdapter(tuple[int] | None)


@dataclass(frozen=True, slots=True)
class RepoIndexStatus:
    index_fresh: bool
    indexed_files: int
    changed_files: tuple[str, ...]
    finding_count: int
    database_ok: bool
    git_available: bool
    git_status: str


@dataclass(frozen=True, slots=True)
class RepoStatusService:
    repo_root: Path | str

    def get_status(self) -> RepoIndexStatus:
        state = initialize_storage(self.repo_root)
        inventory_hashes = {
            item.path: item.hash for item in build_file_inventory(state.repo_root)
        }
        stored_hashes = _load_hashes(RepositoryStorage(state))
        modified_files = tuple(
            path
            for path, file_hash in inventory_hashes.items()
            if stored_hashes.get(path) != file_hash
        )
        deleted_files = tuple(
            path for path in stored_hashes if path not in inventory_hashes
        )
        changed_files = (*modified_files, *deleted_files)
        git_state = detect_git_state(state.repo_root)

        return RepoIndexStatus(
            index_fresh=(
                len(changed_files) == 0 and len(stored_hashes) == len(inventory_hashes)
            ),
            indexed_files=len(stored_hashes),
            changed_files=changed_files,
            finding_count=_finding_count(RepositoryStorage(state)),
            database_ok=True,
            git_available=git_state.available,
            git_status=git_state.status,
        )


def _load_hashes(storage: RepositoryStorage) -> dict[str, str]:
    with storage.read_connection() as connection:
        rows: list[tuple[str, str]] = connection.execute(
            "select path, hash from files",
        ).fetchall()
    return dict(rows)


def _finding_count(storage: RepositoryStorage) -> int:
    with storage.read_connection() as connection:
        row = COUNT_ROW.validate_python(
            connection.execute(
                "select count(*) from findings where status != 'resolved'",
            ).fetchone(),
        )
    if row is None:
        return 0
    return row[0]
