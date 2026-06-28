from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final, Protocol, cast

from mcp.shared.exceptions import McpError

from codescent.services.config import ConfigService
from codescent.storage import RepositoryStorage, initialize_storage

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

PRIVACY_NOTICE = (
    "Subjective LLM review is disabled by default. Enable it only when you "
    "intend to send prompt context to the selected provider."
)

# Subjective findings are a distinct provenance class: they never carry the
# deterministic ``verified``/``heuristic`` tiers and live in their own table.
CONFIDENCE_TIER_SUBJECTIVE: Final = "subjective"
PROVENANCE_SUBJECTIVE: Final = "subjective"

_DEFAULT_CONFIDENCE: Final = 0.5
_MIN_CONFIDENCE: Final = 0.0
_MAX_CONFIDENCE: Final = 1.0
_REDACTED: Final = "[redacted]"

_PROMPT_BASE: Final = (
    "CodeScent subjective review prompt\n"
    "Review deterministic findings only as subjective judgment.\n"
    "Label all returned items as subjective and provider-scoped."
)
_PROMPT_INSTRUCTIONS: Final = (
    'Respond with a JSON array. Each item must be {"file_path": string, '
    '"title": string, "message": string, "confidence": number between 0 and 1}. '
    "Judge ONLY the finding metadata listed below; never request, infer, or "
    "reproduce file contents."
)

# ponytail: regex secret/PII scrub mirroring sanitize_event_payload's "emit only
# safe values" discipline. Heuristic, not exhaustive; upgrade to entropy-based
# detection if real leakage is ever observed.
_KEYED_SECRET: Final = re.compile(
    r"""(?ix)
    \b(api[_-]?key|secret|token|password|passwd|pwd|authorization|bearer)\b
    \s*[:=]\s*\S+
    """,
)
_SECRET_PATTERNS: Final = (
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),  # emails
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),  # AWS access key ids
    re.compile(r"\b[A-Za-z0-9+/]{40,}={0,2}\b"),  # long base64-ish secrets
    re.compile(r"\b[0-9a-fA-F]{32,}\b"),  # long hex tokens/hashes
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
    confidence_tier: str = CONFIDENCE_TIER_SUBJECTIVE
    provenance: str = PROVENANCE_SUBJECTIVE


@dataclass(frozen=True, slots=True)
class FindingMetadata:
    rule_id: str
    file_path: str
    severity: str
    title: str
    message: str


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


class SamplingReply(Protocol):
    @property
    def text(self) -> str | None: ...


class SamplingChannel(Protocol):
    """A client-backed sampling transport (FastMCP ``Context`` satisfies this).

    The CodeScent server never calls a model directly; ``sample`` routes the
    request back through the MCP session so the *client's* LLM responds.
    """

    async def sample(self, messages: str) -> SamplingReply: ...


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
class SamplingSubjectiveReviewProvider:
    """Subjective provider backed by client-side MCP sampling.

    ``from_sampling`` issues the sampling request through the MCP session (no
    server network call) and captures the client model's text. ``review`` then
    parses that text into subjective findings. When the client cannot sample the
    provider is returned in an ``available=False`` state so callers degrade
    gracefully instead of crashing.
    """

    response_text: str | None
    available: bool

    @property
    def name(self) -> str:
        return "sampling"

    @classmethod
    async def from_sampling(
        cls,
        channel: SamplingChannel,
        prompt: str,
    ) -> SamplingSubjectiveReviewProvider:
        # ponytail: relies on the client default max_tokens (512). Thread a
        # larger budget through SamplingChannel if reviews get truncated.
        try:
            reply = await channel.sample(prompt)
        except (ValueError, McpError):
            return cls(response_text=None, available=False)
        else:
            return cls(response_text=reply.text, available=True)

    def review(self, prompt: str) -> tuple[SubjectiveFinding, ...]:
        if not self.available or self.response_text is None:
            return ()
        return _parse_sampled_findings(self.name, prompt, self.response_text)


