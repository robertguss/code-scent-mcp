from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from codescent.core.paths import resolve_repo_root
from codescent.services.context_optimization_models import (
    DEFAULT_RESULT_TTL_SECONDS,
    MAX_RETRIEVAL_LIMIT,
    ContextEnvelope,
    ContextStatsPayload,
    ResultPayload,
    RetrievalHint,
    RetrievalPayload,
    StoredResult,
    SummaryPayload,
)
from codescent.services.context_optimization_payloads import (
    estimate_tokens,
    normalize_session_id,
    not_found,
    payload_from_json,
    result_id_for_payload,
    select_payload,
    should_store_result,
    summarize_result,
    summary_from_json,
    to_json,
)
from codescent.storage import RepositoryStorage, initialize_storage
from codescent.storage.repositories.context_results import (
    insert_session_event,
    largest_sql,
    stats_parameters,
    stats_sql,
)

if TYPE_CHECKING:
    import sqlite3

__all__ = [
    "ContextEnvelope",
    "ContextOptimizationService",
    "ResultPayload",
    "RetrievalHint",
    "estimate_tokens",
    "result_id_for_payload",
    "should_store_result",
    "summarize_result",
]


@dataclass(frozen=True, slots=True)
class ContextOptimizationService:
    repo_root: str

    def store_result(
        self,
        *,
        tool_name: str,
        session_id: str | None,
        query: str | None,
        raw_payload: ResultPayload,
        returned_payload: SummaryPayload,
    ) -> StoredResult:
        state = initialize_storage(self.repo_root)
        resolved_session_id = normalize_session_id(session_id)
        now = utc_now()
        expires_at = now + timedelta(seconds=DEFAULT_RESULT_TTL_SECONDS)
        raw_tokens = estimate_tokens(raw_payload)
        returned_tokens = estimate_tokens(returned_payload)
        result_id = result_id_for_payload(
            tool_name=tool_name,
            session_id=resolved_session_id,
            query=query,
            payload=raw_payload,
        )
        with RepositoryStorage(state).write_transaction() as connection:
            _ = connection.execute(
                "delete from stored_results where expires_at <= ?",
                (now.isoformat(),),
            )
            _ = connection.execute(
                """
                insert or replace into stored_results (
                    id,
                    tool_name,
                    session_id,
                    query,
                    raw_payload_json,
                    returned_payload_json,
                    raw_token_estimate,
                    returned_token_estimate,
                    created_at,
                    expires_at,
                    retrieval_count
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result_id,
                    tool_name,
                    resolved_session_id,
                    query,
                    to_json(raw_payload),
                    to_json(returned_payload),
                    raw_tokens,
                    returned_tokens,
                    now.isoformat(),
                    expires_at.isoformat(),
                    0,
                ),
            )
            insert_session_event(
                connection,
                session_id=resolved_session_id,
                tool_name=tool_name,
                event_type="tool_called",
                result_id=result_id,
                raw_tokens=raw_tokens,
                returned_tokens=returned_tokens,
                created_at=now.isoformat(),
            )
        return StoredResult(
            result_id=result_id,
            session_id=resolved_session_id,
            expires_at=expires_at.isoformat(),
            raw_token_estimate=raw_tokens,
            returned_token_estimate=returned_tokens,
        )

    def retrieve_result(  # noqa: PLR0913 - service mirrors MCP retrieval filters.
        self,
        result_id: str,
        *,
        mode: str,
        query: str | None = None,
        file: str | None = None,
        symbol: str | None = None,
        session_id: str | None = None,
        limit: int = MAX_RETRIEVAL_LIMIT,
    ) -> RetrievalPayload:
        state = initialize_storage(resolve_repo_root(self.repo_root))
        now = utc_now().isoformat()
        bounded_limit = min(max(limit, 1), MAX_RETRIEVAL_LIMIT)
        with RepositoryStorage(state).write_transaction() as connection:
            rows = result_rows(
                connection=connection,
                result_id=result_id,
                expires_after=now,
                session_id=session_id,
            )
            if not rows:
                return not_found(result_id, mode)
            raw_json, returned_json, session_id, tool_name = rows[0]
            _ = connection.execute(
                """
                update stored_results
                set retrieval_count = retrieval_count + 1
                where id = ?
                """,
                (result_id,),
            )
            insert_session_event(
                connection,
                session_id=session_id,
                tool_name=tool_name,
                event_type="result_retrieved",
                result_id=result_id,
                raw_tokens=0,
                returned_tokens=0,
                created_at=now,
            )
        return {
            "ok": True,
            "result_id": result_id,
            "mode": mode,
            "session_id": session_id,
            "payload": select_payload(
                mode=mode,
                raw_payload=payload_from_json(raw_json),
                returned_payload=summary_from_json(returned_json),
                query=query,
                file=file,
                symbol=symbol,
                limit=bounded_limit,
            ),
            "warnings": (),
        }

    def context_stats(self, *, session_id: str | None) -> ContextStatsPayload:
        state = initialize_storage(resolve_repo_root(self.repo_root))
        with RepositoryStorage(state).read_connection() as connection:
            rows: list[tuple[str, str, int, int]] = connection.execute(
                stats_sql(session_id),
                stats_parameters(session_id),
            ).fetchall()
            largest_rows: list[tuple[str]] = connection.execute(
                largest_sql(session_id),
                stats_parameters(session_id),
            ).fetchall()
        tool_calls = sum(1 for row in rows if row[1] == "tool_called")
        retrievals = sum(1 for row in rows if row[1] == "result_retrieved")
        raw_tokens = sum(row[2] for row in rows if row[1] == "tool_called")
        returned_tokens = sum(row[3] for row in rows if row[1] == "tool_called")
        tools = sorted({row[0] for row in rows if row[1] == "tool_called"})
        return {
            "ok": True,
            "session_id": session_id,
            "tool_calls": tool_calls,
            "summarized_results": tool_calls,
            "retrievals": retrievals,
            "estimated_raw_tokens": raw_tokens,
            "estimated_returned_tokens": returned_tokens,
            "estimated_tokens_avoided": max(raw_tokens - returned_tokens, 0),
            "largest_summarized_results": tuple(row[0] for row in largest_rows),
            "most_used_tools": tuple(tools),
            "warnings": (),
        }


def utc_now() -> datetime:
    return datetime.now(UTC)


def result_rows(
    *,
    connection: sqlite3.Connection,
    result_id: str,
    expires_after: str,
    session_id: str | None,
) -> list[tuple[str, str, str, str]]:
    if session_id is None:
        return connection.execute(
            """
            select raw_payload_json, returned_payload_json, session_id, tool_name
            from stored_results
            where id = ? and expires_at > ?
            """,
            (result_id, expires_after),
        ).fetchall()
    return connection.execute(
        """
        select raw_payload_json, returned_payload_json, session_id, tool_name
        from stored_results
        where id = ? and expires_at > ? and session_id = ?
        """,
        (result_id, expires_after, session_id),
    ).fetchall()
