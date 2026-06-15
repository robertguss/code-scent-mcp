from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Final, Literal, TypedDict, cast

from codescent.core.models import ResponseEnvelope
from codescent.storage import RepositoryStorage, initialize_storage
from codescent.storage.repositories import (
    StoredResultCreate,
    StoredResultRepository,
    StoredResultRow,
)

DEFAULT_RETRIEVE_LIMIT: Final = 20
MAX_RETRIEVE_LIMIT: Final = 100
RESULT_ID_PREFIX: Final = "ctx_"
RESULT_ID_LENGTH: Final = 20

JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
RetrieveMode = Literal["exact", "summary", "filtered", "sample"]
ResultStoreErrorCode = Literal[
    "invalid_result_id",
    "missing_result",
    "expired_result",
]


class StoredResultMode(StrEnum):
    EXACT = "exact"
    SUMMARY = "summary"
    FILTERED = "filtered"
    SAMPLE = "sample"


class RetrievalFilters(TypedDict, total=False):
    query: str | None
    file: str | None
    symbol: str | None
    result_type: str | None


class RetrievedResultPayload(TypedDict):
    kind: str
    result_id: str
    mode: str
    summary: str
    items: tuple[JsonValue, ...]
    remaining_count: int
    omitted_count: int
    warnings: tuple[str, ...]
    retrieval_hints: tuple[str, ...]


class StoredResultErrorPayload(TypedDict):
    kind: str
    code: str
    message: str
    result_id: str
    retryable: bool


@dataclass(frozen=True, slots=True)
class ResultStoreError(Exception):
    code: ResultStoreErrorCode
    result_id: str
    message: str
    retryable: bool = False

    def __post_init__(self) -> None:
        Exception.__init__(self, self.message)

    def to_payload(self) -> StoredResultErrorPayload:
        return {
            "kind": "result_store_error",
            "code": self.code,
            "message": self.message,
            "result_id": self.result_id,
            "retryable": self.retryable,
        }


