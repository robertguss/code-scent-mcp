from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final, Literal, cast

if TYPE_CHECKING:
    from collections.abc import Mapping

    from codescent.storage import RepositoryStorage

type SessionEventType = Literal[
    "tool_called",
    "large_result_summarized",
    "result_retrieved",
    "agent_repeated_query",
    "agent_requested_exact_large_result",
    "server_warning_returned",
    "structural_backend_resolved",
]

type JsonScalar = str | int | float | bool | None
type SanitizedPayload = dict[str, JsonScalar]

SAFE_STRING_KEYS: Final = frozenset(
    {"query_fingerprint", "input_fingerprint", "warning_code", "backend_name"},
)
METRIC_KEYS: Final = frozenset(
    {
        "raw_tokens",
        "returned_tokens",
        "avoided_tokens",
        "result_count",
        "warning_count",
        "retrieval_count",
        "broad_query",
        "exact_requested",
    },
)
FINGERPRINT_SOURCE_KEYS: Final = frozenset(
    {"query", "input", "input_json", "params", "arguments", "raw_query"},
)
FINGERPRINT_TARGET_KEYS: Final = frozenset({"query", "raw_query"})
SLUG_PATTERN: Final = re.compile(r"[^a-z0-9_.:-]+")


@dataclass(frozen=True, slots=True)
class SessionEventRow:
    id: str
    project_id: str
    session_id: str
    event_type: SessionEventType
    tool_name: str | None
    result_id: str | None
    payload: SanitizedPayload
    created_at: str


@dataclass(frozen=True, slots=True)
class SessionEventWrite:
    project_id: str
    session_id: str
    event_type: SessionEventType
    tool_name: str | None = None
    result_id: str | None = None
    payload: Mapping[str, object] | None = None
    created_at: str | None = None


@dataclass(frozen=True, slots=True)
class SessionEventRepository:
    storage: RepositoryStorage

    def record_event(self, event: SessionEventWrite) -> SessionEventRow:
        event_id = f"evt_{uuid.uuid4().hex}"
        event_time = event.created_at or datetime.now(UTC).isoformat()
        sanitized_payload = sanitize_event_payload(event.payload or {})
        with self.storage.write_transaction() as connection:
            _ = connection.execute(
                """
                insert into session_events (
                    id,
                    project_id,
                    session_id,
                    event_type,
                    tool_name,
                    result_id,
                    payload_json,
                    created_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    event.project_id,
                    event.session_id,
                    event.event_type,
                    event.tool_name,
                    event.result_id,
                    json.dumps(sanitized_payload, sort_keys=True),
                    event_time,
                ),
            )
        return SessionEventRow(
            id=event_id,
            project_id=event.project_id,
            session_id=event.session_id,
            event_type=event.event_type,
            tool_name=event.tool_name,
            result_id=event.result_id,
            payload=sanitized_payload,
            created_at=event_time,
        )

    def list_events(
        self,
        *,
        project_id: str,
        session_id: str,
        limit: int = 500,
    ) -> tuple[SessionEventRow, ...]:
        safe_limit = min(max(limit, 0), 500)
        with self.storage.read_connection() as connection:
            rows: list[
                tuple[str, str, str, str, str | None, str | None, str | None, str]
            ] = connection.execute(
                """
                    select
                        id,
                        project_id,
                        session_id,
                        event_type,
                        tool_name,
                        result_id,
                        payload_json,
                        created_at
                    from session_events
                    where project_id = ? and session_id = ?
                    order by created_at, id
                    limit ?
                    """,
                (project_id, session_id, safe_limit),
            ).fetchall()
        return tuple(_row_from_database(row) for row in rows)


def sanitize_event_payload(payload: Mapping[str, object]) -> SanitizedPayload:
    sanitized: SanitizedPayload = {}
    for key, value in payload.items():
        normalized_key = str(key)
        if normalized_key in METRIC_KEYS:
            metric = _metric_value(value)
            if metric is not None:
                sanitized[normalized_key] = metric
        elif normalized_key in SAFE_STRING_KEYS:
            if isinstance(value, str):
                sanitized[normalized_key] = _safe_slug(value)
        elif normalized_key in FINGERPRINT_SOURCE_KEYS:
            fingerprint_key = "query_fingerprint"
            if normalized_key not in FINGERPRINT_TARGET_KEYS:
                fingerprint_key = "input_fingerprint"
            sanitized[fingerprint_key] = _fingerprint(value)
    if "input_fingerprint" not in sanitized:
        compound_input = {
            key: payload[key]
            for key in sorted(payload)
            if key not in METRIC_KEYS | SAFE_STRING_KEYS | FINGERPRINT_TARGET_KEYS
        }
        if compound_input:
            sanitized["input_fingerprint"] = _fingerprint(compound_input)
    return sanitized


def _row_from_database(
    row: tuple[str, str, str, str, str | None, str | None, str | None, str],
) -> SessionEventRow:
    raw_payload = row[6] or "{}"
    payload = _payload_from_json(raw_payload)
    return SessionEventRow(
        id=row[0],
        project_id=row[1],
        session_id=row[2],
        event_type=cast("SessionEventType", row[3]),
        tool_name=row[4],
        result_id=row[5],
        payload=payload,
        created_at=row[7],
    )


def _payload_from_json(raw_payload: str) -> SanitizedPayload:
    try:
        decoded = cast("object", json.JSONDecoder().decode(raw_payload))
    except json.JSONDecodeError:
        return {}
    parsed = decoded
    if not isinstance(parsed, dict):
        return {}
    sanitized: SanitizedPayload = {}
    for key, value in cast("dict[object, object]", parsed).items():
        key_text = str(key)
        if key_text in SAFE_STRING_KEYS and isinstance(value, str):
            sanitized[key_text] = _safe_slug(value)
        elif key_text in METRIC_KEYS:
            metric = _metric_value(value)
            if metric is not None:
                sanitized[key_text] = metric
    return sanitized


def _metric_value(value: object) -> JsonScalar:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, float):
        return max(value, 0.0)
    return None


def _safe_slug(value: str) -> str:
    lowered = value.lower().strip()
    collapsed = SLUG_PATTERN.sub("_", lowered).strip("_")
    return collapsed[:80]


def _fingerprint(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return f"sha256:{digest[:16]}"
