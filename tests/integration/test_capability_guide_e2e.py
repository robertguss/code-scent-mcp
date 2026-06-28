"""E2E smoke: boot the MCP path, call how_to_use, read the guide resource."""

import pytest
from fastmcp import Client
from mcp.types import TextResourceContents
from tests.contract.guide_payloads import GuidePayloadModel, guide_text

from codescent.core.public_surface import registered_mcp_tool_names
from codescent.mcp.guide_tools import GUIDE_RESOURCE_URI
from codescent.mcp.server import mcp
from codescent.services.guide import (
    MAX_TOOLS_PER_GROUP,
    SAFETY_BOUNDARIES,
    WORKFLOW,
)


@pytest.mark.anyio
async def test_guide_e2e_over_mcp_path() -> None:
    async with Client(mcp) as client:
        tool_names = {tool.name for tool in await client.list_tools()}
        resource_uris = {str(res.uri) for res in await client.list_resources()}
        tool_result = await client.call_tool("how_to_use", {})
        resource_result = await client.read_resource(GUIDE_RESOURCE_URI)

    assert "how_to_use" in tool_names
    assert GUIDE_RESOURCE_URI in resource_uris

    payload = GuidePayloadModel.model_validate_json(guide_text(tool_result.content))
    assert len(resource_result) == 1
    resource_block = resource_result[0]
    assert isinstance(resource_block, TextResourceContents)
    assert GuidePayloadModel.model_validate_json(resource_block.text) == payload

    # Every registered tool is listed in the guide.
    assert payload.tool_names() == set(registered_mcp_tool_names())

    # All workflow steps and safety boundaries are present.
    assert len(payload.workflow) == len(WORKFLOW)
    assert payload.safety_boundaries == SAFETY_BOUNDARIES

    # Bounded: nothing omitted, per-group cap honored.
    for group in payload.tool_groups:
        assert group.omitted_count == 0
        assert len(group.tools) <= MAX_TOOLS_PER_GROUP

    # No analyzed source leaked.
    serialized = payload.model_dump_json()
    for leaked in ("source_content", "source_ranges", "file_path"):
        assert leaked not in serialized
