"""Read-only index/finding status counts for get_repo_status (bead P3.5 / U5).

These reads used to open raw sqlite3 connections from the transport layer,
bypassing the reader/writer lock and risking a mid-write view. They now go
through RepositoryStorage.read_connection so a status read waits for any
in-flight writer and never observes a half-written database.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codescent.storage import RepositoryStorage


@dataclass(frozen=True, slots=True)
class IndexStatusRepository:
    storage: RepositoryStorage

    def stored_hashes(self) -> dict[str, str]:
        try:
            with self.storage.read_connection() as connection:
                rows: list[tuple[str, str]] = connection.execute(
                    "select path, hash from files",
                ).fetchall()
        except sqlite3.DatabaseError:
            return {}
        return dict(rows)

    def finding_count(self) -> int:
        try:
            with self.storage.read_connection() as connection:
                rows: list[tuple[int]] = connection.execute(
                    "select id from findings",
                ).fetchall()
        except sqlite3.DatabaseError:
            return 0
        return len(rows)

    def unresolved_finding_count(self) -> int:
        """Open/regressed findings whose file location did not resolve.

        Keys on an empty ``file_path`` -- NOT ``file_id`` -- so by-design
        doc/generic findings (which legitimately have no file row) are never
        falsely flagged. A non-empty count means findings predate the file_path
        persistence fix and a rescan re-persists their path.
        """
        try:
            with self.storage.read_connection() as connection:
                rows: list[tuple[int]] = connection.execute(
                    """
                    select 1 from findings
                    where status in ('open', 'regressed')
                        and (file_path is null or file_path = '')
                    """,
                ).fetchall()
        except sqlite3.DatabaseError:
            return 0
        return len(rows)
