"""Contract: the capability guide, the registered surface, and the docs agree.

These fail on drift in either direction: if a tool is added/removed from the
registered surface without the guide (or docs) following, or vice versa.
"""

import re
from pathlib import Path

import pytest
from fastmcp import Client
from mcp.types import TextResourceContents

from codescent.core.public_surface import registered_mcp_tool_names
from codescent.mcp.guide_tools import GUIDE_RESOURCE_URI
from codescent.mcp.server import mcp
from codescent.services.guide import MAX_TOOLS_PER_GROUP, GuidePayload, build_guide
from tests.contract.guide_payloads import GuidePayloadModel, guide_text

MCP_TOOLS_DOC = Path("docs/mcp-tools.md")


def _service_tool_names(guide: GuidePayload) -> set[str]:
    return {name for group in guide["tool_groups"] for name in group["tools"]}


def test_guide_tool_set_equals_registered_surface() -> None:
    guide = build_guide()
    registered = set(registered_mcp_tool_names())

    # The guide's described tool set must equal the registered surface exactly.
    assert _service_tool_names(guide) == registered
    assert guide["tool_count"] == len(registered)
    # Boundedness must not silently drop a registered tool from the guide.
    assert all(group["omitted_count"] == 0 for group in guide["tool_groups"])
    assert all(
        len(group["tools"]) <= MAX_TOOLS_PER_GROUP for group in guide["tool_groups"]
    )


def test_how_to_use_is_registered_and_documented() -> None:
    registered = registered_mcp_tool_names()
    assert "how_to_use" in registered

    text = MCP_TOOLS_DOC.read_text()
    documented = set(re.findall(r"^### `([^`]+)`$", text, flags=re.MULTILINE))
    # Surface == docs: every documented tool reference is a registered tool and
    # every registered tool has a documented reference.
    assert documented == set(registered)
    assert "how_to_use" in documented


@pytest.mark.anyio
async def test_how_to_use_callable_over_stdio_returns_bounded_payload() -> None:
    async with Client(mcp) as client:
        tools = await client.list_tools()
        assert "how_to_use" in {tool.name for tool in tools}

        result = await client.call_tool("how_to_use", {})

    payload = GuidePayloadModel.model_validate_json(guide_text(result.content))
    assert payload.ok is True
    assert payload.server == "CodeScent"
    assert payload.tool_names() == set(registered_mcp_tool_names())
    serialized = payload.model_dump_json()
    for leaked in ("source_content", "source_ranges", "file_path"):
        assert leaked not in serialized


@pytest.mark.anyio
async def test_guide_resource_matches_tool_payload() -> None:
    async with Client(mcp) as client:
        resources = await client.list_resources()
        assert GUIDE_RESOURCE_URI in {str(resource.uri) for resource in resources}

        tool_result = await client.call_tool("how_to_use", {})
        resource_result = await client.read_resource(GUIDE_RESOURCE_URI)

    tool_payload = GuidePayloadModel.model_validate_json(
        guide_text(tool_result.content)
    )
    assert len(resource_result) == 1
    resource_block = resource_result[0]
    assert isinstance(resource_block, TextResourceContents)
    resource_payload = GuidePayloadModel.model_validate_json(resource_block.text)

    # Same bounded payload from both the tool and the resource.
    assert resource_payload == tool_payload
