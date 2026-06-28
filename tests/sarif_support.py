from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import jsonschema

# Vendored SARIF 2.1.0 structural schema (faithful subset of the OASIS schema).
# Validation runs fully offline — no remote schema is fetched at runtime.
SCHEMA_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "sarif" / "sarif-2.1.0.schema.json"
)


def validate_sarif(document: object) -> None:
    """Validate ``document`` against the vendored SARIF 2.1.0 schema."""
    schema = cast("dict[str, object]", json.loads(SCHEMA_PATH.read_text("utf-8")))
    jsonschema.validate(document, schema)
