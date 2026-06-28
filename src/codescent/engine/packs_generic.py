from __future__ import annotations

import re
from collections import Counter
from dataclasses import replace
from typing import TYPE_CHECKING, Final

from codescent.core.models import ProjectConfig
from codescent.core.paths import resolve_repo_root
from codescent.engine.inventory import (
    DEFAULT_EXCLUDED_FILENAMES,
    DEFAULT_EXCLUDED_NAMES,
    MINIFIED_SUFFIXES,
)
from codescent.engine.packs_ts import TS_EXTENSIONS
from codescent.engine.parsers.go import GO_EXTENSIONS
from codescent.engine.rules.model import (
    CONFIDENCE_TIER_HEURISTIC,
    CodeHealthFinding,
    FindingSpec,
    build_finding,
)
from codescent.engine.source_read import read_source_bytes

if TYPE_CHECKING:
    from pathlib import Path

    from codescent.core.models import MaintainabilityThresholds

__all__ = ["scan_generic_health"]

# Suffixes owned by the *specific* language packs (python / typescript / go).
# The generic fallback never touches these, so a specific pack always wins for
# its own files. The set is derived from the specific packs themselves (not a
# hand-kept list) so the precedence boundary stays correct as packs change. It
# is fixed by suffix, not by which packs are *enabled*: disabling the Python pack
# must not make the fallback start emitting bogus heuristics for `.py` files.
_PYTHON_SUFFIXES: Final = (".py", ".pyi")
_RESERVED_SUFFIXES: Final = frozenset(
    suffix.lower() for suffix in (*_PYTHON_SUFFIXES, *TS_EXTENSIONS, *GO_EXTENSIONS)
)
_TODO_MARKERS: Final = ("TODO", "FIXME", "HACK")
# A quoted string in either quote style, escape-aware. Text-only: this is a
# regex over raw source, not a parse, so it claims nothing about structure.
_STRING_LITERAL_RE: Final[re.Pattern[str]] = re.compile(
    r"""(?P<quote>["'])(?P<body>(?:\\.|(?!(?P=quote)).)*)(?P=quote)""",
)


def scan_generic_health(
    root: Path | str,
    *,
    config: ProjectConfig | None = None,
) -> tuple[CodeHealthFinding, ...]:
    """Text-only fallback findings for files no specific pack owns.

    Line/text heuristics only: large-file, TODO cluster, duplicate literal. No
    parsing, no symbol/reference/structural output -- the fallback degrades
    honestly and never makes a claim it cannot prove from raw text.
    """
    repo_root = resolve_repo_root(root)
    project_config = config or ProjectConfig()
    thresholds = project_config.thresholds
    findings: list[CodeHealthFinding] = []
    for relative in _generic_files(repo_root, project_config):
        source = read_source_bytes(repo_root / relative)
        content = source.content
        if content is None or b"\x00" in content:
            # Oversized (bounded read) or binary -- skip, do not guess.
            continue
        text = content.decode("utf-8", errors="replace")
        lines = text.splitlines()
        findings.extend(_large_file(relative, len(lines), thresholds))
        findings.extend(_todo_cluster(relative, lines, thresholds))
        findings.extend(_duplicate_literals(relative, text, thresholds))
    return tuple(findings)


def _generic_files(repo_root: Path, config: ProjectConfig) -> tuple[str, ...]:
    config_patterns = tuple(
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
    for path in sorted(repo_root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(repo_root)
        if any(part in DEFAULT_EXCLUDED_NAMES for part in relative.parts):
            continue
        if path.name in DEFAULT_EXCLUDED_FILENAMES:
            continue
        if path.name.endswith(MINIFIED_SUFFIXES):
            continue
        if path.suffix.lower() in _RESERVED_SUFFIXES:
            # A specific pack owns this suffix -- it always wins.
            continue
        rel_posix = relative.as_posix()
        if any(
            rel_posix == p or rel_posix.startswith(f"{p}/") for p in config_patterns
        ):
            continue
        paths.append(rel_posix)
    return tuple(paths)


def _large_file(
    relative: str,
    line_count: int,
    thresholds: MaintainabilityThresholds,
) -> tuple[CodeHealthFinding, ...]:
    if line_count < thresholds.large_file_lines:
        return ()
    return (
        _generic_finding(
            FindingSpec(
                rule_id="generic.large_file",
                title="Large file",
                message=f"{relative} has {line_count} lines.",
                file_path=relative,
                symbol=None,
                severity="warning",
                confidence=0.8,
                evidence={
                    "line_count": line_count,
                    "threshold": thresholds.large_file_lines,
                },
                suggested_action="Split cohesive responsibilities into smaller files.",
            ),
        ),
    )


def _todo_cluster(
    relative: str,
    lines: list[str],
    thresholds: MaintainabilityThresholds,
) -> tuple[CodeHealthFinding, ...]:
    count = sum(1 for line in lines if _todo_marker(line))
    if count < thresholds.todo_cluster_size:
        return ()
    return (
        _generic_finding(
            FindingSpec(
                rule_id="generic.todo_cluster",
                title="TODO/FIXME/HACK cluster",
                message=f"{relative} contains {count} TODO-like markers.",
                file_path=relative,
                symbol=None,
                severity="info",
                confidence=0.8,
                evidence={"count": count, "threshold": thresholds.todo_cluster_size},
                suggested_action="Resolve or split the TODO cluster into tracked work.",
            ),
        ),
    )


def _duplicate_literals(
    relative: str,
    source_text: str,
    thresholds: MaintainabilityThresholds,
) -> tuple[CodeHealthFinding, ...]:
    literals = Counter(
        body
        for match in _STRING_LITERAL_RE.finditer(source_text)
        for body in (match.group("body"),)
        if len(body) >= thresholds.duplicate_literal_min_length
    )
    return tuple(
        _generic_finding(
            FindingSpec(
                rule_id="generic.duplicate_literal",
                title="Duplicate literal string",
                message=f"{relative} repeats a literal {count} times.",
                file_path=relative,
                symbol=None,
                severity="info",
                confidence=0.7,
                evidence={"literal": literal, "count": count},
                suggested_action="Name the repeated literal once and reuse it.",
            ),
        )
        for literal, count in literals.items()
        if count >= thresholds.duplicate_literal_min_count
    )


def _generic_finding(spec: FindingSpec) -> CodeHealthFinding:
    # Set provenance explicitly: text-only heuristics over an arbitrary language,
    # so resolution is "text" (not regex/ast) and language is "generic". The
    # model's default derivation would mis-tag these as typescript/regex.
    return build_finding(
        replace(
            spec,
            confidence_tier=CONFIDENCE_TIER_HEURISTIC,
            provenance={
                "rule_id": spec.rule_id,
                "language": "generic",
                "resolution": "text",
                "symbol_resolved": False,
            },
        ),
    )


def _todo_marker(line: str) -> bool:
    folded = line.upper()
    return any(marker in folded for marker in _TODO_MARKERS)
