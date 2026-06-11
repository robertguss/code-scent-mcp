from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from pydantic import BaseModel, ConfigDict

from codescent.services.context import ContextService
from codescent.services.verification import SuggestedTests, VerificationService
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
