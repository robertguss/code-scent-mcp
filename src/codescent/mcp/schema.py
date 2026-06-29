"""Machine-readable self-describing schema for the CodeScent MCP surface.

``get_schema`` is the run-this-first companion to ``how_to_use``: it derives the
registered tool list -- each tool's name, group, accepted params, and response
keys -- from the public surface registry plus runtime introspection, alongside
the small set of enumerable type vocabularies and the parameter aliases the
boundary accepts. Everything is derived, never hardcoded, so the schema stays
correct as tools change.
"""

from __future__ import annotations

import importlib
import inspect
from typing import TYPE_CHECKING, Final, TypedDict, cast

from codescent.core.defensive import PARAM_ALIASES
from codescent.core.models import EnvelopeConfidence, EnvelopeMode, FindingStatus
from codescent.core.public_surface import (
    PUBLIC_SURFACE,
    SEARCH_OUTPUT_MODES,
    registered_mcp_tool_names,
)
from codescent.engine.search.constraints import CONSTRAINT_KINDS

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import ModuleType

SERVER_NAME: Final = "CodeScent"
SUMMARY: Final = (
    "Machine-readable CodeScent surface: run this first to orient. Lists every "
    "registered tool with its params and response keys, the enumerable type "
    "vocabularies, and the parameter aliases the boundary accepts."
)

# Tool functions live across these mcp adapter modules; the registered tool name
# matches the function name, so name -> function resolves by scanning them.
_TOOL_MODULES: Final[tuple[str, ...]] = (
    "repo_tools",
    "search_tools",
    "context_tools",
    "answer_pack_tools",
    "result_tools",
    "finding_tools",
    "planning_tools",
    "risk_tools",
    "session_stats_tools",
    "guide_tools",
    "subjective_tools",
)


class SchemaToolEntry(TypedDict):
    name: str
    group: str
    params: tuple[str, ...]
    response_keys: tuple[str, ...]


class SchemaTypeSet(TypedDict):
    name: str
    values: tuple[str, ...]
    count: int


class SchemaAlias(TypedDict):
    alias: str
    canonical: str


class SchemaConstraintKind(TypedDict):
    token: str
    description: str


class SchemaPayload(TypedDict):
    ok: bool
    server: str
    summary: str
    tool_count: int
    tools: tuple[SchemaToolEntry, ...]
    types: tuple[SchemaTypeSet, ...]
    param_aliases: tuple[SchemaAlias, ...]
    # The search/grep ``constraints`` DSL prefilter kinds (plan unit U9).
    constraints: tuple[SchemaConstraintKind, ...]


def build_schema() -> SchemaPayload:
    """Render the self-describing surface from the registered MCP tools.

    Pure and deterministic: the tool list is derived from the public surface
    registry and runtime introspection, so a new tool appears here with no edit
    to this module.

    Returns:
        The bounded, machine-readable :class:`SchemaPayload`.
    """
    registered = registered_mcp_tool_names()
    modules = _load_modules()
    entries = tuple(
        _tool_entry(entry.name, entry.group, modules)
        for entry in PUBLIC_SURFACE.mcp_tools
        if entry.name in registered
    )
    return {
        "ok": True,
        "server": SERVER_NAME,
        "summary": SUMMARY,
        "tool_count": len(entries),
        "tools": entries,
        "types": _type_sets(),
        "param_aliases": tuple(
            {"alias": alias, "canonical": canonical}
            for alias, canonical in sorted(PARAM_ALIASES.items())
        ),
        "constraints": tuple(
            {"token": kind.token, "description": kind.description}
            for kind in CONSTRAINT_KINDS
        ),
    }


def _load_modules() -> tuple[ModuleType, ...]:
    return tuple(
        importlib.import_module(f"codescent.mcp.{name}") for name in _TOOL_MODULES
    )


def _tool_entry(
    name: str,
    group: str,
    modules: tuple[ModuleType, ...],
) -> SchemaToolEntry:
    found = _find_function(name, modules)
    if found is None:
        return {"name": name, "group": group, "params": (), "response_keys": ()}
    fn, module = found
    params = tuple(str(param) for param in inspect.signature(fn).parameters)
    return {
        "name": name,
        "group": group,
        "params": params,
        "response_keys": _response_keys(fn, module),
    }


def _find_function(
    name: str,
    modules: tuple[ModuleType, ...],
) -> tuple[Callable[..., object], ModuleType] | None:
    for module in modules:
        candidate = getattr(module, name, None)
        if callable(candidate):
            return candidate, module
    return None


def _response_keys(fn: Callable[..., object], module: ModuleType) -> tuple[str, ...]:
    return_name = _annotations(fn).get("return")
    if not isinstance(return_name, str):
        return ()
    payload = getattr(module, return_name, None)
    return tuple(_annotations(payload))


def _annotations(obj: object) -> dict[str, object]:
    raw = getattr(obj, "__annotations__", None)
    if not isinstance(raw, dict):
        return {}
    return {str(key): value for key, value in cast("dict[object, object]", raw).items()}


def _type_sets() -> tuple[SchemaTypeSet, ...]:
    return (
        _type_set("output_modes", tuple(sorted(SEARCH_OUTPUT_MODES))),
        _type_set("result_modes", tuple(mode.value for mode in EnvelopeMode)),
        _type_set(
            "confidence_levels",
            tuple(level.value for level in EnvelopeConfidence),
        ),
        _type_set("finding_statuses", tuple(status.value for status in FindingStatus)),
    )


def _type_set(name: str, values: tuple[str, ...]) -> SchemaTypeSet:
    return {"name": name, "values": values, "count": len(values)}
