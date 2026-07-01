"""Deterministic agent-experience dimensions (R2-R6), network-free (plan U1-U6).

These dimensions drive the real MCP surface through the in-memory client and
score it with no model in the loop, so they run offline in CI and form the
per-cluster gate for the phase-two consolidation. Each dimension is appended to
:func:`run_deterministic_dimensions`.

This module must never import the model-driven ``tool_selection`` path or any
network client: that boundary is what keeps the default suite compliant with
the repo's deterministic-floor invariant (``AGENTS.md``).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from codescent.core.public_surface import PUBLIC_SURFACE, registered_mcp_tool_names
from codescent.core.token_estimate import estimate_tokens
from codescent.evals.agent_ux._client import call_tool_json, list_tools_manifest
from codescent.evals.agent_ux._graph import EXPECTED_EDGES, bfs, collect_next_tools
from codescent.evals.agent_ux.models import BreakdownEntry, DimensionResult
from codescent.evals.agent_ux.schemas import validates_exactly_one

if TYPE_CHECKING:
    from pathlib import Path

    from fastmcp import Client
    from fastmcp.client.transports import FastMCPTransport

    from codescent.evals.agent_ux.models import ToolInfo

_GROUP_BY_TOOL: dict[str, str] = {
    entry.name: entry.group for entry in PUBLIC_SURFACE.mcp_tools if entry.registered
}


async def run_deterministic_dimensions(
    client: Client[FastMCPTransport],
    repo: Path,
) -> tuple[DimensionResult, ...]:
    """Score the deterministic dimensions (R2-R6) over ``repo``.

    ``repo`` is scanned once here so every dimension reuses the same index. U2-U5
    each append their scorer to the ``dimensions`` list below; R6 needs only the
    manifest.

    Args:
        client: An open in-memory ``fastmcp.Client`` session.
        repo: A repository already written by ``build_smelly_repo``.

    Returns:
        The scored deterministic dimensions.
    """
    _ = await call_tool_json(client, "scan_code_health", {"repo": str(repo)})
    dimensions: list[DimensionResult] = [
        await manifest_token_cost(client),
        await error_recovery(client, repo),
        await constraint_drop(client, repo),
        await loop_connectivity(client, repo),
        await envelope_conformance(client, repo),
    ]
    return tuple(dimensions)


# --- R4: envelope conformance --------------------------------------------


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

    Below 100% at baseline -- several tools emit ad-hoc success dicts -- which is
    the gap phase two (U14) closes. Non-conforming tool names are listed in
    ``notes`` so the number is explainable.
    """
    finding_id = await _todo_finding_id(client, repo)
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


# --- R3: guided-loop connectivity ----------------------------------------


async def loop_connectivity(
    client: Client[FastMCPTransport],
    repo: Path,
) -> DimensionResult:
    """Score R3: the improvement spine forms a connected next_tools chain (AE3).

    Scores 1.0 only when BFS from ``scan_code_health`` reaches both
    ``mark_finding`` and ``record_verification``, no spine tool is a dead end,
    and every emitted target resolves against the registry. Otherwise the
    dead-ends and dangling targets are reported as notes.
    """
    finding_id = await _todo_finding_id(client, repo)
    graph = await collect_next_tools(client, repo, finding_id)
    registered = registered_mcp_tool_names()
    reachable = bfs("scan_code_health", graph)

    reaches_spine = "mark_finding" in reachable and "record_verification" in reachable
    dead_ends = [tool for tool in EXPECTED_EDGES if not graph.get(tool)]
    dangling = [
        f"{source}->{target}"
        for source, targets in graph.items()
        for target in targets
        if target.split(":", 1)[0] not in registered
    ]
    connected = reaches_spine and not dead_ends and not dangling

    notes: list[str] = []
    if not reaches_spine:
        notes.append("spine does not reach mark_finding/record_verification")
    notes.extend(f"dead-end: {tool}" for tool in dead_ends)
    notes.extend(f"dangling: {edge}" for edge in dangling)
    return DimensionResult(
        name="loop_connectivity",
        value=1.0 if connected else 0.0,
        unit="share",
        passed=1 if connected else 0,
        total=1,
        notes=tuple(notes),
    )


# --- R2: error-recovery readiness ----------------------------------------


def recoverable_with_hint(
    payload: dict[str, object],
    expected_code: str,
    recovery_key: str,
) -> bool:
    """Return whether ``payload`` is a recoverable error with actionable data.

    A malformed-input call passes only when the error boundary marked it
    recoverable (a domain error, not ``internal``), the code matches, and the
    recovery bag carries both the site-specific key (``available_options`` /
    ``valid_values`` / ``suggestions``) and a ``fix_hint`` -- everything an
    agent needs to reach a valid next call without an out-of-band failure.
    """
    if payload.get("ok") is not False or payload.get("recoverable") is not True:
        return False
    if payload.get("code") != expected_code:
        return False
    data = payload.get("data")
    if not isinstance(data, dict):
        return False
    typed = cast("dict[str, object]", data)
    return bool(typed.get(recovery_key)) and bool(typed.get("fix_hint"))


