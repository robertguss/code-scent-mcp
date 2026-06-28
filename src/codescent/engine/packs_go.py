from __future__ import annotations

import re
from collections import Counter
from dataclasses import replace
from typing import TYPE_CHECKING, Final

from codescent.core.models import ProjectConfig
from codescent.core.paths import resolve_repo_root
from codescent.engine.inventory import DEFAULT_EXCLUDED_NAMES
from codescent.engine.parsers.go import GO_EXTENSIONS, parse_go_file
from codescent.engine.rules.model import (
    CONFIDENCE_TIER_HEURISTIC,
    CodeHealthFinding,
    FindingSpec,
    build_finding,
)
from codescent.engine.source_read import read_source_text

if TYPE_CHECKING:
    from pathlib import Path

    from codescent.core.models import MaintainabilityThresholds
    from codescent.engine.parsers.python import ParsedPythonFile

# Re-exported so packs.py imports the parser + extensions from one Go module,
# mirroring how packs.py imports TS_EXTENSIONS/parse_typescript_file from packs_ts.
__all__ = ["GO_EXTENSIONS", "parse_go_file", "scan_go_health"]

_FUNCTION_KINDS: Final = frozenset({"function", "method"})
_STRING_LITERAL_RE: Final[re.Pattern[str]] = re.compile(r'"((?:[^"\\]|\\.)*)"')


def scan_go_health(
    root: Path | str,
    *,
    config: ProjectConfig | None = None,
) -> tuple[CodeHealthFinding, ...]:
    repo_root = resolve_repo_root(root)
    project_config = config or ProjectConfig()
    thresholds = project_config.thresholds
    go_paths = _go_files(repo_root, project_config)
    go_path_set = frozenset(go_paths)
    findings: list[CodeHealthFinding] = []
    for relative in go_paths:
        source = read_source_text(repo_root / relative)
        if source.text is None:
            continue
        parsed = parse_go_file(repo_root / relative, relative)
        findings.extend(_large_file(parsed, len(source.text.splitlines()), thresholds))
        findings.extend(_large_functions(parsed, thresholds))
        findings.extend(_missing_nearby_test(parsed, relative, go_path_set))
        findings.extend(_duplicate_literals(parsed, source.text, thresholds))
    return tuple(findings)


def _go_files(repo_root: Path, config: ProjectConfig) -> tuple[str, ...]:
    # The shared inventory only maps known suffixes (no `.go`), and the suffix
    # map belongs to the generic-fallback unit, so the Go pack walks `.go` files
    # itself while honoring the same default and config-driven exclusions.
    patterns = tuple(
        cleaned
        for pattern in (
            *config.exclude,
            *config.generated,
            *config.vendor,
            *config.build,
        )
        for cleaned in (pattern.strip().strip("/"),)
        if cleaned
    )
    paths: list[str] = []
    for path in sorted(repo_root.rglob("*.go")):
        if not path.is_file():
            continue
        relative = path.relative_to(repo_root)
        if any(part in DEFAULT_EXCLUDED_NAMES for part in relative.parts):
            continue
        rel_posix = relative.as_posix()
        if any(rel_posix == p or rel_posix.startswith(f"{p}/") for p in patterns):
            continue
        paths.append(rel_posix)
    return tuple(paths)


def _large_file(
    parsed: ParsedPythonFile,
    line_count: int,
    thresholds: MaintainabilityThresholds,
) -> tuple[CodeHealthFinding, ...]:
    if line_count < thresholds.large_file_lines:
        return ()
    return (
        _go_finding(
            FindingSpec(
                rule_id="go.large_file",
                title="Large Go file",
                message=f"{parsed.path} has {line_count} lines.",
                file_path=parsed.path,
                symbol=None,
                severity="warning",
                confidence=0.9,
                evidence={
                    "line_count": line_count,
                    "threshold": thresholds.large_file_lines,
                },
                suggested_action="Split cohesive responsibilities into smaller files.",
            ),
        ),
    )


def _large_functions(
    parsed: ParsedPythonFile,
    thresholds: MaintainabilityThresholds,
) -> tuple[CodeHealthFinding, ...]:
    return tuple(
        _go_finding(
            FindingSpec(
                rule_id="go.large_function",
                title="Large Go function",
                message=f"{symbol.qualified_name} spans {span} lines.",
                file_path=parsed.path,
                symbol=symbol.qualified_name,
                severity="warning",
                confidence=0.9,
                evidence={
                    "line_count": span,
                    "threshold": thresholds.large_function_lines,
                },
                suggested_action="Extract named steps while preserving behavior.",
            ),
        )
        for symbol in parsed.symbols
        if symbol.kind in _FUNCTION_KINDS
        for span in (symbol.end_line - symbol.start_line + 1,)
        if span >= thresholds.large_function_lines
    )


def _missing_nearby_test(
    parsed: ParsedPythonFile,
    relative: str,
    go_paths: frozenset[str],
) -> tuple[CodeHealthFinding, ...]:
    if relative.endswith("_test.go"):
        return ()
    exported = tuple(
        symbol
        for symbol in parsed.symbols
        if symbol.kind in _FUNCTION_KINDS and symbol.name[:1].isupper()
    )
    if not exported:
        return ()
    directory = _directory(relative)
    if any(p.endswith("_test.go") and _directory(p) == directory for p in go_paths):
        return ()
    return (
        _go_finding(
            FindingSpec(
                rule_id="go.missing_nearby_test",
                title="Go file without a nearby test",
                message=(
                    f"{relative} exports functions but no _test.go covers its package."
                ),
                file_path=parsed.path,
                symbol=exported[0].qualified_name,
                severity="warning",
                confidence=0.6,
                evidence={"exported_count": len(exported)},
                suggested_action="Add a _test.go covering the exported functions.",
            ),
        ),
    )


def _duplicate_literals(
    parsed: ParsedPythonFile,
    source_text: str,
    thresholds: MaintainabilityThresholds,
) -> tuple[CodeHealthFinding, ...]:
    literals = Counter(
        match.group(1)
        for match in _STRING_LITERAL_RE.finditer(source_text)
        if len(match.group(1)) >= thresholds.duplicate_literal_min_length
    )
    return tuple(
        _go_finding(
            FindingSpec(
                rule_id="go.duplicate_literal",
                title="Duplicate literal string",
                message=f"{parsed.path} repeats a literal {count} times.",
                file_path=parsed.path,
                symbol=None,
                severity="info",
                confidence=0.8,
                evidence={"literal": literal, "count": count},
                suggested_action="Name the repeated literal once and reuse it.",
            ),
        )
        for literal, count in literals.items()
        if count >= thresholds.duplicate_literal_min_count
    )


def _go_finding(spec: FindingSpec) -> CodeHealthFinding:
    # Go findings are regex-derived (heuristic). Set provenance explicitly so the
    # finding is tagged language "go" instead of the default-derived "typescript"
    # (the model's language derivation is off-limits to this unit).
    return build_finding(
        replace(
            spec,
            confidence_tier=CONFIDENCE_TIER_HEURISTIC,
            provenance={
                "rule_id": spec.rule_id,
                "language": "go",
                "resolution": "regex",
                "symbol_resolved": spec.symbol is not None,
            },
        ),
    )


def _directory(relative_path: str) -> str:
    return relative_path.rsplit("/", maxsplit=1)[0] if "/" in relative_path else ""
