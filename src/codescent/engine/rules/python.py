from __future__ import annotations

import ast
from collections import Counter
from typing import TYPE_CHECKING

from codescent.core.models import MaintainabilityThresholds, ProjectConfig
from codescent.core.paths import resolve_repo_root
from codescent.engine.inventory import build_file_inventory
from codescent.engine.parsers.python import parse_python_file
from codescent.engine.rules.dead_code import scan_dead_code
from codescent.engine.rules.model import (
    CodeHealthFinding,
    FindingSpec,
    build_finding,
)
from codescent.engine.rules.python_patterns import secondary_findings
from codescent.engine.rules.relative_size import SizeSample, relative_outlier_findings
from codescent.engine.rules.structural_duplicates import structural_duplicate_findings
from codescent.engine.source_read import read_source_text

if TYPE_CHECKING:
    from pathlib import Path

    from codescent.engine.parsers.python import ParsedPythonFile

_FUNCTION_KINDS = frozenset({"function", "async_function", "method"})


def scan_python_health(
    root: Path | str,
    *,
    config: ProjectConfig | None = None,
) -> tuple[CodeHealthFinding, ...]:
    repo_root = resolve_repo_root(root)
    project_config = config or ProjectConfig()
    thresholds = project_config.thresholds
    findings: list[CodeHealthFinding] = []
    file_samples: list[SizeSample] = []
    function_samples: list[SizeSample] = []
    class_samples: list[SizeSample] = []
    for item in build_file_inventory(repo_root, config=project_config):
        if item.language != "python":
            continue
        parsed = parse_python_file(repo_root / item.path, item.path)
        source_path = repo_root / parsed.path
        source = read_source_text(source_path)
        if source.text is None:
            continue
        lines = source.text.splitlines()
        findings.extend(_large_file(parsed, len(lines), thresholds))
        findings.extend(_symbol_size_findings(parsed, thresholds))
        findings.extend(_todo_cluster(parsed, lines, thresholds))
        findings.extend(_duplicate_literals(parsed, source.text, thresholds))
        findings.extend(secondary_findings(parsed, source.text, lines, thresholds))
        _collect_size_samples(
            parsed,
            len(lines),
            file_samples=file_samples,
            function_samples=function_samples,
            class_samples=class_samples,
        )
    findings.extend(structural_duplicate_findings(repo_root, config=project_config))
    findings.extend(scan_dead_code(repo_root, config=project_config))
    findings.extend(
        relative_outlier_findings(
            file_samples=file_samples,
            function_samples=function_samples,
            class_samples=class_samples,
            thresholds=thresholds,
        ),
    )
    return tuple(findings)


def _collect_size_samples(
    parsed: ParsedPythonFile,
    line_count: int,
    *,
    file_samples: list[SizeSample],
    function_samples: list[SizeSample],
    class_samples: list[SizeSample],
) -> None:
    file_samples.append(SizeSample(parsed.path, None, line_count))
    for symbol in parsed.symbols:
        span = symbol.end_line - symbol.start_line + 1
        if symbol.kind == "class":
            class_samples.append(SizeSample(parsed.path, symbol.qualified_name, span))
        elif symbol.kind in _FUNCTION_KINDS:
            function_samples.append(
                SizeSample(parsed.path, symbol.qualified_name, span),
            )


def _large_file(
    parsed: ParsedPythonFile,
    line_count: int,
    thresholds: MaintainabilityThresholds,
) -> tuple[CodeHealthFinding, ...]:
    if line_count < thresholds.large_file_lines:
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
                evidence={
                    "line_count": line_count,
                    "threshold": thresholds.large_file_lines,
                },
                suggested_action=(
                    "Split cohesive responsibilities into smaller modules."
                ),
            ),
        ),
    )


def _symbol_size_findings(
    parsed: ParsedPythonFile,
    thresholds: MaintainabilityThresholds,
) -> tuple[CodeHealthFinding, ...]:
    findings: list[CodeHealthFinding] = []
    for symbol in parsed.symbols:
        span = symbol.end_line - symbol.start_line + 1
        if symbol.kind == "class" and span >= thresholds.large_class_lines:
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
                            "threshold": thresholds.large_class_lines,
                        },
                        suggested_action="Extract smaller classes or collaborators.",
                    ),
                ),
            )
        if symbol.kind in {"function", "async_function", "method"}:
            findings.extend(
                _large_function(parsed, symbol.qualified_name, span, thresholds),
            )
    return tuple(findings)


def _large_function(
    parsed: ParsedPythonFile,
    qualified_name: str,
    span: int,
    thresholds: MaintainabilityThresholds,
) -> tuple[CodeHealthFinding, ...]:
    if span < thresholds.large_function_lines:
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
                evidence={
                    "line_count": span,
                    "threshold": thresholds.large_function_lines,
                },
                suggested_action="Extract named steps while preserving behavior.",
            ),
        ),
    )


def _todo_cluster(
    parsed: ParsedPythonFile,
    lines: list[str],
    thresholds: MaintainabilityThresholds,
) -> tuple[CodeHealthFinding, ...]:
    count = sum(1 for line in lines if _todo_marker(line))
    if count < thresholds.todo_cluster_size:
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
                evidence={"count": count, "threshold": thresholds.todo_cluster_size},
                suggested_action="Resolve or split the TODO cluster into tracked work.",
            ),
        ),
    )


def _duplicate_literals(
    parsed: ParsedPythonFile,
    source_text: str,
    thresholds: MaintainabilityThresholds,
) -> tuple[CodeHealthFinding, ...]:
    try:
        tree = ast.parse(source_text, filename=parsed.path)
    except SyntaxError:
        return ()
    literals = Counter(
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and len(node.value) >= thresholds.duplicate_literal_min_length
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
        if count >= thresholds.duplicate_literal_min_count
    )


def _todo_marker(line: str) -> bool:
    folded = line.upper()
    return "TODO" in folded or "FIXME" in folded or "HACK" in folded
