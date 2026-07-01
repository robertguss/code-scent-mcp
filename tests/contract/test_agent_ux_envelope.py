"""Tests for the R4 envelope-conformance dimension (plan U2)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastmcp import Client

from codescent.evals.agent_ux import build_smelly_repo, call_tool_json
from codescent.evals.agent_ux.envelope import envelope_conformance
from codescent.evals.agent_ux.schemas import validates_exactly_one
from codescent.mcp.server import mcp

if TYPE_CHECKING:
    from pathlib import Path

_EXPECTED_TOOL_COUNT = 48


@pytest.mark.anyio
async def test_envelope_conformance_scored_over_full_surface(tmp_path: Path) -> None:
    repo = build_smelly_repo(tmp_path)
    async with Client(mcp) as client:
        _ = await call_tool_json(client, "scan_code_health", {"repo": str(repo)})
        dimension = await envelope_conformance(client, repo)
    assert dimension.name == "envelope_conformance"
    assert dimension.unit == "share"
    assert dimension.total == _EXPECTED_TOOL_COUNT
    assert 0.0 <= dimension.value <= 1.0


def test_success_envelope_matches_only_success() -> None:
    assert validates_exactly_one({"ok": True, "next_tools": []})


def test_error_envelope_matches_only_error() -> None:
    assert validates_exactly_one(
        {
            "ok": False,
            "code": "not_found",
            "message": "no such finding",
            "recoverable": True,
            "data": {},
        }
    )


def test_bare_dict_matches_neither() -> None:
    # A response with no `ok` field conforms to neither envelope (the R4 gap).
    assert not validates_exactly_one({"result_id": "ctx_0", "items": []})