@dataclass(frozen=True, slots=True)
class ResultStoreService:
    repo_root: Path | str

    def store_result(  # noqa: PLR0913
        self,
        *,
        project_id: str,
        tool_name: str,
        input_payload: JsonValue,
        raw_result: JsonValue,
        summary: ResponseEnvelope | JsonValue | None = None,
        session_id: str | None = None,
        content_type: str = "application/json",
        raw_token_estimate: int | None = None,
        returned_token_estimate: int | None = None,
        created_at: datetime | None = None,
        expires_at: datetime | None = None,
    ) -> StoredResultRow:
        return self.repository.create_result(
            StoredResultCreate(
                project_id=project_id,
                session_id=session_id,
                tool_name=tool_name,
                input_json=_json_text(input_payload),
                raw_result_json=_json_text(raw_result),
                summary_json=_summary_text(summary),
                content_type=content_type,
                raw_token_estimate=raw_token_estimate,
                returned_token_estimate=returned_token_estimate,
                created_at=created_at,
                expires_at=expires_at,
            ),
        )

    def store_result_json(  # noqa: PLR0913
        self,
        *,
        project_id: str,
        tool_name: str,
        input_json: str,
        raw_result_json: str,
        summary_json: str | None = None,
        session_id: str | None = None,
        content_type: str = "application/json",
        raw_token_estimate: int | None = None,
        returned_token_estimate: int | None = None,
        created_at: datetime | None = None,
        expires_at: datetime | None = None,
    ) -> StoredResultRow:
        _validate_json(input_json)
        _validate_json(raw_result_json)
        if summary_json is not None:
            _validate_json(summary_json)
        return self.repository.create_result(
            StoredResultCreate(
                project_id=project_id,
                session_id=session_id,
                tool_name=tool_name,
                input_json=input_json,
                raw_result_json=raw_result_json,
                summary_json=summary_json,
                content_type=content_type,
                raw_token_estimate=raw_token_estimate,
                returned_token_estimate=returned_token_estimate,
                created_at=created_at,
                expires_at=expires_at,
            ),
        )

    def retrieve_result(  # noqa: PLR0913
        self,
        result_id: str,
        *,
        mode: RetrieveMode = "exact",
        limit: int = DEFAULT_RETRIEVE_LIMIT,
        query: str | None = None,
        file: str | None = None,
        symbol: str | None = None,
        result_type: str | None = None,
        now: datetime | None = None,
    ) -> RetrievedResultPayload:
        self._validate_result_id(result_id)
        row = self._get_active_result(result_id, now=now)
        raw_payload = _load_json(row.raw_result_json)
        summary_payload = _load_json(row.summary_json) if row.summary_json else None
        bounded_limit = _bounded_limit(limit)

        if mode == StoredResultMode.SUMMARY.value:
            _ = self.repository.increment_retrieval_count(result_id)
            return _summary_response(
                row,
                summary_payload=summary_payload,
                raw_payload=raw_payload,
                limit=bounded_limit,
            )

        records = _records(raw_payload)
        if mode == StoredResultMode.FILTERED.value:
            records = tuple(
                record
                for record in records
                if _matches_filters(
                    record,
                    query=query,
                    file=file,
                    symbol=symbol,
                    result_type=result_type,
                )
            )
        elif mode == StoredResultMode.SAMPLE.value:
            records = _sample(records, bounded_limit)

        _ = self.repository.increment_retrieval_count(result_id)
        return _items_response(
            row,
            mode=mode,
            records=records,
            limit=bounded_limit,
            filters={
                "query": query,
                "file": file,
                "symbol": symbol,
                "result_type": result_type,
            },
        )

    @property
    def repository(self) -> StoredResultRepository:
        state = initialize_storage(Path(self.repo_root))
        return StoredResultRepository(RepositoryStorage(state))

    def _validate_result_id(self, result_id: str) -> None:
        if (
            not result_id.startswith(RESULT_ID_PREFIX)
            or len(result_id) != RESULT_ID_LENGTH
        ):
            raise ResultStoreError(
                code="invalid_result_id",
                result_id=result_id,
                message="Result ID must be an opaque ctx_ identifier.",
            )

    def _get_active_result(
        self,
        result_id: str,
        *,
        now: datetime | None,
    ) -> StoredResultRow:
        try:
            return self.repository.get_result(result_id, now=now)
        except LookupError as exc:
            if self._is_expired(result_id, now=now):
                raise ResultStoreError(
                    code="expired_result",
                    result_id=result_id,
                    message="Stored result is expired and cannot be retrieved.",
                ) from exc
            raise ResultStoreError(
                code="missing_result",
                result_id=result_id,
                message="Stored result ID was not found.",
            ) from exc

    def _is_expired(self, result_id: str, *, now: datetime | None) -> bool:
        try:
            row = self.repository.get_result(result_id, include_expired=True)
        except LookupError:
            return False
        if row.expires_at is None:
            return False
        comparison_time = now or datetime.now(UTC)
        if comparison_time.tzinfo is None:
            comparison_time = comparison_time.replace(tzinfo=UTC)
        return _parse_timestamp(row.expires_at) <= comparison_time.astimezone(UTC)


def _summary_response(
    row: StoredResultRow,
    *,
    summary_payload: JsonValue | None,
    raw_payload: JsonValue | None,
    limit: int,
) -> RetrievedResultPayload:
    if summary_payload is not None:
        records = _records(summary_payload)
    else:
        records = _records(raw_payload)
    visible = records[:limit]
    omitted_count = max(len(records) - len(visible), 0)
    warnings = _partial_warnings(omitted_count)
    return {
        "kind": "retrieved_result",
        "result_id": row.id,
        "mode": StoredResultMode.SUMMARY.value,
        "summary": _summary_text_for(row, len(visible), len(records)),
        "items": visible,
        "remaining_count": omitted_count,
        "omitted_count": omitted_count,
        "warnings": warnings,
        "retrieval_hints": _retrieval_hints(row.id, warnings=warnings),
    }


def _items_response(
    row: StoredResultRow,
    *,
    mode: RetrieveMode,
    records: tuple[JsonValue, ...],
    limit: int,
    filters: RetrievalFilters,
) -> RetrievedResultPayload:
    visible = records[:limit]
    omitted_count = max(len(records) - len(visible), 0)
    response_mode = mode
    warnings = _partial_warnings(omitted_count)
    if mode == StoredResultMode.EXACT.value and omitted_count > 0:
        response_mode = StoredResultMode.SUMMARY.value
        warnings = ("exact result exceeded limit; returning bounded partial payload",)
    return {
        "kind": "retrieved_result",
        "result_id": row.id,
        "mode": response_mode,
        "summary": _retrieval_summary(row, response_mode, len(visible), len(records)),
        "items": visible,
        "remaining_count": omitted_count,
        "omitted_count": omitted_count,
        "warnings": warnings,
        "retrieval_hints": _retrieval_hints(row.id, filters=filters, warnings=warnings),
    }


