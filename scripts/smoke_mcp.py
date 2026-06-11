#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "anyio",
#     "fastmcp>=2.12",
#     "typer>=0.12",
#     "pydantic>=2.0",
#     "rapidfuzz>=3.0",
# ]
# ///

# ─── How to run ───
# 1. Install uv (if not installed):
#      curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run directly (no venv, no pip install needed):
#      uv run scripts/smoke_mcp.py --repo tests/fixtures/python-basic get_repo_map
# 3. Or make executable and run:
#      chmod +x scripts/smoke_mcp.py && ./scripts/smoke_mcp.py --repo <repo> <tool>
# ──────────────────

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Final

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import anyio
import typer
from fastmcp import Client
from pydantic import TypeAdapter

from codescent.engine.inventory import build_file_inventory
from codescent.mcp.server import mcp
from codescent.services.repo_index import RepoIndexService

type JsonValue = (
    None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
)
JSON_VALUE_ADAPTER: Final[TypeAdapter[JsonValue]] = TypeAdapter(JsonValue)

FULL_LOOP_TOOLS: Final[tuple[str, ...]] = (
    "scan_code_health",
    "get_next_improvement",
    "get_finding_context",
    "plan_refactor",
    "suggest_tests",
    "rescan",
    "mark_finding",
)
SEARCH_EXPANSION_TOOLS: Final[tuple[str, ...]] = (
    "multi_search_content:pending-review,workflow",
)
SEARCH_CHANGED_TOOLS: Final[tuple[str, ...]] = ("search_changed_files",)
SEARCH_TODOS_TESTS_TOOLS: Final[tuple[str, ...]] = (
    "search_todos:config",
    "search_tests:workflow",
)
SEARCH_FRECENCY_TOOLS: Final[tuple[str, ...]] = (
    "search_files:workflow",
    "search_files:workflow",
    "search_content:pending-review",
)
GRAPH_CONTEXT_TOOLS: Final[tuple[str, ...]] = (
    "find_references:print",
    "find_callers:print",
    "find_callees:build_daily_plan",
)
EXPANDED_TOOL_SETS: Final[dict[tuple[str, ...], tuple[str, ...]]] = {
    ("full_loop",): FULL_LOOP_TOOLS,
    ("search_expansion",): SEARCH_EXPANSION_TOOLS,
    ("search_changed",): SEARCH_CHANGED_TOOLS,
    ("search_todos_tests",): SEARCH_TODOS_TESTS_TOOLS,
    ("search_frecency",): SEARCH_FRECENCY_TOOLS,
    ("graph_context",): GRAPH_CONTEXT_TOOLS,
}


@dataclass(frozen=True, slots=True)
class ToolCall:
    name: str
    arguments: dict[str, JsonValue]


async def _call_tools(repo: str, tools: tuple[str, ...]) -> dict[str, JsonValue]:
    transcript: list[JsonValue] = []
    current_finding_id: str | None = None
    async with Client(mcp) as client:
        for tool in tools:
            if tool == "list_tools":
                listed = await client.list_tools()
                transcript.append(
                    {
                        "tool": "list_tools",
                        "data": {
                            "tools": _to_json_value(
                                sorted(item.name for item in listed),
                            ),
                        },
                    },
                )
                continue
            tool_call = _parse_tool_call(tool, repo)
            if tool_call.name == "mark_finding" and current_finding_id is not None:
                tool_call.arguments["finding_id"] = current_finding_id
            if (
                tool_call.name
                in {
                    "get_finding_context",
                    "plan_refactor",
                    "suggest_tests",
                }
                and current_finding_id is not None
            ):
                tool_call.arguments["finding_id"] = current_finding_id
            result = await client.call_tool(tool_call.name, tool_call.arguments)
            data = _to_json_value(result.structured_content or {})
            current_finding_id = _next_finding_id(
                tool_call.name,
                data,
                current_finding_id,
            )
            transcript.append(
                {
                    "tool": tool_call.name,
                    "data": data,
                },
            )
    return {"calls": transcript}


