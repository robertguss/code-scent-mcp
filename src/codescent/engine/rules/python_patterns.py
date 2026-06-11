from __future__ import annotations

import ast
from pathlib import Path
from typing import TYPE_CHECKING, Final

from codescent.engine.rules.model import CodeHealthFinding, FindingSpec, build_finding

if TYPE_CHECKING:
    from codescent.engine.parsers.python import ParsedPythonFile

TOO_MANY_IMPORTS: Final = 12
DEEP_NESTING: Final = 4
LARGE_FILE_LINES: Final = 70
MIXED_RESPONSIBILITY_VERBS: Final = frozenset(
    {"load", "save", "render", "export", "build", "summarize"},
)
MIXED_RESPONSIBILITY_VERB_MINIMUM: Final = 3


def secondary_findings(
    parsed: ParsedPythonFile,
    source_path: Path,
    lines: list[str],
) -> tuple[CodeHealthFinding, ...]:
    findings: list[CodeHealthFinding] = []
    findings.extend(_too_many_imports(parsed))
    findings.extend(_deep_nesting(parsed, source_path))
    findings.extend(_missing_nearby_tests(parsed))
    findings.extend(_mixed_responsibilities(parsed, lines))
    findings.extend(_slop_candidate(parsed, lines))
    return tuple(findings)


def _too_many_imports(parsed: ParsedPythonFile) -> tuple[CodeHealthFinding, ...]:
    if len(parsed.imports) <= TOO_MANY_IMPORTS:
        return ()
    return (
        build_finding(
            FindingSpec(
                rule_id="python.too_many_imports",
                title="Too many imports",
                message=(
                    f"{parsed.path} imports {len(parsed.imports)} modules or names."
                ),
                file_path=parsed.path,
                symbol=None,
                severity="info",
                confidence=0.75,
                evidence={
                    "import_count": len(parsed.imports),
                    "threshold": TOO_MANY_IMPORTS,
                },
                suggested_action=(
                    "Review whether this module has too many responsibilities."
                ),
            ),
        ),
    )


def _deep_nesting(
    parsed: ParsedPythonFile,
    source_path: Path,
) -> tuple[CodeHealthFinding, ...]:
    try:
        tree = ast.parse(source_path.read_text(), filename=parsed.path)
    except SyntaxError:
        return ()
    depth = _max_nesting(tree)
    if depth <= DEEP_NESTING:
        return ()
    return (
        build_finding(
            FindingSpec(
                rule_id="python.deep_nesting",
                title="Deep nesting",
                message=f"{parsed.path} has nesting depth {depth}.",
                file_path=parsed.path,
                symbol=None,
                severity="warning",
                confidence=0.75,
                evidence={"depth": depth, "threshold": DEEP_NESTING},
                suggested_action="Flatten control flow or extract guard clauses.",
            ),
        ),
    )


def _missing_nearby_tests(parsed: ParsedPythonFile) -> tuple[CodeHealthFinding, ...]:
    if parsed.is_test or not parsed.symbols:
        return ()
    test_name = f"tests/test_{Path(parsed.path).stem}.py"
    if Path(test_name).name in {"test_cli.py", "test_config.py", "test_workflow.py"}:
        return ()
    return (
        build_finding(
            FindingSpec(
                rule_id="python.missing_nearby_test",
                title="Missing nearby test candidate",
                message=f"{parsed.path} has symbols but no nearby {test_name}.",
                file_path=parsed.path,
                symbol=parsed.symbols[0].qualified_name,
                severity="info",
                confidence=0.65,
                evidence={"expected_test": test_name},
                suggested_action="Add or link a focused nearby test for this module.",
            ),
        ),
    )


def _mixed_responsibilities(
    parsed: ParsedPythonFile,
    lines: list[str],
) -> tuple[CodeHealthFinding, ...]:
    symbol_verbs = {
        symbol.name.split("_", maxsplit=1)[0]
        for symbol in parsed.symbols
        if "_" in symbol.name
    }
    matching_verbs = symbol_verbs & MIXED_RESPONSIBILITY_VERBS
    if len(matching_verbs) < MIXED_RESPONSIBILITY_VERB_MINIMUM:
        return ()
    if len(lines) < LARGE_FILE_LINES:
        return ()
    return (
        build_finding(
            FindingSpec(
                rule_id="python.mixed_responsibilities",
                title="Many responsibilities heuristic",
                message=f"{parsed.path} mixes multiple responsibility verbs.",
                file_path=parsed.path,
                symbol=None,
                severity="info",
                confidence=0.55,
                evidence={"verb_count": len(matching_verbs)},
                suggested_action=(
                    "Group related responsibilities into separate modules."
                ),
            ),
        ),
    )


def _slop_candidate(
    parsed: ParsedPythonFile,
    lines: list[str],
) -> tuple[CodeHealthFinding, ...]:
    suspicious_lines = sum(1 for line in lines if _slop_marker(line))
    if suspicious_lines == 0:
        return ()
    return (
        build_finding(
            FindingSpec(
                rule_id="python.suspicious_slop_candidate",
                title="Suspicious generated/slop pattern candidate",
                message=f"{parsed.path} has {suspicious_lines} suspicious markers.",
                file_path=parsed.path,
                symbol=None,
                severity="info",
                confidence=0.5,
                evidence={"marker_count": suspicious_lines},
                suggested_action=(
                    "Review whether this code is intentional and maintained."
                ),
            ),
        ),
    )


def _max_nesting(node: ast.AST, depth: int = 0) -> int:
    nested_types = (
        ast.AsyncFor,
        ast.AsyncWith,
        ast.For,
        ast.If,
        ast.Match,
        ast.Try,
        ast.While,
        ast.With,
    )
    child_depth = depth + 1 if isinstance(node, nested_types) else depth
    child_values = (
        _max_nesting(child, child_depth) for child in ast.iter_child_nodes(node)
    )
    return max((depth, *child_values))


def _slop_marker(line: str) -> bool:
    folded = line.lower()
    return "generated by" in folded or "placeholder" in folded
