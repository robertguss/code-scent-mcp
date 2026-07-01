"""Target success/error envelope schemas for R4 conformance (plan U2).

R4 measures the share of tool responses that validate against *exactly one*
envelope shape. The success schema encodes the uniform shape the phase-two
consolidation drives toward (``ok`` plus ``next_tools``); the error schema is
the already-uniform recoverable-error envelope from ``ToolErrorBoundary``. A
bare-dict response that matches neither is non-conforming -- exactly the gap
U14 closes.
"""

from __future__ import annotations

import jsonschema

SUCCESS_SCHEMA: dict[str, object] = {
    "type": "object",
    "required": ["ok", "next_tools"],
    "properties": {
        "ok": {"const": True},
        "next_tools": {"type": "array"},
    },
}

ERROR_SCHEMA: dict[str, object] = {
    "type": "object",
    "required": ["ok", "code", "message", "recoverable", "data"],
    "properties": {
        "ok": {"const": False},
        "recoverable": {"type": "boolean"},
    },
}


def matches(payload: dict[str, object], schema: dict[str, object]) -> bool:
    """Return whether ``payload`` validates against ``schema``."""
    try:
        jsonschema.validate(payload, schema)
    except jsonschema.ValidationError:
        return False
    return True


def validates_exactly_one(payload: dict[str, object]) -> bool:
    """Return whether ``payload`` matches exactly one of the two envelopes."""
    return matches(payload, SUCCESS_SCHEMA) != matches(payload, ERROR_SCHEMA)
