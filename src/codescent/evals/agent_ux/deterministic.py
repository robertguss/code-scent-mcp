"""Deterministic agent-experience dimensions (R2-R6), network-free (plan U1-U6).

The dimensions drive the real MCP surface through the in-memory client and score
it with no model in the loop, so they run offline in CI and form the per-cluster
gate for the phase-two consolidation. This module aggregates all six via
:func:`run_deterministic_dimensions` and defines the behavioural scorers
(R2 error-recovery, R3 loop-connectivity, R5 constraint-drop); R4 lives in
``envelope`` and R6 in ``token_cost``.

This module must never import the model-driven ``tool_selection`` path or any
network client: that boundary is what keeps the default suite compliant with
the repo's deterministic-floor invariant (``AGENTS.md``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from codescent.core.errors import ErrorCode
from codescent.core.models import EnvelopeConfidence
from codescent.core.public_surface import registered_mcp_tool_names
from codescent.evals.agent_ux._client import (
    call_tool_json,
    list_tools_manifest,
    todo_finding_id,
)
from codescent.evals.agent_ux._graph import EXPECTED_EDGES, bfs, collect_next_tools
from codescent.evals.agent_ux.envelope import envelope_conformance
from codescent.evals.agent_ux.models import DimensionResult
from codescent.evals.agent_ux.token_cost import manifest_token_cost

if TYPE_CHECKING:
    from pathlib import Path

    from fastmcp import Client
    from fastmcp.client.transports import FastMCPTransport


async def run_deterministic_dimensions(
    client: Client[FastMCPTransport],
    repo: Path,
) -> tuple[DimensionResult, ...]:
    """Score every deterministic dimension (R2-R6) over ``repo``.

    The single ``todo_finding_id`` call scans ``repo`` once and builds the index
    every dimension reuses; the finding id and manifest are then threaded into
    the scorers so no dimension re-scans or re-fetches.

    Args:
        client: An open in-memory ``fastmcp.Client`` session.
        repo: A repository already written by ``build_smelly_repo``.

    Returns:
        The scored deterministic dimensions.
    """
    finding_id = await todo_finding_id(client, repo)
    manifest = await list_tools_manifest(client)
    dimensions: list[DimensionResult] = [
        await manifest_token_cost(client, manifest=manifest),
        await error_recovery(client, repo, finding_id=finding_id),
        await constraint_drop(client, repo),
        await loop_connectivity(client, repo, finding_id=finding_id),
        await envelope_conformance(
            client, repo, finding_id=finding_id, manifest=manifest
        ),
    ]
    return tuple(dimensions)


# --- R3: guided-loop connectivity ----------------------------------------


async def loop_connectivity(
    client: Client[FastMCPTransport],
    repo: Path,
    *,
    finding_id: str | None = None,
) -> DimensionResult:
    """Score R3: the improvement spine forms a connected next_tools chain (AE3).

    Scores 1.0 only when BFS from ``scan_code_health`` reaches both
    ``mark_finding`` and ``record_verification``, no spine tool is a dead end,
    and every emitted target resolves against the registry. Otherwise the
    dead-ends and dangling targets are reported as notes. ``finding_id`` is
    derived from the surface when not supplied by the aggregator.
    """
    if finding_id is None:
        finding_id = await todo_finding_id(client, repo)
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


def _recovery_cases(
    repo: Path,
    finding_id: str,
) -> tuple[tuple[str, dict[str, object], ErrorCode, str], ...]:
    """The four malformed-input calls and the recovery each must carry (AE4)."""
    return (
        (
            "get_finding",
            {"repo": str(repo), "finding_id": "does-not-exist"},
            ErrorCode.NOT_FOUND,
            "available_options",
        ),
        (
            "mark_finding",
            {"repo": str(repo), "finding_id": finding_id, "status": "banana"},
            ErrorCode.INVALID_VALUE,
            "valid_values",
        ),
        (
            "get_symbol_context",
            {"repo": str(repo), "qualified_name": "pkg.config.load_confib"},
            ErrorCode.NOT_FOUND,
            "suggestions",
        ),
        (
            "get_file_context",
            {"repo": str(repo), "path": "src/pkg/confgi.py"},
            ErrorCode.NOT_FOUND,
            "suggestions",
        ),
    )


async def error_recovery(
    client: Client[FastMCPTransport],
    repo: Path,
    *,
    finding_id: str | None = None,
) -> DimensionResult:
    """Score R2: the four malformed-input sites return recoverable errors (AE4).

    ``finding_id`` is derived from the surface when not supplied by the
    aggregator.
    """
    if finding_id is None:
        finding_id = await todo_finding_id(client, repo)
    cases = _recovery_cases(repo, finding_id)
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
    return mentioned and payload.get("confidence") != EnvelopeConfidence.HIGH


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
