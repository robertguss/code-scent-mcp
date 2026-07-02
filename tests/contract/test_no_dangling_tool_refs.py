"""Dangling-tool-reference guard (bead P2.0 / U9 -- lands FIRST).

Fails the build on any string-pinned reference to a tool that is not
registered -- the guard that makes the shim-free hard break safe (R14) before
the Phase-2 surface merges land. It covers the whole string-pinned internal
surface, not just ``next_tools``:

  (a) ``next_tools`` targets declared across the MCP tool modules (``:arg``
      deep-link suffixes stripped);
  (b) tool-name literals in ``mcp/prompts.py``;
  (c) sibling tool names named in *prose* inside every live tool description
      (descriptions cross-reference siblings, e.g. "Use scan_code_health");
  (d) the eval seed docs -- ``agent_task.md``'s required-tool sequence and
      ``tool_selection_tasks.json``'s ``intended_tool``/``confusable_with``.

Every reference must resolve against :func:`registered_mcp_tool_names`. A name
that has moved to the locked or absent split (what a surface merge flips) is a
dangling reference and fails here.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest
from fastmcp import Client

from codescent.core.public_surface import (
    known_mcp_tool_names,
    registered_mcp_tool_names,
)
from codescent.mcp.server import mcp

if TYPE_CHECKING:
    from collections.abc import Iterable

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MCP_DIR = _REPO_ROOT / "src" / "codescent" / "mcp"
_PROMPTS = _MCP_DIR / "prompts.py"
_AGENT_TASK = _REPO_ROOT / "evals" / "agent_task.md"
_TOOL_TASKS = _REPO_ROOT / "evals" / "tool_selection_tasks.json"

_TOKEN = re.compile(r"[a-z][a-z0-9_]{2,}")
# ``next_tools=(...)`` literal tuples; ``next_tools=next_tools`` (dynamic
# forwarding) and ``next_tools: tuple[...]`` (annotations) deliberately miss.
_NEXT_TOOLS = re.compile(r"next_tools\s*=\s*\(([^)]*)\)")
_QUOTED = re.compile(r"""["']([a-z][a-z0-9_:]+)["']""")


# --------------------------------------------------------------------------- #
# Pure checkers -- exercised directly by the synthetic negatives below.
# --------------------------------------------------------------------------- #
def unresolved_explicit(
    refs: Iterable[str],
    registered: frozenset[str],
) -> set[str]:
    """Explicit tool references that do not resolve to a registered tool.

    Deep-link forms carry a ``:arg`` suffix; only the tool-name prefix must
    resolve.
    """
    return {ref.split(":", 1)[0] for ref in refs} - registered


def unresolved_prose(
    text: str,
    vocabulary: frozenset[str],
    registered: frozenset[str],
) -> set[str]:
    """Known tool names mentioned in ``text`` that are not registered.

    Only tokens in the known-tool ``vocabulary`` are treated as references, so
    ordinary prose words are ignored while a removed tool's name is caught.
    """
    named = set(_TOKEN.findall(text)) & vocabulary
    return named - registered


# --------------------------------------------------------------------------- #
# Collectors over the real surface.
# --------------------------------------------------------------------------- #
def _next_tools_targets() -> set[str]:
    refs: set[str] = set()
    for path in _MCP_DIR.rglob("*.py"):
        for match in _NEXT_TOOLS.finditer(path.read_text()):
            refs.update(_QUOTED.findall(match.group(1)))
    return refs


def _eval_explicit_refs() -> set[str]:
    tasks = cast("list[dict[str, object]]", json.loads(_TOOL_TASKS.read_text()))
    refs: set[str] = set()
    for task in tasks:
        intended = task.get("intended_tool")
        if isinstance(intended, str):
            refs.add(intended)
        confusable = task.get("confusable_with", ())
        if isinstance(confusable, list):
            items = cast("list[object]", confusable)
            refs.update(item for item in items if isinstance(item, str))
    return refs


async def _description_prose() -> str:
    async with Client(mcp) as client:
        tools = await client.list_tools()
    return "\n".join(tool.description or "" for tool in tools)


# --------------------------------------------------------------------------- #
# Positive: the current surface resolves cleanly.
# --------------------------------------------------------------------------- #
def test_next_tools_targets_all_registered() -> None:
    targets = _next_tools_targets()
    assert targets  # guard against a broken collector silently passing
    assert unresolved_explicit(targets, registered_mcp_tool_names()) == set()


def test_eval_seed_tool_refs_all_registered() -> None:
    refs = _eval_explicit_refs()
    assert refs
    assert unresolved_explicit(refs, registered_mcp_tool_names()) == set()


def test_prompts_name_no_unregistered_tool() -> None:
    assert (
        unresolved_prose(
            _PROMPTS.read_text(),
            known_mcp_tool_names(),
            registered_mcp_tool_names(),
        )
        == set()
    )


def test_agent_task_names_no_unregistered_tool() -> None:
    assert (
        unresolved_prose(
            _AGENT_TASK.read_text(),
            known_mcp_tool_names(),
            registered_mcp_tool_names(),
        )
        == set()
    )


@pytest.mark.anyio
async def test_tool_descriptions_name_no_unregistered_sibling() -> None:
    prose = await _description_prose()
    assert prose  # descriptions must be non-empty for the scan to mean anything
    assert (
        unresolved_prose(prose, known_mcp_tool_names(), registered_mcp_tool_names())
        == set()
    )


# --------------------------------------------------------------------------- #
# Synthetic negatives: each source, made to name a removed tool, fails.
# --------------------------------------------------------------------------- #
def test_synthetic_dangling_next_tools_target_fails() -> None:
    registered = registered_mcp_tool_names()
    refs = {"explain_finding", "merged_away_tool:status", "removed_tool"}
    assert unresolved_explicit(refs, registered) == {"merged_away_tool", "removed_tool"}


def test_synthetic_prompt_naming_removed_tool_fails() -> None:
    vocabulary = known_mcp_tool_names()
    # Pretend a merge moved plan_refactor out of the registered split.
    reduced = registered_mcp_tool_names() - {"plan_refactor"}
    text = "First call explain_finding, then plan_refactor for the change."
    assert unresolved_prose(text, vocabulary, reduced) == {"plan_refactor"}


def test_synthetic_description_naming_removed_sibling_fails() -> None:
    # A description whose vocabulary now includes a removed sibling is caught.
    vocabulary = known_mcp_tool_names() | {"scan_code_health"}
    reduced = registered_mcp_tool_names() - {"scan_code_health"}
    description = "Read-only. Use scan_code_health to refresh findings first."
    assert unresolved_prose(description, vocabulary, reduced) == {"scan_code_health"}


def test_synthetic_eval_naming_removed_tool_fails() -> None:
    registered = registered_mcp_tool_names()
    refs = {"search_files", "explain_finding", "removed_eval_tool"}
    assert unresolved_explicit(refs, registered) == {"removed_eval_tool"}
