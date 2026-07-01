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

from typing import TYPE_CHECKING

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
    ]
    return tuple(dimensions)


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
