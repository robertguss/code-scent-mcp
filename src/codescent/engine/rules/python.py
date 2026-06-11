from __future__ import annotations

import ast
from collections import Counter
from typing import TYPE_CHECKING, Final

from codescent.core.paths import resolve_repo_root
from codescent.engine.rules.model import (
    CodeHealthFinding,
    FindingSpec,
    build_finding,
)
from codescent.engine.rules.python_patterns import secondary_findings
from codescent.services.symbols import SymbolService

if TYPE_CHECKING:
    from pathlib import Path

    from codescent.engine.parsers.python import ParsedPythonFile

LARGE_FILE_LINES: Final = 70
LARGE_FUNCTION_LINES: Final = 25
LARGE_CLASS_LINES: Final = 60
TODO_CLUSTER_SIZE: Final = 3
DUPLICATE_LITERAL_COUNT: Final = 3
MIN_LITERAL_LENGTH: Final = 3


def scan_python_health(root: Path | str) -> tuple[CodeHealthFinding, ...]:
    repo_root = resolve_repo_root(root)
    findings: list[CodeHealthFinding] = []
    for parsed in SymbolService(repo_root).extract().files:
        source_path = repo_root / parsed.path
        lines = source_path.read_text().splitlines()
        findings.extend(_large_file(parsed, len(lines)))
        findings.extend(_symbol_size_findings(parsed))
        findings.extend(_todo_cluster(parsed, lines))
        findings.extend(_duplicate_literals(parsed, source_path))
        findings.extend(secondary_findings(parsed, source_path, lines))
    return tuple(findings)


def _large_file(
    parsed: ParsedPythonFile,
    line_count: int,
) -> tuple[CodeHealthFinding, ...]:
    if line_count < LARGE_FILE_LINES:
        return ()
    return (
        build_finding(
            FindingSpec(
                rule_id="python.large_file",
                title="Large Python file",
                message=f"{parsed.path} has {line_count} lines.",
                file_path=parsed.path,
                symbol=None,
                severity="warning",
                confidence=0.9,
                evidence={"line_count": line_count, "threshold": LARGE_FILE_LINES},
                suggested_action=(
                    "Split cohesive responsibilities into smaller modules."
                ),
            ),
        ),
    )


def _symbol_size_findings(parsed: ParsedPythonFile) -> tuple[CodeHealthFinding, ...]:
    findings: list[CodeHealthFinding] = []
    for symbol in parsed.symbols:
        span = symbol.end_line - symbol.start_line + 1
        if symbol.kind == "class" and span >= LARGE_CLASS_LINES:
            findings.append(
                build_finding(
                    FindingSpec(
                        rule_id="python.large_class",
                        title="Large Python class",
                        message=f"{symbol.qualified_name} spans {span} lines.",
                        file_path=parsed.path,
                        symbol=symbol.qualified_name,
                        severity="warning",
                        confidence=0.85,
                        evidence={
                            "line_count": span,
                            "threshold": LARGE_CLASS_LINES,
                        },
                        suggested_action="Extract smaller classes or collaborators.",
                    ),
                ),
            )
        if symbol.kind in {"function", "async_function", "method"}:
            findings.extend(_large_function(parsed, symbol.qualified_name, span))
    return tuple(findings)


def _large_function(
    parsed: ParsedPythonFile,
    qualified_name: str,
    span: int,
) -> tuple[CodeHealthFinding, ...]:
    if span < LARGE_FUNCTION_LINES:
        return ()
    return (
        build_finding(
            FindingSpec(
                rule_id="python.large_function",
                title="Large Python function",
                message=f"{qualified_name} spans {span} lines.",
                file_path=parsed.path,
                symbol=qualified_name,
                severity="warning",
                confidence=0.9,
                evidence={"line_count": span, "threshold": LARGE_FUNCTION_LINES},
                suggested_action="Extract named steps while preserving behavior.",
            ),
        ),
    )


def _todo_cluster(
    parsed: ParsedPythonFile,
    lines: list[str],
) -> tuple[CodeHealthFinding, ...]:
    count = sum(1 for line in lines if _todo_marker(line))
    if count < TODO_CLUSTER_SIZE:
        return ()
    return (
        build_finding(
            FindingSpec(
                rule_id="python.todo_cluster",
                title="TODO/FIXME/HACK cluster",
                message=f"{parsed.path} contains {count} TODO-like markers.",
                file_path=parsed.path,
                symbol=None,
                severity="info",
                confidence=0.9,
                evidence={"count": count, "threshold": TODO_CLUSTER_SIZE},
                suggested_action="Resolve or split the TODO cluster into tracked work.",
            ),
        ),
    )


def _duplicate_literals(
    parsed: ParsedPythonFile,
    source_path: Path,
) -> tuple[CodeHealthFinding, ...]:
    try:
        tree = ast.parse(source_path.read_text(), filename=parsed.path)
    except SyntaxError:
        return ()
    literals = Counter(
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and len(node.value) > MIN_LITERAL_LENGTH
    )
    return tuple(
        build_finding(
            FindingSpec(
                rule_id="python.duplicate_literal",
                title="Duplicate literal string",
                message=f"{parsed.path} repeats a literal {count} times.",
                file_path=parsed.path,
                symbol=None,
                severity="info",
                confidence=0.85,
                evidence={"literal": literal, "count": count},
                suggested_action="Name the repeated literal once and reuse it.",
            ),
        )
        for literal, count in literals.items()
        if count >= DUPLICATE_LITERAL_COUNT
    )


def _todo_marker(line: str) -> bool:
    folded = line.upper()
    return "TODO" in folded or "FIXME" in folded or "HACK" in folded
