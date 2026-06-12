from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import TypeAdapter

from codescent.services.context_optimization_models import (
    DEFAULT_SESSION_ID,
    OPAQUE_ID_HEX_LENGTH,
    ContextEnvelope,
    JsonValue,
    ResultItem,
    ResultPayload,
    RetrievalPayload,
    SummaryPayload,
)

JSON_VALUE_ADAPTER: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)
StringResultKey = Literal[
    "path",
    "file",
    "symbol",
    "certainty",
    "caller",
    "snippet",
    "text",
]
IntResultKey = Literal["line", "start_line"]
FloatResultKey = Literal["score", "confidence"]


def normalize_session_id(session_id: str | None) -> str:
    if session_id:
        return session_id
    return DEFAULT_SESSION_ID


def estimate_tokens(payload: ResultPayload | SummaryPayload) -> int:
    return max(len(to_json(payload)) // 4, 1)


def result_id_for_payload(
    *,
    tool_name: str,
    session_id: str,
    query: str | None,
    payload: ResultPayload,
) -> str:
    digest = hashlib.sha256()
    digest.update(tool_name.encode())
    digest.update(b"\0")
    digest.update(session_id.encode())
    digest.update(b"\0")
    digest.update((query or "").encode())
    digest.update(b"\0")
    digest.update(to_json(payload).encode())
    return f"ctx_{digest.hexdigest()[:OPAQUE_ID_HEX_LENGTH]}"


def should_store_result(payload: ResultPayload, *, returned_limit: int) -> bool:
    return len(payload["items"]) > returned_limit


def summarize_result(
    *,
    kind: str,
    result_id: str,
    payload: ResultPayload,
    returned_limit: int,
) -> ContextEnvelope:
    total_count = len(payload["items"])
    omitted_count = max(total_count - returned_limit, 0)
    return {
        "kind": kind,
        "mode": "summary",
        "summary": (
            f"{total_count} items; showing {returned_limit}. "
            f"Retrieve {result_id} for full result."
        ),
        "omitted_count": omitted_count,
        "original_result_id": result_id,
        "retrieval_available": True,
        "retrieval_hints": (
            {"mode": "exact", "description": "return the full stored payload"},
            {"mode": "filtered", "description": "filter by file or symbol"},
            {"mode": "sample", "description": "return a bounded sample"},
        ),
        "confidence": "high",
        "warnings": (),
    }


def select_payload(  # noqa: PLR0913 - retrieval supports independent filters.
    *,
    mode: str,
    raw_payload: ResultPayload,
    returned_payload: SummaryPayload,
    query: str | None,
    file: str | None,
    symbol: str | None,
    limit: int,
) -> ResultPayload:
    match mode:
        case "exact":
            return raw_payload
        case "summary":
            return {"items": ({"snippet": returned_payload["summary"]},)}
        case "filtered":
            return {
                "items": tuple(
                    item
                    for item in raw_payload["items"]
                    if matches_item(item, query=query, file=file, symbol=symbol)
                )[:limit],
            }
        case "sample":
            return {"items": raw_payload["items"][:limit]}
        case _:
            return {"items": ()}


def matches_item(
    item: ResultItem,
    *,
    query: str | None,
    file: str | None,
    symbol: str | None,
) -> bool:
    if file and item.get("path", item.get("file", "")) != file:
        return False
    if symbol and item.get("symbol") != symbol:
        return False
    return not (query and query.lower() not in item_text(item).lower())


def item_text(item: ResultItem) -> str:
    return " ".join(
        value
        for value in (
            item.get("path"),
            item.get("file"),
            item.get("symbol"),
            item.get("snippet"),
            item.get("text"),
        )
        if value
    )


def payload_from_json(payload_json: str) -> ResultPayload:
    loaded = JSON_VALUE_ADAPTER.validate_json(payload_json)
    if not isinstance(loaded, dict):
        return {"items": ()}
    loaded_items = loaded.get("items")
    if not isinstance(loaded_items, list):
        return {"items": ()}
    items = [
        result_item_from_mapping(loaded_item)
        for loaded_item in loaded_items
        if isinstance(loaded_item, dict)
    ]
    return {"items": tuple(items)}


def result_item_from_mapping(mapping: dict[str, JsonValue]) -> ResultItem:
    item: ResultItem = {}
    for key in ("path", "file", "symbol", "certainty", "caller", "snippet", "text"):
        add_string_field(item, mapping, key)
    for key in ("line", "start_line"):
        add_int_field(item, mapping, key)
    for key in ("score", "confidence"):
        add_float_field(item, mapping, key)
    return item


def add_string_field(
    item: ResultItem,
    mapping: dict[str, JsonValue],
    key: StringResultKey,
) -> None:
    value = mapping.get(key)
    if isinstance(value, str):
        item[key] = value


def add_int_field(
    item: ResultItem,
    mapping: dict[str, JsonValue],
    key: IntResultKey,
) -> None:
    value = mapping.get(key)
    if isinstance(value, int):
        item[key] = value


def add_float_field(
    item: ResultItem,
    mapping: dict[str, JsonValue],
    key: FloatResultKey,
) -> None:
    value = mapping.get(key)
    if isinstance(value, float):
        item[key] = value


def summary_from_json(payload_json: str) -> SummaryPayload:
    loaded = JSON_VALUE_ADAPTER.validate_json(payload_json)
    if isinstance(loaded, dict):
        summary = loaded.get("summary")
        if isinstance(summary, str):
            return {"summary": summary}
    return {"summary": ""}


def not_found(result_id: str, mode: str) -> RetrievalPayload:
    return {
        "ok": False,
        "result_id": result_id,
        "mode": mode,
        "session_id": DEFAULT_SESSION_ID,
        "payload": {"items": ()},
        "error_code": "result_not_found",
        "warnings": ("result was not found or has expired",),
    }


def to_json(payload: ResultPayload | SummaryPayload) -> str:
    return json.dumps(canonical_json(payload), sort_keys=True, separators=(",", ":"))


def canonical_json(payload: ResultPayload | SummaryPayload) -> JsonValue:
    if "items" in payload:
        return {
            "items": [
                {
                    key: value
                    for key, value in item.items()
                    if isinstance(value, str | int | float | bool) or value is None
                }
                for item in payload["items"]
            ],
        }
    return {"summary": payload["summary"]}
