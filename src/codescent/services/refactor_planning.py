from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from pydantic import BaseModel, ConfigDict

from codescent.core.paths import resolve_repo_root
from codescent.services.context import ContextService, RelatedFilePayload
from codescent.services.git import git_changed_paths
from codescent.services.verification import (
    SuggestedTests,
    VerificationRecommendation,
    VerificationService,
)
from codescent.storage import RepositoryStorage, initialize_storage
from codescent.storage.repositories import FindingRepository, FindingRow

if TYPE_CHECKING:
    from pathlib import Path


class EvidencePayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    line_count: int | None = None
    threshold: int | None = None
    count: int | None = None
    literal: str | None = None
    expected_test: str | None = None
    import_count: int | None = None
    depth: int | None = None
    verb_count: int | None = None
    marker_count: int | None = None


LOW_IMPACT_CONFIDENCE_THRESHOLD = 0.6


@dataclass(frozen=True, slots=True)
class FindingContext:
    finding_id: str
    rule_id: str
    summary: str
    affected_files: tuple[str, ...]
    relevant_symbols: tuple[str, ...]
    relevant_tests: tuple[str, ...]
    source_ranges: tuple[dict[str, str | int], ...]
    risk_notes: tuple[str, ...]
    suggested_action: str
    next_tools: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SafeRefactorPlan:
    finding_id: str
    goal: str
    non_goals: tuple[str, ...]
    affected_files: tuple[str, ...]
    relevant_symbols: tuple[str, ...]
    risk: str
    steps: tuple[str, ...]
    fallback: str
    expected_behavior_preservation: tuple[str, ...]
    verification_recommendations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ImpactReport:
    target_type: str
    target: str
    affected_files: tuple[str, ...]
    likely_tests: tuple[str, ...]
    risk_notes: tuple[str, ...]
    confidence: float


@dataclass(frozen=True, slots=True)
class RefactorPlanningService:
    repo_root: Path | str

    def get_finding_context(self, finding_id: str) -> FindingContext:
        finding = _repository(self.repo_root).get_finding(finding_id)
        file_context = ContextService(self.repo_root).get_file_context(
            finding.file_path,
        )
        return FindingContext(
            finding_id=finding.id,
            rule_id=finding.rule_id,
            summary=_summary(finding),
            affected_files=(finding.file_path,),
            relevant_symbols=_qualified_symbols(
                self.repo_root,
                finding.file_path,
                file_context["symbols"],
            ),
            relevant_tests=file_context["likely_tests"],
            source_ranges=file_context["source_ranges"],
            risk_notes=file_context["risk_notes"],
            suggested_action=finding.suggested_action,
            next_tools=("plan_refactor", "suggest_tests"),
        )

    def plan_refactor(self, finding_id: str) -> SafeRefactorPlan:
        context = self.get_finding_context(finding_id)
        suggested = self.suggest_tests(finding_id)
        return SafeRefactorPlan(
            finding_id=finding_id,
            goal=f"Address {context.rule_id} in {context.affected_files[0]}.",
            non_goals=(
                "Do not edit source files automatically.",
                "Do not change public behavior without tests.",
            ),
            affected_files=context.affected_files,
            relevant_symbols=context.relevant_symbols,
            risk=_risk(context.rule_id),
            steps=(
                "Review the bounded finding context and current tests.",
                "Make the smallest source change that removes the smell.",
                "Run the suggested verification commands.",
                "Rescan with CodeScent and update the finding lifecycle.",
            ),
            fallback="Revert the source change and keep the finding open.",
            expected_behavior_preservation=(
                "Keep existing imports and call sites working.",
                "Preserve test-observed behavior for likely related tests.",
            ),
            verification_recommendations=suggested.commands,
        )

    def suggest_tests(self, finding_id: str) -> SuggestedTests:
        finding = _repository(self.repo_root).get_finding(finding_id)
        return VerificationService(self.repo_root).suggest_tests(finding.file_path)

    def verify_change(self, finding_id: str) -> VerificationRecommendation:
        return VerificationService(self.repo_root).verify_change(finding_id)

    def get_impact(
        self,
        *,
        target: str | None = None,
        target_type: str = "file",
        finding_id: str | None = None,
    ) -> ImpactReport:
        resolved_type = target_type
        resolved_target = target or ""
        file_path = target or ""
        if finding_id is not None:
            finding = _repository(self.repo_root).get_finding(finding_id)
            resolved_type = "finding"
            resolved_target = finding.id
            file_path = finding.file_path
        elif target_type == "symbol" and target is not None:
            symbol = ContextService(self.repo_root, auto_refresh=False).find_symbol(
                target,
                limit=1,
            )[0]
            file_path = symbol["path"]

        context = ContextService(self.repo_root, auto_refresh=False)
        file_context = context.get_file_context(file_path)
        related = context.get_related_files(file_path, limit=10)
        related_files = tuple(item["path"] for item in related["results"])
        likely_tests = _dedupe(
            (
                *file_context["likely_tests"],
                *tuple(path for path in related_files if path.startswith("tests/")),
            ),
        )
        affected_files = _dedupe((file_path, *related_files))
        risk_notes = _impact_risk_notes(
            related["results"],
            git_changed_paths(resolve_repo_root(self.repo_root)),
        )
        return ImpactReport(
            target_type=resolved_type,
            target=resolved_target,
            affected_files=affected_files,
            likely_tests=likely_tests,
            risk_notes=risk_notes,
            confidence=_impact_confidence(related["results"]),
        )


def _repository(repo_root: Path | str) -> FindingRepository:
    state = initialize_storage(repo_root)
    return FindingRepository(RepositoryStorage(state))


def _summary(finding: FindingRow) -> str:
    evidence = EvidencePayload.model_validate_json(finding.evidence_json)
    evidence_keys = ", ".join(sorted(evidence.model_fields_set)) or "no evidence"
    return f"{finding.rule_id} in {finding.file_path}; evidence: {evidence_keys}."


def _qualified_symbols(
    repo_root: Path | str,
    file_path: str,
    symbol_names: tuple[str, ...],
) -> tuple[str, ...]:
    service = ContextService(repo_root)
    symbols: list[str] = []
    for name in symbol_names:
        matches = service.find_symbol(name)
        symbols.extend(
            match["qualified_name"] for match in matches if match["path"] == file_path
        )
    return tuple(dict.fromkeys(symbols))


def _risk(rule_id: str) -> str:
    if rule_id in {"python.large_function", "python.large_class", "python.large_file"}:
        return "medium"
    return "low"


def _dedupe(items: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(item for item in items if item))


def _impact_risk_notes(
    related_files: tuple[RelatedFilePayload, ...],
    changed_paths: frozenset[str],
) -> tuple[str, ...]:
    notes = ["confidence is bounded by deterministic local graph signals"]
    if changed_paths:
        notes.append(f"changed files in worktree: {len(changed_paths)}")
    if any(
        item["confidence"] < LOW_IMPACT_CONFIDENCE_THRESHOLD for item in related_files
    ):
        notes.append("some related files are low-confidence candidates")
    return tuple(notes)


def _impact_confidence(related_files: tuple[RelatedFilePayload, ...]) -> float:
    if not related_files:
        return 0.5
    confidence_values = tuple(float(item["confidence"]) for item in related_files)
    return min(sum(confidence_values) / len(confidence_values), 0.95)
