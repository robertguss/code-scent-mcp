"""get_schema returns a machine-readable, registry-derived surface."""

from __future__ import annotations

import json
from typing import cast

import pytest
from fastmcp import Client
from mcp.types import ContentBlock, TextContent

from codescent.core.public_surface import registered_mcp_tool_names
from codescent.mcp.guide_tools import get_schema
from codescent.mcp.schema import SchemaPayload, build_schema
from codescent.mcp.server import mcp

_TOP_LEVEL_KEYS = {
    "ok",
    "server",
    "summary",
    "tool_count",
    "tools",
    "types",
    "param_aliases",
    "constraints",
    "next_tools",
}


def test_schema_lists_every_registered_tool() -> None:
    payload = build_schema()
    registered = set(registered_mcp_tool_names())

    # The shape keys are present and the tool set matches the registry exactly.
    assert set(payload) == _TOP_LEVEL_KEYS
    assert payload["ok"] is True
    assert payload["server"] == "CodeScent"
    names = {tool["name"] for tool in payload["tools"]}
    assert names == registered
    assert payload["tool_count"] == len(registered)
    # get_schema describes itself: it is part of the surface it returns.
    assert "get_schema" in names


def test_schema_tool_entries_carry_params_and_response_keys() -> None:
    payload = build_schema()
    by_name = {tool["name"]: tool for tool in payload["tools"]}

    for tool in payload["tools"]:
        assert set(tool) == {"name", "group", "params", "response_keys"}

    search = by_name["search_content"]
    # Surfaces that the search tools take output_mode and expand.
    assert "output_mode" in search["params"]
    assert "expand" in search["params"]
    assert "pattern" in search["params"]
    assert "results" in search["response_keys"]
    # The group is carried straight from the public surface registry.
    assert search["group"] == "search"


def test_schema_exposes_type_vocabularies_with_counts() -> None:
    payload = build_schema()
    types = {entry["name"]: entry for entry in payload["types"]}

    assert {
        "output_modes",
        "result_modes",
        "confidence_levels",
        "finding_statuses",
    } <= set(types)
    assert set(types["output_modes"]["values"]) == {
        "content",
        "files",
        "count",
        "usage",
    }
    for entry in payload["types"]:
        # Counts are meaningful: they match the listed vocabulary length.
        assert entry["count"] == len(entry["values"])
        assert entry["count"] > 0


def test_schema_advertises_the_param_aliases_the_boundary_accepts() -> None:
    payload = build_schema()
    aliases = {entry["alias"]: entry["canonical"] for entry in payload["param_aliases"]}

    assert aliases.get("pattern") == "query"


def test_get_schema_tool_equals_build_schema() -> None:
    assert get_schema() == build_schema()


@pytest.mark.anyio
async def test_get_schema_callable_over_stdio_returns_bounded_payload() -> None:
    async with Client(mcp) as client:
        tools = await client.list_tools()
        assert "get_schema" in {tool.name for tool in tools}

        result = await client.call_tool("get_schema", {})

    payload = cast("SchemaPayload", json.loads(_text_content(result.content)))
    assert payload["ok"] is True
    assert payload["server"] == "CodeScent"
    names = {tool["name"] for tool in payload["tools"]}
    assert {"get_schema", "search_content"} <= names
    assert payload["tool_count"] == len(payload["tools"])


def _text_content(content: list[ContentBlock]) -> str:
    assert len(content) == 1
    first = content[0]
    assert isinstance(first, TextContent)
    return first.text
