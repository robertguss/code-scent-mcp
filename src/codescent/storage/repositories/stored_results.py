from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from codescent.storage import RepositoryStorage


@dataclass(frozen=True, slots=True)
class StoredResultCreate:
    project_id: str
    tool_name: str
    input_json: str
    raw_result_json: str
    summary_json: str | None = None
    session_id: str | None = None
    content_type: str | None = None
    raw_token_estimate: int | None = None
    returned_token_estimate: int | None = None
    created_at: datetime | None = None
    expires_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class StoredResultRow:
    id: str
    project_id: str
    session_id: str | None
    tool_name: str
    input_json: str
    raw_result_json: str
    summary_json: str | None
    content_type: str | None
    raw_token_estimate: int | None
    returned_token_estimate: int | None
    created_at: str
    expires_at: str | None
    retrieval_count: int


@dataclass(frozen=True, slots=True)
class StoredResultSummaryRow:
    id: str
    project_id: str
    session_id: str | None
    tool_name: str
    summary_json: str
    raw_token_estimate: int | None
    returned_token_estimate: int | None
    created_at: str
    expires_at: str | None
    retrieval_count: int


@dataclass(frozen=True, slots=True)
class StoredResultRepository:
    storage: RepositoryStorage

    def create_result(self, request: StoredResultCreate) -> StoredResultRow:
        created = _timestamp(request.created_at or datetime.now(UTC))
        expires = _optional_timestamp(request.expires_at)
        result_id = _result_id(
            project_id=request.project_id,
            tool_name=request.tool_name,
            input_json=request.input_json,
            raw_result_json=request.raw_result_json,
            created_at=created,
        )
        with self.storage.write_transaction() as connection:
            _ = connection.execute(
                """
                insert into stored_results (
                    id,
                    project_id,
                    session_id,
                    tool_name,
                    input_json,
                    raw_result_json,
                    summary_json,
                    content_type,
                    raw_token_estimate,
                    returned_token_estimate,
                    created_at,
                    expires_at,
                    retrieval_count
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    result_id,
                    request.project_id,
                    request.session_id,
                    request.tool_name,
                    request.input_json,
                    request.raw_result_json,
                    request.summary_json,
                    request.content_type,
                    request.raw_token_estimate,
                    request.returned_token_estimate,
                    created,
                    expires,
                ),
            )
        return self.get_result(result_id, include_expired=True)

    def get_result(
        self,
        result_id: str,
        *,
        include_expired: bool = False,
        now: datetime | None = None,
    ) -> StoredResultRow:
        timestamp = _timestamp(now or datetime.now(UTC))
        query = """
            select
                id,
                project_id,
                session_id,
                tool_name,
                input_json,
                raw_result_json,
                summary_json,
                content_type,
                raw_token_estimate,
                returned_token_estimate,
                created_at,
                expires_at,
                retrieval_count
            from stored_results
            where id = ?
        """
        params: tuple[str, ...]
        if include_expired:
            params = (result_id,)
        else:
            query += " and (expires_at is null or expires_at > ?)"
            params = (result_id, timestamp)
        with self.storage.read_connection() as connection:
            rows: list[StoredResultTuple] = connection.execute(query, params).fetchall()
        if not rows:
            raise LookupError(result_id)
        return _row_from_tuple(rows[0])

    def increment_retrieval_count(self, result_id: str) -> StoredResultRow:
        updated_count = 0
        with self.storage.write_transaction() as connection:
            cursor = connection.execute(
                """
                update stored_results
                set retrieval_count = retrieval_count + 1
                where id = ?
                """,
                (result_id,),
            )
            updated_count = cursor.rowcount
        if updated_count != 1:
            raise LookupError(result_id)
        return self.get_result(result_id, include_expired=True)

    def cleanup_expired(self, *, now: datetime | None = None) -> int:
        timestamp = _timestamp(now or datetime.now(UTC))
        with self.storage.write_transaction() as connection:
            cursor = connection.execute(
                """
                delete from stored_results
                where expires_at is not null and expires_at <= ?
                """,
                (timestamp,),
            )
            return cursor.rowcount

    def list_summarized_results(
        self,
        *,
        limit: int,
        order_by: Literal["largest", "recent"],
        now: datetime | None = None,
    ) -> tuple[StoredResultSummaryRow, ...]:
        timestamp = _timestamp(now or datetime.now(UTC))
        with self.storage.read_connection() as connection:
            if order_by == "largest":
                rows: list[StoredResultSummaryTuple] = connection.execute(
                    """
                    select
                        id,
                        project_id,
                        session_id,
                        tool_name,
                        summary_json,
                        raw_token_estimate,
                        returned_token_estimate,
                        created_at,
                        expires_at,
                        retrieval_count
                    from stored_results
                    where summary_json is not null
                        and (expires_at is null or expires_at > ?)
                    order by coalesce(raw_token_estimate, 0) desc, created_at desc, id
                    limit ?
                    """,
                    (timestamp, limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    select
                        id,
                        project_id,
                        session_id,
                        tool_name,
                        summary_json,
                        raw_token_estimate,
                        returned_token_estimate,
                        created_at,
                        expires_at,
                        retrieval_count
                    from stored_results
                    where summary_json is not null
                        and (expires_at is null or expires_at > ?)
                    order by created_at desc, id
                    limit ?
                    """,
                    (timestamp, limit),
                ).fetchall()
        return tuple(_summary_from_tuple(row) for row in rows)


StoredResultTuple = tuple[
    str,
    str,
    str | None,
    str,
    str,
    str,
    str | None,
    str | None,
    int | None,
    int | None,
    str,
    str | None,
    int,
]

StoredResultSummaryTuple = tuple[
    str,
    str,
    str | None,
    str,
    str,
    int | None,
    int | None,
    str,
    str | None,
    int,
]


def _result_id(
    *,
    project_id: str,
    tool_name: str,
    input_json: str,
    raw_result_json: str,
    created_at: str,
) -> str:
    payload = (
        f"{project_id}\x1f{tool_name}\x1f{input_json}"
        f"\x1f{raw_result_json}\x1f{created_at}"
    )
    digest = hashlib.sha256(
        payload.encode(),
    ).hexdigest()
    return f"ctx_{digest[:16]}"


def _row_from_tuple(row: StoredResultTuple) -> StoredResultRow:
    return StoredResultRow(
        id=row[0],
        project_id=row[1],
        session_id=row[2],
        tool_name=row[3],
        input_json=row[4],
        raw_result_json=row[5],
        summary_json=row[6],
        content_type=row[7],
        raw_token_estimate=row[8],
        returned_token_estimate=row[9],
        created_at=row[10],
        expires_at=row[11],
        retrieval_count=row[12],
    )


def _summary_from_tuple(row: StoredResultSummaryTuple) -> StoredResultSummaryRow:
    return StoredResultSummaryRow(
        id=row[0],
        project_id=row[1],
        session_id=row[2],
        tool_name=row[3],
        summary_json=row[4],
        raw_token_estimate=row[5],
        returned_token_estimate=row[6],
        created_at=row[7],
        expires_at=row[8],
        retrieval_count=row[9],
    )


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def _optional_timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _timestamp(value)
