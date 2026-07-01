"""Tests for the R5 constraint-drop dimension (plan U4, covers AE2)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastmcp import Client

from codescent.evals.agent_ux import build_smelly_repo, call_tool_json
from codescent.evals.agent_ux.deterministic import constraint_drop, constraint_surfaced
from codescent.mcp.server import mcp

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.anyio
async def test_all_malformed_tokens_surface(tmp_path: Path) -> None:
    repo = build_smelly_repo(tmp_path)
    async with Client(mcp) as client:
        _ = await call_tool_json(client, "scan_code_health", {"repo": str(repo)})
        dimension = await constraint_drop(client, repo)
    assert dimension.name == "constraint_drop"
    assert dimension.unit == "share"
    # AE2: every malformed token on every constraint-accepting search tool is
    # surfaced (3 tools x 4 token families = 12 cases).
    assert dimension.total == 12
    assert dimension.value == 1.0
    assert dimension.notes == ()


@pytest.mark.anyio
async def test_well_formed_constraint_is_not_flagged(tmp_path: Path) -> None:
    # A valid constraint must not false-positive as a dropped token.
    repo = build_smelly_repo(tmp_path)
    async with Client(mcp) as client:
        _ = await call_tool_json(client, "scan_code_health", {"repo": str(repo)})
        payload = await call_tool_json(
            client,
            "search_content",
            {"repo": str(repo), "query": "load", "constraints": "size:<10kb"},
        )
    assert not constraint_surfaced(payload, "size:<10kb")


def test_constraint_surfaced_requires_warning_and_downgrade() -> None:
    surfaced: dict[str, object] = {
        "constraint_warnings": ["ignored 'size:banana' - expected e.g. size:<10kb"],
        "confidence": "medium",
    }
    assert constraint_surfaced(surfaced, "size:banana")

    silent: dict[str, object] = {"constraint_warnings": [], "confidence": "high"}
    assert not constraint_surfaced(silent, "size:banana")