def _parse_tool_call(raw_tool: str, repo: str) -> ToolCall:
    if ":" not in raw_tool:
        return _tool_call_without_arg(raw_tool, repo)
    tool_name, query = raw_tool.split(":", maxsplit=1)
    if tool_name == "multi_search_content":
        queries = [item.strip() for item in query.split(",") if item.strip()]
        return ToolCall(
            name=tool_name,
            arguments={"repo": repo, "queries": _to_json_value(queries)},
        )
    if tool_name == "get_file_context":
        return ToolCall(name=tool_name, arguments={"repo": repo, "path": query})
    if tool_name == "get_symbol_context":
        return ToolCall(
            name=tool_name,
            arguments={"repo": repo, "qualified_name": query},
        )
    if tool_name == "mark_finding":
        return ToolCall(
            name=tool_name,
            arguments={"repo": repo, "finding_id": query, "status": "in_progress"},
        )
    return ToolCall(name=tool_name, arguments={"repo": repo, "query": query})


def _tool_call_without_arg(raw_tool: str, repo: str) -> ToolCall:
    if raw_tool == "mark_finding":
        return ToolCall(
            name=raw_tool,
            arguments={
                "repo": repo,
                "status": "needs_review",
                "note": "final smoke loop reviewed after rescan evidence",
            },
        )
    return ToolCall(name=raw_tool, arguments={"repo": repo})


def _next_finding_id(
    tool_name: str,
    data: JsonValue,
    fallback: str | None,
) -> str | None:
    if tool_name == "rescan":
        return fallback
    if not isinstance(data, dict):
        return fallback
    finding_id = data.get("finding_id")
    if isinstance(finding_id, str) and finding_id:
        return finding_id
    finding_ids = data.get("finding_ids")
    if isinstance(finding_ids, list) and finding_ids:
        first = finding_ids[0]
        if isinstance(first, str):
            return first
    return fallback


def _to_json_value(value: object) -> JsonValue:
    return JSON_VALUE_ADAPTER.validate_python(value)


def _expanded_tools(tools: tuple[str, ...]) -> tuple[str, ...]:
    return EXPANDED_TOOL_SETS.get(tools, tools)


def prepare_repo_for_tools(repo: Path, tools: tuple[str, ...]) -> None:
    if tools == ("search_changed",):
        shutil.rmtree(repo / ".codescent", ignore_errors=True)
    if tools == ("graph_context",):
        shutil.rmtree(repo / ".codescent", ignore_errors=True)
        _ = RepoIndexService(repo).index_repo()


def _source_hashes(repo: Path) -> dict[str, str]:
    return {
        item.path: hashlib.sha256((repo / item.path).read_bytes()).hexdigest()
        for item in build_file_inventory(repo)
    }


def _source_read_only(repo: Path, before: dict[str, str]) -> dict[str, JsonValue]:
    after = _source_hashes(repo)
    changed_paths = sorted(
        path for path in set(before) | set(after) if before.get(path) != after.get(path)
    )
    return {
        "source_hashes_unchanged": before == after,
        "changed_source_paths": _to_json_value(changed_paths),
        "allowed_runtime_state": ".codescent",
    }


def main(
    repo: Annotated[str, typer.Option()],
    tools: Annotated[list[str], typer.Argument()],
    out: Annotated[Path | None, typer.Option()] = None,
) -> None:
    repo_path = Path(repo)
    prepare_repo_for_tools(repo_path, tuple(tools))
    before = _source_hashes(repo_path)
    payload = anyio.run(_call_tools, repo, _expanded_tools(tuple(tools)))
    payload["source_read_only"] = _source_read_only(repo_path, before)
    rendered = json.dumps(payload, indent=2, sort_keys=True)
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        _ = out.write_text(rendered)
    typer.echo(rendered)


if __name__ == "__main__":
    typer.run(main)
