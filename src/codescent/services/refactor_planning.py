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
        # A finding can point at a file that is not in the code index -- an empty
        # path (stale row not yet rescanned) or a real-but-non-indexed file
        # (generic-pack findings on docs/.md/.html/.json). get_file_context reads
        # the index and raises LookupError for those; degrade to the finding's own
        # detail instead of letting it surface as a non-recoverable internal error.
        try:
            file_context = (
                ContextService(self.repo_root).get_file_context(finding.file_path)
                if finding.file_path
                else None
            )
        except LookupError:
            file_context = None
        if file_context is None:
            no_context_note = (
                "no indexed source context for this finding's file; "
                "see message and evidence"
            )
            return FindingContext(
                finding_id=finding.id,
                rule_id=finding.rule_id,
                summary=_summary(finding),
                affected_files=(finding.file_path,) if finding.file_path else (),
                relevant_symbols=(),
                relevant_tests=(),
                source_ranges=(),
                risk_notes=(no_context_note,),
                suggested_action=finding.suggested_action,
                next_tools=("explain_finding", "suggest_tests"),
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
        location = (
            context.affected_files[0] if context.affected_files else "the finding"
        )
        return SafeRefactorPlan(
            finding_id=finding_id,
            goal=f"Address {context.rule_id} in {location}.",
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
        likely_tests_seed, related_results = _impact_file_signals(
            context,
            file_path,
            tolerate_missing=finding_id is not None,
        )
        related_files = tuple(item["path"] for item in related_results)
        likely_tests = _dedupe(
            (
                *likely_tests_seed,
                *tuple(path for path in related_files if path.startswith("tests/")),
            ),
        )
        affected_files = _dedupe((file_path, *related_files))
        risk_notes = _impact_risk_notes(
            related_results,
            git_changed_paths(resolve_repo_root(self.repo_root)),
        )
        return ImpactReport(
            target_type=resolved_type,
            target=resolved_target,
            affected_files=affected_files,
            likely_tests=likely_tests,
            risk_notes=risk_notes,
            confidence=_impact_confidence(related_results),
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


def _impact_file_signals(
    context: ContextService,
    file_path: str,
    *,
    tolerate_missing: bool,
) -> tuple[tuple[str, ...], tuple[RelatedFilePayload, ...]]:
    """Return (likely_tests, related_files) for a target file's blast radius.

    A non-indexed file (e.g. a generic-pack finding on a doc/.md file) makes
    get_file_context / get_related_files raise LookupError. When
    ``tolerate_missing`` (a finding target, which is a real file), degrade to
    empty signals rather than crashing the tool. An explicit file/symbol target
    keeps raising so callers like refactor_preflight can surface "not indexed".
    """
    if not file_path:
        return (), ()
    try:
        likely_tests = context.get_file_context(file_path)["likely_tests"]
        related = context.get_related_files(file_path, limit=10)["results"]
    except LookupError:
        if not tolerate_missing:
            raise
        return (), ()
    return likely_tests, related


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
