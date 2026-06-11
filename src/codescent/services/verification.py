from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from codescent.services.context import ContextService
from codescent.storage import RepositoryStorage, initialize_storage
from codescent.storage.repositories import FindingRepository

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True, slots=True)
class SuggestedTests:
    commands: tuple[str, ...]
    likely_tests: tuple[str, ...]
    executes_in_v1: bool


@dataclass(frozen=True, slots=True)
class VerificationRecommendation:
    recommendation_id: int
    recommended_commands: tuple[str, ...]
    likely_tests: tuple[str, ...]
    missing_characterization_tests: tuple[str, ...]
    executes: bool


@dataclass(frozen=True, slots=True)
class VerificationService:
    repo_root: Path | str

    def suggest_tests(self, file_path: str) -> SuggestedTests:
        context = ContextService(self.repo_root).get_file_context(file_path)
        likely_tests = context["likely_tests"]
        commands = tuple(f"pytest {path}" for path in likely_tests)
        return SuggestedTests(
            commands=commands or ("pytest",),
            likely_tests=likely_tests,
            executes_in_v1=False,
        )

    def verify_change(self, finding_id: str) -> VerificationRecommendation:
        state = initialize_storage(self.repo_root)
        finding = FindingRepository(RepositoryStorage(state)).get_finding(finding_id)
        suggested = self.suggest_tests(finding.file_path)
        reason = f"Verify deterministic finding {finding.rule_id} without execution."
        with RepositoryStorage(state).write_transaction() as connection:
            cursor = connection.execute(
                """
                insert into suggested_verifications (
                    finding_id,
                    command,
                    reason,
                    executes_in_v1
                ) values (?, ?, ?, ?)
                """,
                (
                    finding.id,
                    suggested.commands[0],
                    reason,
                    0,
                ),
            )
        recommendation_id = cursor.lastrowid
        if recommendation_id is None:
            recommendation_id = 0
        return VerificationRecommendation(
            recommendation_id=recommendation_id,
            recommended_commands=suggested.commands,
            likely_tests=suggested.likely_tests,
            missing_characterization_tests=(),
            executes=False,
        )
