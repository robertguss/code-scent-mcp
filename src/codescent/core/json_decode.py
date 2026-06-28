"""Bounded JSON-object decoders shared across services and adapters.

Findings persist their ``evidence`` and ``provenance`` as JSON strings. Several
layers (the report/explain services, the MCP finding payloads, the dashboard
payloads) need to decode those blobs back into flat, scalar-only dicts. This is
their single home so the services and the MCP/dashboard adapters depend on a
neutral helper instead of importing across the adapter boundary.
"""

from __future__ import annotations

import json
from typing import TypeGuard, cast

JsonScalar = str | int | float | bool | None
JsonObject = dict[str, JsonScalar]

# A bounded provenance dict (rule_id, language, resolution, symbol_resolved):
# only string and boolean values, never numbers or nested structures.
ProvenanceItem = dict[str, str | bool]


def is_json_scalar(value: object) -> TypeGuard[JsonScalar]:
    return value is None or isinstance(value, str | int | float | bool)


def decode_json_object(raw: str) -> JsonObject:
    """Decode a JSON object string to a flat dict of scalar values.

    A non-object payload, malformed JSON, or non-scalar values yield an empty
    dict / are dropped -- the result is always a bounded scalar mapping.
    """
    try:
        decoded = cast("object", json.loads(raw))
    except json.JSONDecodeError:
        return {}
    if not isinstance(decoded, dict):
        return {}
    items = cast("dict[object, object]", decoded)
    return {str(key): value for key, value in items.items() if is_json_scalar(value)}


def decode_provenance(raw: str) -> ProvenanceItem:
    """Decode a stored provenance JSON blob to a small, bounded str|bool dict."""
    return {
        key: value
        for key, value in decode_json_object(raw).items()
        if isinstance(value, str | bool)
    }
