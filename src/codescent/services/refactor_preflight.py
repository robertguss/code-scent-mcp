"""Compose existing analyses into one bounded refactor blast-radius bundle.

Pure orchestration: given a file/symbol or finding id, this bundles four
already-shipped capabilities into a single deduped, bounded payload so an agent
does not have to chain ``get_impact`` + git co-change + ``select_tests`` +
``get_changed_file_health`` (and know all four exist):

* impact / blast radius -> :class:`RefactorPlanningService.get_impact`
* git co-change coupling -> :func:`codescent.services.git.git_co_change_counts`
* minimal verification set -> :class:`VerificationService.select_tests`
* changed-file health     -> :class:`RiskService.get_changed_file_health`

No new analysis is invented; each section equals what its component service
returns when called directly. The bundle introduces only the co-change list,
which inherits the most restrictive existing per-section cap
(``git`` co-change tops out at :data:`SECTION_ITEM_CAP`); every list section is
held to that ceiling. None of the four sections carry source ranges, so the
"drop source ranges before raising caps" fallback never has to fire. Missing
inputs (no git history, an unindexed target) degrade to an empty section with a
reason in ``warnings`` rather than crashing.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import TYPE_CHECKING

from codescent.core.errors import CodeScentError
from codescent.core.paths import resolve_repo_root
from codescent.services.git import CO_CHANGE_MAX_RESULTS, git_co_change_counts
from codescent.services.refactor_planning import ImpactReport, RefactorPlanningService
from codescent.services.risk import ChangedFileHealth, RiskService
from codescent.services.verification import SelectedTests, VerificationService

if TYPE_CHECKING:
    from pathlib import Path

# The most restrictive existing per-section cap among the composed components.
SECTION_ITEM_CAP = CO_CHANGE_MAX_RESULTS

PREFLIGHT_NEXT_TOOLS = ("plan_refactor", "verify_refactor", "select_tests")


@dataclass(frozen=True, slots=True)
class CoChangeEntry:
    path: str
    commits: int


@dataclass(frozen=True, slots=True)
class RefactorPreflightBundle:
    ok: bool
    target_type: str
    target: str
    file_path: str
    impact: ImpactReport
    co_change: tuple[CoChangeEntry, ...]
    test_selection: SelectedTests
    changed_file_health: ChangedFileHealth
    warnings: tuple[str, ...]
    next_tools: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RefactorPreflightService:
    repo_root: Path | str

    def preflight(
        self,
        *,
        target: str | None = None,
        target_type: str = "file",
        finding_id: str | None = None,
    ) -> RefactorPreflightBundle:
        repo_root = resolve_repo_root(self.repo_root)
        warnings: list[str] = []

        impact = self._impact(
            target=target,
            target_type=target_type,
            finding_id=finding_id,
            warnings=warnings,
        )
        resolved_type, resolved_target = _resolved_identity(
            impact,
            target,
            target_type,
            finding_id,
        )
        file_path = _primary_path(impact, target, target_type)
        if not file_path:
            warnings.append("no resolvable file/symbol/finding target")

        co_change = self._co_change(repo_root, file_path, warnings)
        test_selection = self._test_selection(file_path)
        health = self._changed_file_health(file_path, warnings)

        return RefactorPreflightBundle(
            ok=bool(file_path),
            target_type=resolved_type,
            target=resolved_target,
            file_path=file_path,
            impact=_bound_impact(
                impact or _empty_impact(resolved_type, resolved_target)
            ),
            co_change=co_change,
            test_selection=_bound_selection(test_selection),
            changed_file_health=_bound_health(health or _empty_health(file_path)),
            warnings=tuple(warnings),
            next_tools=PREFLIGHT_NEXT_TOOLS,
        )

    def _impact(
        self,
        *,
        target: str | None,
        target_type: str,
        finding_id: str | None,
        warnings: list[str],
    ) -> ImpactReport | None:
        try:
            return RefactorPlanningService(self.repo_root).get_impact(
                target=target,
                target_type=target_type,
                finding_id=finding_id,
            )
        except (LookupError, IndexError, CodeScentError):
            # A bad finding id now raises a structured not-found CodeScentError
            # (U2); keep degrading impact to a warning here rather than failing
            # the whole preflight bundle for one unindexed/unknown target.
            warnings.append("impact unavailable: target not indexed")
            return None

    def _co_change(
        self,
        repo_root: Path,
        file_path: str,
        warnings: list[str],
    ) -> tuple[CoChangeEntry, ...]:
        if not file_path:
            return ()
        counts = git_co_change_counts(repo_root, file_path)
        if not counts:
            warnings.append("co-change empty: no shared git history for target")
        return tuple(
            CoChangeEntry(path=path, commits=commits)
            for path, commits in counts[:SECTION_ITEM_CAP]
        )

    def _test_selection(self, file_path: str) -> SelectedTests:
        paths = (file_path,) if file_path else ()
        return VerificationService(self.repo_root).select_tests(paths=paths)

    def _changed_file_health(
        self,
        file_path: str,
        warnings: list[str],
    ) -> ChangedFileHealth | None:
        if not file_path:
            return None
        try:
            return RiskService(self.repo_root).get_changed_file_health(file_path)
        except LookupError:
            warnings.append("changed-file health unavailable: target not indexed")
            return None


def _primary_path(
    impact: ImpactReport | None,
    target: str | None,
    target_type: str,
) -> str:
    if impact is not None and impact.affected_files:
        return impact.affected_files[0]
    if target_type == "file" and target:
        return target
    return ""


def _resolved_identity(
    impact: ImpactReport | None,
    target: str | None,
    target_type: str,
    finding_id: str | None,
) -> tuple[str, str]:
    if impact is not None:
        return impact.target_type, impact.target
    if finding_id is not None:
        return "finding", finding_id
    return target_type, target or ""


def _empty_impact(target_type: str, target: str) -> ImpactReport:
    return ImpactReport(
        target_type=target_type,
        target=target,
        affected_files=(),
        likely_tests=(),
        risk_notes=(),
        confidence=0.0,
    )


def _empty_health(path: str) -> ChangedFileHealth:
    return ChangedFileHealth(
        ok=False,
        path=path,
        risk_score=0.0,
        risk_level="low",
        findings=(),
        suggested_tests=(),
        recommended_commands=(),
        risk_notes=(),
    )


def _bound[T](items: tuple[T, ...]) -> tuple[T, ...]:
    return items[:SECTION_ITEM_CAP]


def _bound_impact(impact: ImpactReport) -> ImpactReport:
    return dataclasses.replace(
        impact,
        affected_files=_bound(impact.affected_files),
        likely_tests=_bound(impact.likely_tests),
        risk_notes=_bound(impact.risk_notes),
    )


def _bound_selection(selection: SelectedTests) -> SelectedTests:
    return dataclasses.replace(
        selection,
        changed_files=_bound(selection.changed_files),
        test_files=_bound(selection.test_files),
    )


def _bound_health(health: ChangedFileHealth) -> ChangedFileHealth:
    return dataclasses.replace(
        health,
        findings=_bound(health.findings),
        suggested_tests=_bound(health.suggested_tests),
        recommended_commands=_bound(health.recommended_commands),
        risk_notes=_bound(health.risk_notes),
    )
