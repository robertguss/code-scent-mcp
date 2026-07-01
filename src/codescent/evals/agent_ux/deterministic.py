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

from codescent.evals.agent_ux._client import call_tool_json

if TYPE_CHECKING:
    from pathlib import Path

    from fastmcp import Client
    from fastmcp.client.transports import FastMCPTransport

    from codescent.evals.agent_ux.models import DimensionResult


async def run_deterministic_dimensions(
    client: Client[FastMCPTransport],
    repo: Path,
) -> tuple[DimensionResult, ...]:
    """Score the deterministic dimensions (R2-R6) over ``repo``.

    ``repo`` is scanned once here so every dimension reuses the same index. U1
    ships this as an empty aggregator; U2-U6 each append their scorer to the
    ``dimensions`` list below.

    Args:
        client: An open in-memory ``fastmcp.Client`` session.
        repo: A repository already written by ``build_smelly_repo``.

    Returns:
        The scored deterministic dimensions.
    """
    _ = await call_tool_json(client, "scan_code_health", {"repo": str(repo)})
    dimensions: list[DimensionResult] = []
    # U2-U6 append their scored dimensions to this list before it is returned.
    return tuple(dimensions)
