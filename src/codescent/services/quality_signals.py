"""Derived code-quality ranking signals (plan unit U13 / bead P3.2).

Reads the PERSISTED findings (never a fresh scan) and turns them into per-path
quality flags -- hotspot (churn x size), dead code, structural duplication and
complexity -- plus the duplicate's twin location. These ride the shared
``RankingSignals`` seam so every retrieval surface down-weights dead/duplicate
code, flags risky (hotspot/complex) code, and annotates results inline. This is
strictly READ-ONLY over the Inspector's facts: it never scans, never writes a
finding, and degrades to neutral (``{}``) when a repo has no persisted findings.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, TypedDict, cast

from codescent.core.models import FindingStatus
from codescent.engine.search.ranking import PathQuality
from codescent.services.git import git_change_counts
from codescent.storage import RepositoryStorage, initialize_storage
from codescent.storage.repositories import FindingRepository

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from codescent.storage.repositories import FindingRow


class QualityAnnotation(TypedDict):
    """Bounded inline quality annotation attached to a search result (U13)."""

    flags: tuple[str, ...]
    duplicate_twin: str | None


# Quality only describes the current code while a finding is still actionable; a
# resolved or suppressed finding no longer applies, so it does not annotate.
_ACTIVE_STATUSES: frozenset[FindingStatus] = frozenset(
    {
        FindingStatus.OPEN,
        FindingStatus.IN_PROGRESS,
        FindingStatus.REGRESSED,
        FindingStatus.NEEDS_REVIEW,
    },
)
_DEAD_RULES: frozenset[str] = frozenset({"python.dead_code_candidate"})
_DUPLICATE_RULES: frozenset[str] = frozenset(
    {
        "python.structural_near_duplicate",
        "python.duplicate_literal",
        "typescript.duplicate_literal",
    },
)
_COMPLEX_RULES: frozenset[str] = frozenset(
    {"python.deep_nesting", "python.mixed_responsibilities"},
)
_SIZE_RULES: frozenset[str] = frozenset(
    {
        "python.large_file",
        "python.large_function",
        "python.large_class",
        "python.relative_large_file",
        "python.relative_large_function",
        "python.relative_large_class",
        "typescript.large_component",
    },
)


def quality_signals_for(repo_root: Path) -> dict[str, PathQuality]:
    """Per-path quality from PERSISTED findings; ``{}`` when none exist.

    Reads the cached findings store (never runs a scan) and folds churn x size,
    dead code, duplication and complexity into one :class:`PathQuality` per
    path. A repo with no persisted findings yields ``{}`` (neutral ranking).
    """
    findings = _active_findings(repo_root)
    if not findings:
        return {}
    churn = git_change_counts(repo_root)
    flags_by_path: dict[str, set[str]] = {}
    twin_by_path: dict[str, str] = {}
    for finding in findings:
        path = finding.file_path
        if not path:
            continue
        flags = _flags_for(finding, churn)
        if not flags:
            continue
        flags_by_path.setdefault(path, set()).update(flags)
        if "duplicate" in flags and path not in twin_by_path:
            twin = _twin_for(finding)
            if twin is not None:
                twin_by_path[path] = twin
    return {
        path: PathQuality(
            flags=tuple(sorted(flags)),
            duplicate_twin=twin_by_path.get(path),
        )
        for path, flags in flags_by_path.items()
    }


def quality_annotation_for(
    path: str,
    quality: Mapping[str, PathQuality],
) -> QualityAnnotation | None:
    """Bounded annotation for ``path``, or ``None`` when it carries no quality."""
    entry = quality.get(path)
    if entry is None or not entry.flags:
        return None
    return {"flags": entry.flags, "duplicate_twin": entry.duplicate_twin}


def _active_findings(repo_root: Path) -> tuple[FindingRow, ...]:
    if not (repo_root / ".codescent" / "index.sqlite").exists():
        return ()
    repository = FindingRepository(RepositoryStorage(initialize_storage(repo_root)))
    return tuple(
        finding
        for finding in repository.list_findings()
        if finding.status in _ACTIVE_STATUSES
    )


def _flags_for(finding: FindingRow, churn: Mapping[str, int]) -> set[str]:
    flags: set[str] = set()
    rule_id = finding.rule_id
    if rule_id in _DEAD_RULES:
        flags.add("dead_code")
    if rule_id in _DUPLICATE_RULES:
        flags.add("duplicate")
    if rule_id in _COMPLEX_RULES:
        flags.add("complex")
    if (
        rule_id in _SIZE_RULES
        and churn.get(finding.file_path, 0) > 0
        and _line_count(finding.evidence_json) > 0
    ):
        flags.add("hotspot")
    return flags


def _twin_for(finding: FindingRow) -> str | None:
    for entry in _locations(finding.evidence_json):
        twin_path = entry.split(":", 1)[0].strip()
        if twin_path and twin_path != finding.file_path:
            return twin_path
    return None


def _locations(evidence_json: str) -> tuple[str, ...]:
    value = _evidence(evidence_json).get("locations")
    if not isinstance(value, str):
        return ()
    return tuple(part.strip() for part in value.split(";") if part.strip())


def _line_count(evidence_json: str) -> int:
    value = _evidence(evidence_json).get("line_count")
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return max(value, 0)


def _evidence(evidence_json: str) -> dict[str, object]:
    try:
        parsed = cast("object", json.loads(evidence_json))
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return cast("dict[str, object]", parsed)