@dataclass(frozen=True, slots=True)
class SubjectiveReviewService:
    repo_root: Path | str

    def is_enabled(self, allow_subjective: bool | None = None) -> bool:
        if allow_subjective is not None:
            return allow_subjective
        return ConfigService(self.repo_root).load().privacy.allow_llm_review

    def review(
        self,
        *,
        provider_name: str,
        provider: SubjectiveReviewProvider | None = None,
        allow_subjective: bool | None = None,
        prompt: str | None = None,
    ) -> SubjectiveReviewResult:
        enabled = self.is_enabled(allow_subjective)
        resolved_prompt = (
            prompt if prompt is not None else build_subjective_review_prompt()
        )
        if not enabled:
            return SubjectiveReviewResult(
                enabled=False,
                provider="disabled",
                privacy_notice=PRIVACY_NOTICE,
                prompt=resolved_prompt,
                subjective_findings=(),
            )
        review_provider = provider or _provider(provider_name)
        findings = review_provider.review(resolved_prompt)
        _store_subjective_findings(self.repo_root, resolved_prompt, findings)
        return SubjectiveReviewResult(
            enabled=True,
            provider=review_provider.name,
            privacy_notice=PRIVACY_NOTICE,
            prompt=resolved_prompt,
            subjective_findings=findings,
        )


def build_subjective_review_prompt(findings: Sequence[FindingMetadata] = ()) -> str:
    if not findings:
        return _PROMPT_BASE
    lines = [_PROMPT_BASE, "", _PROMPT_INSTRUCTIONS, "", "Findings (metadata only):"]
    lines.extend(
        _scrub_secrets(_format_metadata(index, finding))
        for index, finding in enumerate(findings, start=1)
    )
    return "\n".join(lines)


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
            "confidence_tier": finding.confidence_tier,
            "provenance": finding.provenance,
        }
        for finding in findings
    ]


def _format_metadata(index: int, finding: FindingMetadata) -> str:
    return (
        f"{index}. rule={finding.rule_id} severity={finding.severity} "
        f"file={finding.file_path} | {finding.title}: {finding.message}"
    )


def _scrub_secrets(text: str) -> str:
    scrubbed = _KEYED_SECRET.sub(_redact_keyed, text)
    for pattern in _SECRET_PATTERNS:
        scrubbed = pattern.sub(_REDACTED, scrubbed)
    return scrubbed


def _redact_keyed(match: re.Match[str]) -> str:
    return f"{match.group(1)}={_REDACTED}"


def _parse_sampled_findings(
    provider: str,
    prompt: str,
    response_text: str,
) -> tuple[SubjectiveFinding, ...]:
    cleaned = response_text.strip()
    if not cleaned:
        return ()
    items = _coerce_items(cleaned)
    if items is None:
        return (_finding_from_text(provider, prompt, cleaned),)
    return tuple(
        _finding_from_item(provider, prompt, item, index)
        for index, item in enumerate(items)
    )


def _coerce_items(text: str) -> list[dict[str, object]] | None:
    decoded = _safe_json(_strip_code_fence(text))
    if isinstance(decoded, dict):
        return [cast("dict[str, object]", decoded)]
    if isinstance(decoded, list):
        raw_items = cast("list[object]", decoded)
        return [
            cast("dict[str, object]", item)
            for item in raw_items
            if isinstance(item, dict)
        ]
    return None


def _safe_json(text: str) -> object:
    try:
        return cast("object", json.loads(text))
    except json.JSONDecodeError:
        return None


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    inner = stripped.splitlines()[1:]
    if inner and inner[-1].strip() == "```":
        inner = inner[:-1]
    return "\n".join(inner).strip()


def _finding_from_item(
    provider: str,
    prompt: str,
    item: dict[str, object],
    index: int,
) -> SubjectiveFinding:
    file_path = _as_text(item.get("file_path")) or "unknown"
    title = _as_text(item.get("title")) or "Subjective review note"
    message = _as_text(item.get("message"))
    confidence = _as_confidence(item.get("confidence"))
    seed = f"{prompt}|{index}|{file_path}|{title}|{message}"
    return SubjectiveFinding(
        id=_subjective_id(provider, seed),
        provider=provider,
        file_path=file_path,
        title=title,
        message=message,
        confidence=confidence,
        subjective=True,
    )


def _finding_from_text(provider: str, prompt: str, text: str) -> SubjectiveFinding:
    seed = f"{prompt}|fallback|{text}"
    return SubjectiveFinding(
        id=_subjective_id(provider, seed),
        provider=provider,
        file_path="unknown",
        title="Subjective review note",
        message=text,
        confidence=_DEFAULT_CONFIDENCE,
        subjective=True,
    )


def _subjective_id(provider: str, seed: str) -> str:
    digest = hashlib.sha256(seed.encode()).hexdigest()[:12]
    return f"subjective.{provider}:{digest}"


def _as_text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _as_confidence(value: object) -> float:
    if isinstance(value, bool):
        return _DEFAULT_CONFIDENCE
    if isinstance(value, int | float):
        return max(_MIN_CONFIDENCE, min(_MAX_CONFIDENCE, float(value)))
    return _DEFAULT_CONFIDENCE


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