async def _todo_finding_id(
    client: Client[FastMCPTransport],
    repo: Path,
) -> str:
    """Return the fixture's ``python.todo_cluster`` finding id via the surface."""
    scan = await call_tool_json(client, "scan_code_health", {"repo": str(repo)})
    ids = scan.get("finding_ids")
    if not isinstance(ids, list):
        msg = "scan payload has no finding_ids list"
        raise TypeError(msg)
    for item in cast("list[object]", ids):
        if isinstance(item, str) and item.startswith("python.todo_cluster"):
            return item
    msg = "no python.todo_cluster finding in the fixture"
    raise ValueError(msg)


async def error_recovery(
    client: Client[FastMCPTransport],
    repo: Path,
) -> DimensionResult:
    """Score R2: the four malformed-input sites return recoverable errors (AE4)."""
    finding_id = await _todo_finding_id(client, repo)
    cases: tuple[tuple[str, dict[str, object], str, str], ...] = (
        (
            "get_finding",
            {"repo": str(repo), "finding_id": "does-not-exist"},
            "not_found",
            "available_options",
        ),
        (
            "mark_finding",
            {"repo": str(repo), "finding_id": finding_id, "status": "banana"},
            "invalid_value",
            "valid_values",
        ),
        (
            "get_symbol_context",
            {"repo": str(repo), "qualified_name": "pkg.config.load_confib"},
            "not_found",
            "suggestions",
        ),
        (
            "get_file_context",
            {"repo": str(repo), "path": "src/pkg/confgi.py"},
            "not_found",
            "suggestions",
        ),
    )
    passed = 0
    notes: list[str] = []
    for tool, args, expected_code, recovery_key in cases:
        payload = await call_tool_json(client, tool, args)
        if recoverable_with_hint(payload, expected_code, recovery_key):
            passed += 1
        else:
            code = payload.get("code")
            notes.append(f"{tool}: no recoverable {recovery_key} (code={code})")
    total = len(cases)
    return DimensionResult(
        name="error_recovery",
        value=passed / total,
        unit="share",
        passed=passed,
        total=total,
        notes=tuple(notes),
    )


# --- R6: manifest & description token cost -------------------------------


def manifest_cost(manifest: list[ToolInfo]) -> tuple[int, dict[str, int]]:
    """Sum ``estimate_tokens`` over each tool's name, description, and schema.

    Returns the surface total and a per-group breakdown. The count is monotonic
    in the number of tools -- the property phase two relies on to prove 48->~31
    lowers manifest cost -- because each tool contributes a non-negative charge.

    Args:
        manifest: The live ``tools/list`` manifest entries.

    Returns:
        A ``(total_tokens, tokens_by_group)`` pair.
    """
    total = 0
    per_group: dict[str, int] = {}
    for tool in manifest:
        cost = (
            estimate_tokens(tool.name)
            + estimate_tokens(tool.description)
            + estimate_tokens(tool.input_schema_json)
        )
        total += cost
        group = _GROUP_BY_TOOL.get(tool.name, "unknown")
        per_group[group] = per_group.get(group, 0) + cost
    return total, per_group


async def manifest_token_cost(
    client: Client[FastMCPTransport],
) -> DimensionResult:
    """Score R6: the token size of the ``tools/list`` manifest + descriptions."""
    manifest = await list_tools_manifest(client)
    total, per_group = manifest_cost(manifest)
    breakdown = tuple(
        BreakdownEntry(label=group, value=float(cost))
        for group, cost in sorted(per_group.items())
    )
    return DimensionResult(
        name="manifest_token_cost",
        value=float(total),
        unit="tokens",
        breakdown=breakdown,
    )


# --- R5: constraint-drop detection ---------------------------------------

_CONSTRAINT_SEARCH_TOOLS: tuple[tuple[str, dict[str, object]], ...] = (
    ("search_files", {"query": "load"}),
    ("search_content", {"query": "load"}),
    ("multi_search_content", {"queries": ["load"]}),
)
_MALFORMED_CONSTRAINTS: tuple[str, ...] = (
    "size:banana",
    "mtime:soon",
    "git:nonsense",
    "bogus:1",
)


def constraint_surfaced(payload: dict[str, object], token: str) -> bool:
    """Return whether a dropped constraint ``token`` is surfaced to the caller.

    Passes only when the token appears in ``constraint_warnings`` and the
    result ``confidence`` was downgraded off ``high`` -- i.e. the malformed
    filter was reported, not silently applied as no filter (F2 / AE2).
    """
    warnings = payload.get("constraint_warnings")
    if not isinstance(warnings, list):
        return False
    mentioned = any(
        isinstance(entry, str) and token in entry
        for entry in cast("list[object]", warnings)
    )
    return mentioned and payload.get("confidence") != "high"


async def constraint_drop(
    client: Client[FastMCPTransport],
    repo: Path,
) -> DimensionResult:
    """Score R5: malformed constraint tokens surface, never silently drop (AE2)."""
    passed = 0
    notes: list[str] = []
    for tool, base_args in _CONSTRAINT_SEARCH_TOOLS:
        for token in _MALFORMED_CONSTRAINTS:
            args: dict[str, object] = {
                **base_args,
                "repo": str(repo),
                "constraints": token,
            }
            payload = await call_tool_json(client, tool, args)
            if constraint_surfaced(payload, token):
                passed += 1
            else:
                notes.append(f"{tool}: {token} not surfaced")
    total = len(_CONSTRAINT_SEARCH_TOOLS) * len(_MALFORMED_CONSTRAINTS)
    return DimensionResult(
        name="constraint_drop",
        value=passed / total,
        unit="share",
        passed=passed,
        total=total,
        notes=tuple(notes),
    )
