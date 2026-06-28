"""E2E proof for the capability guide (U1).

Boots the MCP path in-process, calls the ``how_to_use`` tool, reads the
``codescent://guide`` resource, and asserts the guide lists every registered
tool, all workflow steps, the safety boundaries, stays bounded, and leaks no
analyzed source. Verbose per-assertion logging (expected vs found), mirroring
``scripts/prove_source_read_only.py``.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Annotated

import typer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastmcp import Client
from mcp.types import TextResourceContents

from codescent.core.public_surface import registered_mcp_tool_names
from codescent.mcp.guide_tools import GUIDE_RESOURCE_URI
from codescent.mcp.server import mcp
from codescent.services.guide import (
    MAX_TOOLS_PER_GROUP,
    SAFETY_BOUNDARIES,
    WORKFLOW,
)

JsonValue = object
SOURCE_LEAK_MARKERS = ("source_content", "source_ranges", "file_path", "/home/")


def _check(
    checks: list[dict[str, JsonValue]],
    name: str,
    *,
    expected: JsonValue,
    found: JsonValue,
    ok: bool,
) -> None:
    checks.append({"name": name, "expected": expected, "found": found, "ok": ok})
    status = "OK" if ok else "FAIL"
    typer.echo(f"[{status}] {name}: expected={expected!r} found={found!r}")


def _guide_tool_names(payload: dict[str, JsonValue]) -> set[str]:
    names: set[str] = set()
    for group in payload["tool_groups"]:
        names.update(group["tools"])
    return names


async def collect_checks() -> list[dict[str, JsonValue]]:
    registered = set(registered_mcp_tool_names())
    checks: list[dict[str, JsonValue]] = []

    async with Client(mcp) as client:
        tool_names = {tool.name for tool in await client.list_tools()}
        resource_uris = {str(res.uri) for res in await client.list_resources()}
        tool_result = await client.call_tool("how_to_use", {})
        resource_result = await client.read_resource(GUIDE_RESOURCE_URI)

    _check(
        checks,
        "how_to_use tool registered",
        expected=True,
        found="how_to_use" in tool_names,
        ok="how_to_use" in tool_names,
    )
    _check(
        checks,
        "codescent://guide resource registered",
        expected=True,
        found=GUIDE_RESOURCE_URI in resource_uris,
        ok=GUIDE_RESOURCE_URI in resource_uris,
    )

    tool_text = tool_result.content[0].text  # pyright: ignore[reportAttributeAccessIssue]
    payload: dict[str, JsonValue] = json.loads(tool_text)

    resource_block = resource_result[0]
    resource_payload = (
        json.loads(resource_block.text)
        if isinstance(resource_block, TextResourceContents)
        else None
    )
    _check(
        checks,
        "resource payload equals tool payload",
        expected=payload,
        found=resource_payload,
        ok=resource_payload == payload,
    )

    guide_tools = _guide_tool_names(payload)
    missing = sorted(registered - guide_tools)
    extra = sorted(guide_tools - registered)
    _check(
        checks,
        "guide lists every registered tool",
        expected=sorted(registered),
        found=sorted(guide_tools),
        ok=not missing and not extra,
    )

    workflow_steps = payload["workflow"]
    _check(
        checks,
        "all workflow steps present",
        expected=len(WORKFLOW),
        found=len(workflow_steps),
        ok=len(workflow_steps) == len(WORKFLOW),
    )

    boundaries = payload["safety_boundaries"]
    _check(
        checks,
        "all safety boundaries present",
        expected=list(SAFETY_BOUNDARIES),
        found=boundaries,
        ok=list(boundaries) == list(SAFETY_BOUNDARIES),
    )

    groups = payload["tool_groups"]
    bounded = all(
        group["omitted_count"] == 0 and len(group["tools"]) <= MAX_TOOLS_PER_GROUP
        for group in groups
    )
    _check(
        checks,
        "payload is bounded (nothing omitted, per-group cap honored)",
        expected=True,
        found=bounded,
        ok=bounded,
    )

    serialized = json.dumps(payload)
    leaked = [marker for marker in SOURCE_LEAK_MARKERS if marker in serialized]
    _check(
        checks,
        "no analyzed source leaked",
        expected=[],
        found=leaked,
        ok=not leaked,
    )

    return checks


def prove_capability_guide(out: Path) -> dict[str, JsonValue]:
    checks = asyncio.run(collect_checks())
    payload: dict[str, JsonValue] = {
        "ok": all(bool(check["ok"]) for check in checks),
        "checks": checks,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    _ = out.write_text(json.dumps(payload, indent=2, sort_keys=True))
    return payload


def main(out: Annotated[Path, typer.Option()]) -> None:
    payload = prove_capability_guide(out)
    typer.echo(json.dumps({"ok": payload["ok"]}))


if __name__ == "__main__":
    typer.run(main)
