from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol

from codescent.services.config import ConfigService
from codescent.storage import RepositoryStorage, initialize_storage

if TYPE_CHECKING:
    from pathlib import Path

PRIVACY_NOTICE = (
    "Subjective LLM review is disabled by default. Enable it only when you "
    "intend to send prompt context to the selected provider."
)


@dataclass(frozen=True, slots=True)
class SubjectiveFinding:
    id: str
    provider: str
    file_path: str
    title: str
    message: str
    confidence: float
    subjective: bool


@dataclass(frozen=True, slots=True)
class SubjectiveReviewResult:
    enabled: bool
    provider: str
    privacy_notice: str
    prompt: str
    subjective_findings: tuple[SubjectiveFinding, ...]


class SubjectiveReviewProvider(Protocol):
    @property
    def name(self) -> str: ...

    def review(self, prompt: str) -> tuple[SubjectiveFinding, ...]: ...


@dataclass(frozen=True, slots=True)
class FakeSubjectiveReviewProvider:
    @property
    def name(self) -> str:
        return "fake"

    def review(self, prompt: str) -> tuple[SubjectiveFinding, ...]:
        digest = hashlib.sha256(prompt.encode()).hexdigest()[:12]
        return (
            SubjectiveFinding(
                id=f"subjective.fake:{digest}",
                provider=self.name,
                file_path="src/acme_tasks/workflow.py",
                title="Subjective review: workflow clarity",
                message="Fake provider marked this as subjective review evidence.",
                confidence=0.51,
                subjective=True,
            ),
        )


@dataclass(frozen=True, slots=True)
class SubjectiveReviewService:
    repo_root: Path | str

    def review(
        self,
        *,
        provider_name: str,
        provider: SubjectiveReviewProvider | None = None,
        allow_subjective: bool | None = None,
    ) -> SubjectiveReviewResult:
        config = ConfigService(self.repo_root).load()
        enabled = (
            config.privacy.allow_llm_review
            if allow_subjective is None
            else allow_subjective
        )
        prompt = build_subjective_review_prompt()
        if not enabled:
            return SubjectiveReviewResult(
                enabled=False,
                provider="disabled",
                privacy_notice=PRIVACY_NOTICE,
                prompt=prompt,
                subjective_findings=(),
            )
        review_provider = provider or _provider(provider_name)
        findings = review_provider.review(prompt)
        _store_subjective_findings(self.repo_root, prompt, findings)
        return SubjectiveReviewResult(
            enabled=True,
            provider=review_provider.name,
            privacy_notice=PRIVACY_NOTICE,
            prompt=prompt,
            subjective_findings=findings,
        )


def build_subjective_review_prompt() -> str:
    return (
        "CodeScent subjective review prompt\n"
        "Review deterministic findings only as subjective judgment.\n"
        "Label all returned items as subjective and provider-scoped."
    )


def _provider(provider_name: str) -> SubjectiveReviewProvider:
    if provider_name == "fake":
        return FakeSubjectiveReviewProvider()
    message = "only the fake provider is available in local tests"
    raise ValueError(message)


def _store_subjective_findings(
    repo_root: Path | str,
    prompt: str,
    findings: tuple[SubjectiveFinding, ...],
) -> None:
    state = initialize_storage(repo_root)
    storage = RepositoryStorage(state)
    now = datetime.now(UTC).isoformat()
    with storage.write_transaction() as connection:
        for finding in findings:
            _ = connection.execute(
                """
                insert or replace into subjective_findings (
                    id,
                    provider,
                    prompt,
                    file_path,
                    title,
                    message,
                    confidence,
                    created_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    finding.id,
                    finding.provider,
                    prompt,
                    finding.file_path,
                    finding.title,
                    finding.message,
                    finding.confidence,
                    now,
                ),
            )


def subjective_findings_payload(
    findings: tuple[SubjectiveFinding, ...],
) -> list[dict[str, str | float | bool]]:
    return [
        {
            "id": finding.id,
            "provider": finding.provider,
            "file_path": finding.file_path,
            "title": finding.title,
            "message": finding.message,
            "confidence": finding.confidence,
            "subjective": finding.subjective,
        }
        for finding in findings
    ]
