"""Derived code-quality ranking signals.

Reads the PERSISTED findings (never a fresh scan) and turns them into per-path
quality flags -- hotspot (churn x size), dead code, structural duplication and
complexity -- plus the duplicate's twin location. These ride the shared
``RankingSignals`` seam so every retrieval surface down-weights dead/duplicate
code, flags risky (hotspot/complex) code, and annotates results inline. This is
strictly READ-ONLY over the Inspector's facts: it never scans, never writes a
finding, and degrades to neutral (``{}``) when a repo has no persisted findings.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from typing import TYPE_CHECKING, TypedDict

from codescent.core.json_decode import decode_json_object
from codescent.core.models import FindingStatus
from codescent.engine.search.ranking import PathQuality
from codescent.services.git import git_change_counts
from codescent.storage import RepositoryStorage, initialize_storage
from codescent.storage.repositories import FindingRepository

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from pathlib import Path

    from codescent.engine.search.ranking import QualityFlag
    from codescent.storage.repositories import FindingRow


class QualityAnnotation(TypedDict):
    """Bounded inline quality annotation attached to a search result."""

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
    flags_by_path: dict[str, set[QualityFlag]] = {}
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


def _flags_for(finding: FindingRow, churn: Mapping[str, int]) -> set[QualityFlag]:
    return _flags_from(
        finding.rule_id,
        finding.file_path,
        finding.evidence_json,
        churn,
    )


def _flags_from(
    rule_id: str,
    file_path: str,
    evidence_json: str,
    churn: Mapping[str, int],
) -> set[QualityFlag]:
    flags: set[QualityFlag] = set()
    if rule_id in _DEAD_RULES:
        flags.add("dead_code")
    if rule_id in _DUPLICATE_RULES:
        flags.add("duplicate")
    if rule_id in _COMPLEX_RULES:
        flags.add("complex")
    if (
        rule_id in _SIZE_RULES
        and churn.get(file_path, 0) > 0
        and _line_count(evidence_json) > 0
    ):
        flags.add("hotspot")
    return flags


def quality_flags_for_paths(
    repo_root: Path,
    paths: Iterable[str],
) -> dict[str, tuple[str, ...]]:
    """Active quality flags for a SMALL set of paths, via a path-filtered query.

    The hook health surface needs flags only for the handful of git-modified
    matched files, so this folds findings for just those paths instead of
    loading the whole findings store like :func:`quality_signals_for` (R8). A
    missing index or absent path yields no entry; never scans, never writes.
    """
    selected = tuple(dict.fromkeys(path for path in paths if path))
    if not selected:
        return {}
    database = repo_root / ".codescent" / "index.sqlite"
    if not database.exists():
        return {}
    churn = git_change_counts(repo_root)
    placeholders = ",".join("?" * len(selected))
    try:
        with closing(sqlite3.connect(database)) as connection:
            rows: list[tuple[str, str, str, str]] = connection.execute(
                f"""
                select findings.rule_id, files.path, findings.evidence_json,
                    findings.status
                from findings
                join files on files.id = findings.file_id
                where files.path in ({placeholders})
                """,  # noqa: S608 - placeholders are bound params, not interpolated values
                selected,
            ).fetchall()
    except sqlite3.DatabaseError:
        return {}
    flags_by_path: dict[str, set[QualityFlag]] = {}
    for rule_id, path, evidence_json, status in rows:
        if FindingStatus(status) not in _ACTIVE_STATUSES:
            continue
        flags = _flags_from(rule_id, path, evidence_json or "{}", churn)
        if flags:
            flags_by_path.setdefault(path, set()).update(flags)
    return {path: tuple(sorted(flags)) for path, flags in flags_by_path.items()}


def _twin_for(finding: FindingRow) -> str | None:
    for entry in _locations(finding.evidence_json):
        twin_path = entry.split(":", 1)[0].strip()
        if twin_path and twin_path != finding.file_path:
            return twin_path
    return None


def _locations(evidence_json: str) -> tuple[str, ...]:
    value = decode_json_object(evidence_json).get("locations")
    if not isinstance(value, str):
        return ()
    return tuple(part.strip() for part in value.split(";") if part.strip())


def _line_count(evidence_json: str) -> int:
    value = decode_json_object(evidence_json).get("line_count")
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return max(value, 0)
