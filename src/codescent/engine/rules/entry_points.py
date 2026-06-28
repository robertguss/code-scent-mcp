from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from codescent.core.models import ProjectConfig
from codescent.core.paths import resolve_repo_root
from codescent.core.public_surface import PUBLIC_SURFACE
from codescent.engine.inventory import build_file_inventory
from codescent.engine.source_read import read_source_text

if TYPE_CHECKING:
    from pathlib import Path

# Attribute names that publish a callable as an externally invoked entry point:
# FastMCP `mcp.tool(...)`, Typer `app.command(...)`, plus FastMCP resources and
# prompts. Matched on the attribute name so the receiver object can be anything
# (`mcp`, `app`, a locally renamed handle, ...).
_REGISTRATION_ATTRS: Final = frozenset({"tool", "command", "resource", "prompt"})

# getattr(obj, "name") needs at least the object and the attribute-name argument.
_GETATTR_MIN_ARGS: Final = 2

_REASON_MCP_TOOL: Final = "registered MCP tool (core.public_surface)"
_REASON_CLI_COMMAND: Final = "registered CLI command (core.public_surface)"
_REASON_ALL_EXPORT: Final = "exported via __all__"
_REASON_DYNAMIC_DISPATCH: Final = "reachable via dynamic dispatch (getattr)"


@dataclass(frozen=True, slots=True)
class EntryPointRegistry:
    """Map of symbol name -> why it is reachable from outside the call graph.

    Consumed by dead-code detection so registered/exported/decorated callables
    (e.g. the `how_to_use` MCP tool) are never flagged dead despite having an
    internal in-degree of zero.
    """

    reasons: dict[str, str]

    def is_entry_point(self, name: str) -> bool:
        return name in self.reasons

    def reason_for(self, name: str) -> str | None:
        return self.reasons.get(name)


def registered_surface_reasons() -> dict[str, str]:
    """Entry points sourced from the authoritative public surface registry.

    Covers every registered MCP tool name and CLI command name. This is the
    channel that keeps `how_to_use`, `resume_task` and
    `refactor_preflight` (and every other registered tool/command) off the
    dead-code list, which the dogfood gate depends on.
    """
    reasons: dict[str, str] = {}
    for entry in PUBLIC_SURFACE.mcp_tools:
        if entry.registered:
            _ = reasons.setdefault(entry.name, _REASON_MCP_TOOL)
    for entry in PUBLIC_SURFACE.cli_commands:
        if entry.registered:
            _ = reasons.setdefault(entry.name, _REASON_CLI_COMMAND)
    return reasons


def build_entry_point_registry(
    root: Path | str,
    *,
    config: ProjectConfig | None = None,
) -> EntryPointRegistry:
    repo_root = resolve_repo_root(root)
    project_config = config or ProjectConfig()
    reasons = registered_surface_reasons()

    python_items = sorted(
        (
            item
            for item in build_file_inventory(repo_root, config=project_config)
            if item.language == "python"
        ),
        key=lambda item: item.path,
    )
    for item in python_items:
        source = read_source_text(repo_root / item.path)
        if source.text is None:
            continue
        try:
            tree = ast.parse(source.text, filename=item.path)
        except SyntaxError:
            continue
        _collect_module_entry_points(tree, reasons)

    return EntryPointRegistry(reasons=dict(sorted(reasons.items())))


def _collect_module_entry_points(tree: ast.Module, reasons: dict[str, str]) -> None:
    for node in ast.walk(tree):
        match node:
            case ast.Assign(targets=targets, value=value):
                if any(_is_all_target(target) for target in targets):
                    _record_all_exports(value, reasons)
            case ast.AnnAssign(target=target, value=value) if value is not None:
                if _is_all_target(target):
                    _record_all_exports(value, reasons)
            case ast.FunctionDef() | ast.AsyncFunctionDef() | ast.ClassDef():
                attr = _registration_decorator(node.decorator_list)
                if attr is not None:
                    _ = reasons.setdefault(node.name, _decorator_reason(attr))
            case ast.Call():
                _collect_call_entry_points(node, reasons)
            case _:
                continue


def _record_all_exports(value: ast.expr, reasons: dict[str, str]) -> None:
    for name in sorted(_string_constants(value)):
        _ = reasons.setdefault(name, _REASON_ALL_EXPORT)


def _collect_call_entry_points(node: ast.Call, reasons: dict[str, str]) -> None:
    func = node.func
    # getattr(obj, "name", ...) — a dynamic-dispatch indicator: the named symbol
    # may be invoked by string lookup, so it cannot be assumed dead.
    if (
        isinstance(func, ast.Name)
        and func.id == "getattr"
        and len(node.args) >= _GETATTR_MIN_ARGS
    ):
        target = node.args[1]
        if isinstance(target, ast.Constant) and isinstance(target.value, str):
            _ = reasons.setdefault(target.value, _REASON_DYNAMIC_DISPATCH)
        return
    # Call-form registration: `mcp.tool(...)(fn)` / `app.command(...)(fn)`.
    if isinstance(func, ast.Call) and isinstance(func.func, ast.Attribute):
        attr = func.func.attr
        if attr in _REGISTRATION_ATTRS:
            for arg in node.args:
                if isinstance(arg, ast.Name):
                    _ = reasons.setdefault(arg.id, _call_reason(attr))


def _registration_decorator(decorators: list[ast.expr]) -> str | None:
    for decorator in decorators:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Attribute) and target.attr in _REGISTRATION_ATTRS:
            return target.attr
    return None


def _decorator_reason(attr: str) -> str:
    return f"registered via @<obj>.{attr}() decorator"


def _call_reason(attr: str) -> str:
    return f"registered via <obj>.{attr}(...)(<symbol>) call"


def _is_all_target(target: ast.expr) -> bool:
    return isinstance(target, ast.Name) and target.id == "__all__"


def _string_constants(node: ast.expr) -> set[str]:
    match node:
        case ast.List(elts=elts) | ast.Tuple(elts=elts) | ast.Set(elts=elts):
            return {
                element.value
                for element in elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            }
        case _:
            return set()
