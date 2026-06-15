from __future__ import annotations

from typing import TYPE_CHECKING, Final

from codescent.core.models import ProjectConfig
from codescent.core.paths import resolve_repo_root
from codescent.engine.inventory import build_file_inventory
from codescent.engine.packs_ts import parse_typescript_file
from codescent.engine.rules.model import CodeHealthFinding, FindingSpec, build_finding
from codescent.engine.rules.ts_react_next_patterns import secondary_findings
from codescent.engine.source_read import read_source_lines

if TYPE_CHECKING:
    from pathlib import Path

    from codescent.engine.parsers.python import ParsedPythonFile, ParsedSymbol

LARGE_COMPONENT_LINES: Final = 12
TOO_MANY_HOOKS: Final = 1
TOO_MANY_PROPS: Final = 3
TOO_MANY_EXPORTS: Final = 3
ROUTE_HANDLER_LINES: Final = 3


def scan_ts_react_next_health(
    root: Path | str,
    *,
    config: ProjectConfig | None = None,
) -> tuple[CodeHealthFinding, ...]:
    repo_root = resolve_repo_root(root)
    project_config = config or ProjectConfig()
    findings: list[CodeHealthFinding] = []
    inventory = build_file_inventory(repo_root, config=project_config)
    indexed_paths = {item.path for item in inventory}
    for item in inventory:
        if item.language not in {"javascript", "typescript"}:
            continue
        parsed = parse_typescript_file(repo_root / item.path, item.path)
        source = read_source_lines(repo_root / item.path)
        if source.lines is None:
            continue
        lines = list(source.lines)
        findings.extend(_large_components(parsed))
        findings.extend(_too_many_hooks(parsed, lines))
        findings.extend(_too_many_props(parsed, lines))
        findings.extend(_too_many_exports(parsed, lines))
        findings.extend(_route_handler_too_much(parsed))
        findings.extend(secondary_findings(parsed, lines, indexed_paths))
    return tuple(findings)


def _large_components(parsed: ParsedPythonFile) -> tuple[CodeHealthFinding, ...]:
    return tuple(
        build_finding(
            FindingSpec(
                rule_id="typescript.large_component",
                title="Large React component",
                message=f"{symbol.qualified_name} spans {span} lines.",
                file_path=parsed.path,
                symbol=symbol.qualified_name,
                severity="warning",
                confidence=0.8,
                evidence={"line_count": span, "threshold": LARGE_COMPONENT_LINES},
                suggested_action="Extract smaller presentational components or hooks.",
            ),
        )
        for symbol in parsed.symbols
        if symbol.kind == "component"
        for span in (_symbol_span(symbol),)
        if span >= LARGE_COMPONENT_LINES
    )


def _too_many_hooks(
    parsed: ParsedPythonFile,
    lines: list[str],
) -> tuple[CodeHealthFinding, ...]:
    hook_count = sum(_hook_call_count(line) for line in lines)
    if hook_count <= TOO_MANY_HOOKS:
        return ()
    hook_symbol = _first_symbol(parsed, "hook")
    return (
        build_finding(
            FindingSpec(
                rule_id="react.too_many_hooks",
                title="Too many hooks in one unit",
                message=f"{parsed.path} uses {hook_count} hook-like calls.",
                file_path=parsed.path,
                symbol=hook_symbol.qualified_name if hook_symbol is not None else None,
                severity="info",
                confidence=0.7,
                evidence={"hook_count": hook_count, "threshold": TOO_MANY_HOOKS},
                suggested_action="Split independent state/effects into smaller hooks.",
            ),
        ),
    )


def _too_many_props(
    parsed: ParsedPythonFile,
    lines: list[str],
) -> tuple[CodeHealthFinding, ...]:
    prop_count = _type_field_count(lines, "Props")
    if prop_count <= TOO_MANY_PROPS:
        return ()
    return (
        build_finding(
            FindingSpec(
                rule_id="react.too_many_props",
                title="Component has many props",
                message=f"{parsed.path} defines {prop_count} props.",
                file_path=parsed.path,
                symbol=_first_symbol_name(parsed, "component"),
                severity="info",
                confidence=0.65,
                evidence={"prop_count": prop_count, "threshold": TOO_MANY_PROPS},
                suggested_action="Group related props into named view models.",
            ),
        ),
    )


def _too_many_exports(
    parsed: ParsedPythonFile,
    lines: list[str],
) -> tuple[CodeHealthFinding, ...]:
    export_count = sum(1 for line in lines if line.lstrip().startswith("export "))
    if export_count <= TOO_MANY_EXPORTS:
        return ()
    return (
        build_finding(
            FindingSpec(
                rule_id="typescript.too_many_exports",
                title="Too many exports",
                message=f"{parsed.path} exports {export_count} symbols.",
                file_path=parsed.path,
                symbol=None,
                severity="info",
                confidence=0.65,
                evidence={"export_count": export_count, "threshold": TOO_MANY_EXPORTS},
                suggested_action="Split unrelated exports into focused modules.",
            ),
        ),
    )


def _route_handler_too_much(
    parsed: ParsedPythonFile,
) -> tuple[CodeHealthFinding, ...]:
    return tuple(
        build_finding(
            FindingSpec(
                rule_id="next.route_handler_too_much",
                title="Route handler doing too much",
                message=f"{symbol.qualified_name} spans {span} lines.",
                file_path=parsed.path,
                symbol=symbol.qualified_name,
                severity="warning",
                confidence=0.75,
                evidence={"line_count": span, "threshold": ROUTE_HANDLER_LINES},
                suggested_action=(
                    "Move route work into a service and keep the handler thin."
                ),
            ),
        )
        for symbol in parsed.symbols
        if symbol.kind == "route"
        for span in (_symbol_span(symbol),)
        if span >= ROUTE_HANDLER_LINES
    )


def _symbol_span(symbol: ParsedSymbol) -> int:
    return symbol.end_line - symbol.start_line + 1


def _first_symbol(parsed: ParsedPythonFile, kind: str) -> ParsedSymbol | None:
    return next((symbol for symbol in parsed.symbols if symbol.kind == kind), None)


def _first_symbol_name(parsed: ParsedPythonFile, kind: str) -> str | None:
    symbol = _first_symbol(parsed, kind)
    if symbol is None:
        return None
    return symbol.qualified_name


def _type_field_count(lines: list[str], suffix: str) -> int:
    inside = False
    count = 0
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("type ") and stripped.endswith(f"{suffix} = {{"):
            inside = True
            continue
        if inside and stripped == "};":
            return count
        if inside and stripped.startswith("readonly "):
            count += 1
    return count


def _hook_call_count(line: str) -> int:
    if line.strip().startswith("import "):
        return 0
    hook_names = ("useEffect", "useMemo", "useReducer", "useState")
    return sum(line.count(name) for name in hook_names)
