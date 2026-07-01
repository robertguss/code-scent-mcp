"""R6 manifest/description token-cost dimension (plan U6), network-free.

Sums the token weight of the ``tools/list`` manifest -- each tool's name,
description, and input schema -- so the phase-two consolidation can prove a
smaller surface is a cheaper surface. The count is monotonic in the tool count.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from codescent.core.public_surface import PUBLIC_SURFACE
from codescent.core.token_estimate import estimate_tokens
from codescent.evals.agent_ux._client import list_tools_manifest
from codescent.evals.agent_ux.models import BreakdownEntry, DimensionResult

if TYPE_CHECKING:
    from fastmcp import Client
    from fastmcp.client.transports import FastMCPTransport

    from codescent.evals.agent_ux.models import ToolInfo

_GROUP_BY_TOOL: dict[str, str] = {
    entry.name: entry.group for entry in PUBLIC_SURFACE.mcp_tools if entry.registered
}


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
    *,
    manifest: list[ToolInfo] | None = None,
) -> DimensionResult:
    """Score R6: the token size of the ``tools/list`` manifest + descriptions.

    ``manifest`` is fetched from the surface when not supplied by the aggregator.
    """
    if manifest is None:
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
