"""Tests for the R2 error-recovery dimension (plan U3, covers AE4)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastmcp import Client

from codescent.evals.agent_ux import build_smelly_repo, call_tool_json
from codescent.evals.agent_ux.deterministic import error_recovery, recoverable_with_hint
from codescent.mcp.server import mcp

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.anyio
async def test_all_four_recovery_sites_are_recoverable(tmp_path: Path) -> None:
    repo = build_smelly_repo(tmp_path)
    async with Client(mcp) as client:
        _ = await call_tool_json(client, "scan_code_health", {"repo": str(repo)})
        dimension = await error_recovery(client, repo)
    assert dimension.name == "error_recovery"
    assert dimension.unit == "share"
    # AE4: every Phase-1 recovery site returns a recoverable, actionable error.
    assert dimension.passed == 4
    assert dimension.value == 1.0
    assert dimension.notes == ()


def test_recoverable_with_hint_accepts_domain_error_with_data() -> None:
    payload: dict[str, object] = {
        "ok": False,
        "recoverable": True,
        "code": "not_found",
        "data": {"available_options": ["a"], "fix_hint": "call list_findings"},
    }
    assert recoverable_with_hint(payload, "not_found", "available_options")


def test_recoverable_with_hint_rejects_internal_error() -> None:
    payload: dict[str, object] = {
        "ok": False,
        "recoverable": False,
        "code": "internal",
        "data": {},
    }
    assert not recoverable_with_hint(payload, "not_found", "available_options")


def test_recoverable_with_hint_rejects_missing_fix_hint() -> None:
    payload: dict[str, object] = {
        "ok": False,
        "recoverable": True,
        "code": "not_found",
        "data": {"available_options": ["a"]},
    }
    assert not recoverable_with_hint(payload, "not_found", "available_options")
