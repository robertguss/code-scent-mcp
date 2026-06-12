from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import TYPE_CHECKING, Final, TypedDict

from codescent.core.paths import resolve_repo_root
from codescent.engine.inventory import build_file_inventory
from codescent.services.config import ConfigService
from codescent.services.git import detect_git_state

if TYPE_CHECKING:
    from fastmcp import FastMCP

SAMPLE_FILE_LIMIT: Final = 20
CHANGED_FILE_LIMIT: Final = 20
ENTRYPOINT_NAMES: Final = frozenset({"__main__.py", "cli.py", "main.py"})


class RepoMapToolPayload(TypedDict):
    ok: bool
    read_only: bool
    file_count: int
    test_file_count: int
    languages: dict[str, int]
    top_level: tuple[str, ...]
    entrypoints: tuple[str, ...]
    sample_files: tuple[str, ...]


class RepoStatusToolPayload(TypedDict):
    ok: bool
    read_only: bool
    index_fresh: bool
    indexed_files: int
    changed_files: tuple[str, ...]
    finding_count: int
    database_ok: bool
    git_available: bool
    git_status: str


def register_repo_tools(mcp: FastMCP) -> None:
    _ = mcp.tool(
        description=(
            "Use CodeScent before broad grep or large reads to get a bounded "
            "repository map. This tool is read-only and returns paths/counts, "
            "never source content."
        ),
    )(get_repo_map)

    _ = mcp.tool(
        description=(
            "Use CodeScent before broad grep or large reads to inspect bounded "
            "repository status. This tool is read-only and does not create or "
            "modify CodeScent state."
        ),
    )(get_repo_status)


def get_repo_map(repo: str = ".") -> RepoMapToolPayload:
    repo_root = resolve_repo_root(repo)
    config = ConfigService(repo_root).load()
    inventory = build_file_inventory(repo_root, config=config)

    return {
        "ok": True,
        "read_only": True,
        "file_count": len(inventory),
        "test_file_count": sum(1 for item in inventory if item.is_test),
        "languages": _language_counts(tuple(item.language for item in inventory)),
        "top_level": _top_level(tuple(item.path for item in inventory)),
        "entrypoints": _entrypoints(tuple(item.path for item in inventory)),
        "sample_files": tuple(item.path for item in inventory[:SAMPLE_FILE_LIMIT]),
    }


def get_repo_status(repo: str = ".") -> RepoStatusToolPayload:
    repo_root = resolve_repo_root(repo)
    config = ConfigService(repo_root).load()
    inventory_hashes = {
        item.path: item.hash for item in build_file_inventory(repo_root, config=config)
    }
    database_path = repo_root / ".codescent" / "index.sqlite"
    stored_hashes = _stored_hashes(database_path)
    changed_files = _changed_files(inventory_hashes, stored_hashes)
    git_state = detect_git_state(repo_root)

    return {
        "ok": True,
        "read_only": True,
        "index_fresh": (
            database_path.exists()
            and len(changed_files) == 0
            and len(stored_hashes) == len(inventory_hashes)
        ),
        "indexed_files": len(stored_hashes),
        "changed_files": changed_files[:CHANGED_FILE_LIMIT],
        "finding_count": _finding_count(database_path),
        "database_ok": database_path.exists(),
        "git_available": git_state.available,
        "git_status": git_state.status,
    }


def _language_counts(languages: tuple[str, ...]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for language in languages:
        counts[language] = counts.get(language, 0) + 1
    return dict(sorted(counts.items()))


def _top_level(paths: tuple[str, ...]) -> tuple[str, ...]:
    names = {path.split("/", maxsplit=1)[0] for path in paths}
    return tuple(sorted(names))


def _entrypoints(paths: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(path for path in paths if Path(path).name in ENTRYPOINT_NAMES)


def _stored_hashes(database_path: Path) -> dict[str, str]:
    if not database_path.exists():
        return {}
    try:
        with closing(sqlite3.connect(database_path)) as connection:
            rows: list[tuple[str, str]] = connection.execute(
                "select path, hash from files",
            ).fetchall()
    except sqlite3.DatabaseError:
        return {}
    return dict(rows)


def _finding_count(database_path: Path) -> int:
    if not database_path.exists():
        return 0
    try:
        with closing(sqlite3.connect(database_path)) as connection:
            rows: list[tuple[int]] = connection.execute(
                "select id from findings",
            ).fetchall()
    except sqlite3.DatabaseError:
        return 0
    return len(rows)


def _changed_files(
    inventory_hashes: dict[str, str],
    stored_hashes: dict[str, str],
) -> tuple[str, ...]:
    modified_files = tuple(
        path
        for path, file_hash in inventory_hashes.items()
        if stored_hashes.get(path) != file_hash
    )
    deleted_files = tuple(
        path for path in stored_hashes if path not in inventory_hashes
    )
    return (*modified_files, *deleted_files)
