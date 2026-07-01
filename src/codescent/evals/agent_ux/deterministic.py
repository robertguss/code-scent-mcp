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

from typing import TYPE_CHECKING, cast

from codescent.core.public_surface import PUBLIC_SURFACE
from codescent.core.token_estimate import estimate_tokens
from codescent.evals.agent_ux._client import call_tool_json, list_tools_manifest
from codescent.evals.agent_ux.models import BreakdownEntry, DimensionResult

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
    ]
    return tuple(dimensions)


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
