"""R4 envelope-conformance dimension (plan U2), network-free.

Drives every tool once with schema-derived valid args and scores the share of
responses that validate against exactly one envelope shape (see ``schemas``).
Below 100% at baseline -- several tools emit ad-hoc success dicts -- which is the
gap phase two (U14) closes.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from codescent.evals.agent_ux._client import (
    call_tool_json,
    list_tools_manifest,
    todo_finding_id,
)
from codescent.evals.agent_ux.models import DimensionResult
from codescent.evals.agent_ux.schemas import validates_exactly_one

if TYPE_CHECKING:
    from pathlib import Path

    from fastmcp import Client
    from fastmcp.client.transports import FastMCPTransport


def _arg_values(repo: Path, finding_id: str, result_id: str) -> dict[str, object]:
    """A value for every locator param a tool might require, keyed by name."""
    return {
        "repo": str(repo),
        "finding_id": finding_id,
        "result_id": result_id,
        "qualified_name": "pkg.config.load_config",
        "symbol": "pkg.config.load_config",
        "target": "pkg.config.load_config",
        "path": "src/pkg/config.py",
        "query": "load",
        "queries": ["load"],
        "command": "uv run pytest",
        "exit_code": 0,
        "output_summary": "ok",
        "status": "in_progress",
    }


def _build_args(schema_json: str, values: dict[str, object]) -> dict[str, object]:
    """Fill a tool's accepted params from ``values`` off its JSON schema.

    Reads ``properties``/``required`` so every tool gets a representative call
    without a hand-authored per-tool map: ``repo`` is passed only to tools that
    declare it (so tools that don't aren't handed an unexpected kwarg), plus any
    required param with a known value. A required param with no known value is
    left out; the tool then returns a (conforming) error envelope.
    """
    args: dict[str, object] = {}
    parsed = cast("object", json.loads(schema_json))
    if not isinstance(parsed, dict):
        return args
    schema = cast("dict[str, object]", parsed)
    properties = schema.get("properties")
    accepts_repo = isinstance(properties, dict) and "repo" in cast(
        "dict[str, object]", properties
    )
    if accepts_repo:
        args["repo"] = values["repo"]
    required = schema.get("required")
    if isinstance(required, list):
        for param in cast("list[object]", required):
            if isinstance(param, str) and param in values:
                args[param] = values[param]
    return args


async def _sample_result_id(
    client: Client[FastMCPTransport],
    repo: Path,
) -> str:
    """Return a valid ``result_id`` from a search, or a dummy that errors safely."""
    payload = await call_tool_json(
        client, "search_content", {"repo": str(repo), "query": "load"}
    )
    result_id = payload.get("result_id")
    return result_id if isinstance(result_id, str) else "ctx_0000000000000000"


async def envelope_conformance(
    client: Client[FastMCPTransport],
    repo: Path,
) -> DimensionResult:
    """Score R4: share of tool responses matching exactly one envelope shape.

    Non-conforming tool names are listed in ``notes`` so the number is
    explainable.
    """
    finding_id = await todo_finding_id(client, repo)
    result_id = await _sample_result_id(client, repo)
    values = _arg_values(repo, finding_id, result_id)
    manifest = await list_tools_manifest(client)

    conforming = 0
    notes: list[str] = []
    for tool in manifest:
        args = _build_args(tool.input_schema_json, values)
        payload = await call_tool_json(client, tool.name, args)
        if validates_exactly_one(payload):
            conforming += 1
        else:
            notes.append(tool.name)
    total = len(manifest)
    return DimensionResult(
        name="envelope_conformance",
        value=conforming / total,
        unit="share",
        passed=conforming,
        total=total,
        notes=tuple(notes),
    )
