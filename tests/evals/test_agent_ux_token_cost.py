"""Tests for the R6 manifest/description token-cost dimension (plan U6)."""

from __future__ import annotations

import pytest

from codescent.evals.agent_ux import build_agent_ux_report
from codescent.evals.agent_ux.deterministic import manifest_cost
from codescent.evals.agent_ux.models import ToolInfo


def _tool(name: str, description: str) -> ToolInfo:
    return ToolInfo(name=name, description=description, input_schema_json="{}")


def test_manifest_cost_total_equals_group_sum() -> None:
    manifest = [_tool("alpha", "find alpha"), _tool("beta", "find beta things")]
    total, per_group = manifest_cost(manifest)
    assert total > 0
    assert total == sum(per_group.values())


def test_removing_a_tool_lowers_cost() -> None:
    manifest = [_tool("alpha", "find alpha"), _tool("beta", "find beta things")]
    full, _ = manifest_cost(manifest)
    fewer, _ = manifest_cost(manifest[:1])
    assert fewer < full  # the monotonic property phase two relies on


@pytest.mark.anyio
async def test_token_cost_dimension_is_reported() -> None:
    report = await build_agent_ux_report()
    dimension = report.dimension("manifest_token_cost")
    assert dimension is not None
    assert dimension.unit == "tokens"
    assert dimension.value > 0
    assert dimension.value == sum(entry.value for entry in dimension.breakdown)
