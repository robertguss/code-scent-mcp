from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import sqlite3


def insert_session_event(  # noqa: PLR0913 - mirrors persisted event columns.
    connection: sqlite3.Connection,
    *,
    session_id: str,
    tool_name: str,
    event_type: str,
    result_id: str,
    raw_tokens: int,
    returned_tokens: int,
    created_at: str,
) -> None:
    _ = connection.execute(
        """
        insert into session_events (
            session_id,
            tool_name,
            event_type,
            result_id,
            raw_token_estimate,
            returned_token_estimate,
            created_at
        ) values (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            tool_name,
            event_type,
            result_id,
            raw_tokens,
            returned_tokens,
            created_at,
        ),
    )


def stats_sql(session_id: str | None) -> str:
    if session_id is None:
        return """
            select tool_name, event_type, raw_token_estimate, returned_token_estimate
            from session_events
            order by created_at, id
        """
    return """
        select tool_name, event_type, raw_token_estimate, returned_token_estimate
        from session_events
        where session_id = ?
        order by created_at, id
    """


def largest_sql(session_id: str | None) -> str:
    if session_id is None:
        return """
            select id
            from stored_results
            order by raw_token_estimate desc, id
            limit 5
        """
    return """
        select id
        from stored_results
        where session_id = ?
        order by raw_token_estimate desc, id
        limit 5
    """


def stats_parameters(session_id: str | None) -> tuple[str, ...]:
    if session_id is None:
        return ()
    return (session_id,)