def _records(payload: JsonValue | None) -> tuple[JsonValue, ...]:
    if payload is None:
        return ()
    if isinstance(payload, list):
        return tuple(payload)
    if isinstance(payload, dict):
        for key in ("items", "results", "matches", "symbols", "records"):
            value = payload.get(key)
            if isinstance(value, list):
                return tuple(value)
    return (payload,)


def _matches_filters(
    record: JsonValue,
    *,
    query: str | None,
    file: str | None,
    symbol: str | None,
    result_type: str | None,
) -> bool:
    return (
        _matches_query(record, query)
        and _matches_named_fields(record, file, ("file", "path", "file_path"))
        and _matches_named_fields(
            record,
            symbol,
            ("symbol", "name", "qualified_name", "reference_text", "call_text"),
        )
        and _matches_named_fields(record, result_type, ("type", "kind", "result_type"))
    )


def _matches_query(record: JsonValue, query: str | None) -> bool:
    if not query:
        return True
    needle = query.casefold()
    return any(needle in value.casefold() for value in _string_values(record))


def _matches_named_fields(
    record: JsonValue,
    expected: str | None,
    field_names: tuple[str, ...],
) -> bool:
    if not expected:
        return True
    needle = expected.casefold()
    return any(
        needle in value.casefold()
        for value in _field_values(record, frozenset(field_names))
    )


def _string_values(value: JsonValue) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list):
        return tuple(item for entry in value for item in _string_values(entry))
    if isinstance(value, dict):
        return tuple(item for entry in value.values() for item in _string_values(entry))
    return ()


def _field_values(value: JsonValue, field_names: frozenset[str]) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(
            item for entry in value for item in _field_values(entry, field_names)
        )
    if not isinstance(value, dict):
        return ()
    values: list[str] = []
    for key, entry in value.items():
        if key in field_names:
            values.extend(_string_values(entry))
        values.extend(_field_values(entry, field_names))
    return tuple(values)


def _sample(records: tuple[JsonValue, ...], limit: int) -> tuple[JsonValue, ...]:
    if len(records) <= limit:
        return records
    if limit == 1:
        return (records[0],)
    step = (len(records) - 1) / (limit - 1)
    return tuple(records[round(index * step)] for index in range(limit))


def _bounded_limit(limit: int) -> int:
    return min(max(limit, 1), MAX_RETRIEVE_LIMIT)


def _partial_warnings(omitted_count: int) -> tuple[str, ...]:
    if omitted_count == 0:
        return ()
    return (f"partial result; {omitted_count} stored items omitted by limit",)


def _retrieval_hints(
    result_id: str,
    *,
    filters: RetrievalFilters | None = None,
    warnings: tuple[str, ...],
) -> tuple[str, ...]:
    if not warnings:
        return ()
    hints = [
        (
            f"retrieve_result(result_id='{result_id}', "
            f"mode='exact', limit={MAX_RETRIEVE_LIMIT})"
        ),
    ]
    if filters is not None:
        active_filters = tuple(
            f"{key}={value!r}" for key, value in filters.items() if value
        )
        if active_filters:
            hints.append(
                f"retrieve_result(result_id='{result_id}', mode='filtered', "
                + ", ".join(active_filters)
                + ")",
            )
    return tuple(hints)


def _retrieval_summary(
    row: StoredResultRow,
    mode: str,
    returned_count: int,
    total_count: int,
) -> str:
    return (
        f"Returning {returned_count} of {total_count} stored {row.tool_name} "
        f"items in {mode} mode."
    )


def _summary_text_for(
    row: StoredResultRow,
    returned_count: int,
    total_count: int,
) -> str:
    return (
        f"Returning {returned_count} of {total_count} stored summary "
        f"items for {row.tool_name}."
    )


def _summary_text(summary: ResponseEnvelope | JsonValue | None) -> str | None:
    if summary is None:
        return None
    if isinstance(summary, ResponseEnvelope):
        return summary.model_dump_json()
    return _json_text(summary)


def _json_text(value: JsonValue) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _validate_json(payload: str) -> None:
    try:
        decoded = cast("object", json.JSONDecoder().decode(payload))
    except json.JSONDecodeError as exc:
        message = "stored result payload must be valid JSON"
        raise ValueError(message) from exc
    _ = decoded


def _load_json(payload: str) -> JsonValue | None:
    try:
        decoded = cast("object", json.JSONDecoder().decode(payload))
    except json.JSONDecodeError:
        return None
    return cast("JsonValue", decoded)


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
