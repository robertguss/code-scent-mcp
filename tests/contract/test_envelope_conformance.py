"""ok_envelope() + the tools wired through it (bead P3.3 / U3).

Every success payload must carry ok:True AND a next_tools array whose entries
resolve to registered tools; terminal discovery tools carry an empty array.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

import pytest
from fastmcp import Client
from mcp.types import ContentBlock, TextContent

from codescent.core.public_surface import registered_mcp_tool_names
from codescent.mcp.finding_payloads import ok_envelope
from codescent.mcp.server import mcp

if TYPE_CHECKING:
    from pathlib import Path

# Wired tools reachable with just a repo arg (bead P3.3). The arg-heavy tools
# (get_symbol_context, get_impact, ...) are covered by the envelope_conformance
# eval dimension; here we assert the plain-repo ones directly.
_REPO_ONLY_WIRED = (
    "get_repo_map",
    "get_repo_status",
    "get_architecture",
    "get_calibration",
    "review_diff_risk",
)
_TERMINAL_TOOLS = ("how_to_use", "get_schema")


def _text(content: list[ContentBlock]) -> str:
    assert len(content) == 1
    first = content[0]
    assert isinstance(first, TextContent)
    return first.text


def test_ok_envelope_injects_ok_and_next_tools() -> None:
    assert ok_envelope(next_tools=("scan_code_health",), file_count=3) == {
        "ok": True,
        "file_count": 3,
        "next_tools": ("scan_code_health",),
    }


@pytest.mark.anyio
async def test_repo_only_wired_tools_emit_resolvable_next_tools(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "pkg").mkdir(parents=True)
    _ = (repo / "pkg" / "mod.py").write_text("def f() -> int:\n    return 1\n")
    registered = registered_mcp_tool_names()

    async with Client(mcp) as client:
        _ = await client.call_tool("scan_code_health", {"repo": str(repo)})
        for name in _REPO_ONLY_WIRED:
            raw = await client.call_tool(name, {"repo": str(repo)})
            payload = cast("dict[str, object]", json.loads(_text(raw.content)))
            assert payload["ok"] is True, name
            next_tools = payload["next_tools"]
            assert isinstance(next_tools, list)
            assert next_tools, name  # non-terminal tools suggest a next step
            for target in cast("list[str]", next_tools):
                assert target.split(":", 1)[0] in registered, (name, target)


@pytest.mark.anyio
async def test_terminal_tools_conform_with_empty_next_tools() -> None:
    async with Client(mcp) as client:
        for name in _TERMINAL_TOOLS:
            raw = await client.call_tool(name, {})
            payload = cast("dict[str, object]", json.loads(_text(raw.content)))
            assert payload["ok"] is True, name
            assert payload["next_tools"] == [], name
