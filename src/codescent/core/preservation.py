from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

_ALWAYS_PRESERVE_REASONS: dict[str, str] = {
    "error": "error",
    "traceback": "traceback",
    "failing_assertion": "failing assertion",
    "public_api": "public API",
    "security_finding": "security finding",
    "highest_severity_finding": "highest-severity finding",
    "circular_dependency": "circular dependency",
    "unreadable_file": "unreadable file",
    "permission_error": "permission error",
    "environment_error": "environment error",
    "failed_command": "failed command",
}

_FINDING_SEVERITY_PRIORITY: dict[str, int] = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
    "info": 4,
}

_ORDINARY_PRIORITY = 5


@dataclass(frozen=True, slots=True)
class TokenEstimate:
    tokens: int
    basis: str


@dataclass(frozen=True, slots=True)
class PreservationCandidate:
    kind: str
    title: str
    message: str
    severity: str = ""
    content: str = ""
    source_range: tuple[int, int] | None = None
    snippet: str | None = None


@dataclass(frozen=True, slots=True)
class PreservationDecision:
    kind: str
    title: str
    message: str
    severity: str
    priority: int
    preserve_reason: str
    retrieval_required: bool
    warnings: tuple[str, ...]
    token_estimate: int
    token_basis: str
    source_range: tuple[int, int] | None
    snippet: str | None


def estimate_token_usage(text: str) -> TokenEstimate:
    if text == "":
        return TokenEstimate(tokens=0, basis="empty input")

    byte_count = len(text.encode("utf-8", "surrogatepass"))
    newline_count = text.count("\n")
    estimated_tokens = ceil(byte_count / 4) + newline_count
    return TokenEstimate(
        tokens=estimated_tokens,
        basis=(
            "ceil(utf-8-surrogatepass-bytes/4) + newline_count "
            f"(bytes={byte_count}, newlines={newline_count})"
        ),
    )


def rank_preservation_items(
    items: Iterable[PreservationCandidate],
    *,
    token_budget: int | None = None,
) -> tuple[PreservationDecision, ...]:
    decisions = [_build_decision(item, token_budget=token_budget) for item in items]
    return tuple(
        sorted(
            decisions,
            key=lambda decision: (
                decision.priority,
                decision.severity,
                decision.kind,
                decision.title.casefold(),
                decision.message.casefold(),
            ),
        )
    )


def _build_decision(
    item: PreservationCandidate,
    *,
    token_budget: int | None,
) -> PreservationDecision:
    text = item.snippet if item.snippet is not None else item.content or item.message
    token_estimate = estimate_token_usage(text)
    priority, preserve_reason = _preservation_priority(item)
    retrieval_required = (
        token_budget is not None and token_estimate.tokens > token_budget
    )
    warnings = (
        (
            (
                f"retrieval_required: estimated {token_estimate.tokens} tokens exceeds "
                f"budget {token_budget}"
            ),
        )
        if retrieval_required
        else ()
    )
    return PreservationDecision(
        kind=item.kind,
        title=item.title,
        message=item.message,
        severity=item.severity,
        priority=priority,
        preserve_reason=preserve_reason,
        retrieval_required=retrieval_required,
        warnings=warnings,
        token_estimate=token_estimate.tokens,
        token_basis=token_estimate.basis,
        source_range=item.source_range,
        snippet=item.snippet,
    )


def _preservation_priority(item: PreservationCandidate) -> tuple[int, str]:
    normalized_kind = _normalize(item.kind)
    preserve_reason = _ALWAYS_PRESERVE_REASONS.get(normalized_kind)
    if preserve_reason is not None:
        return 0, preserve_reason

    severity = _normalize(item.severity)
    if normalized_kind == "finding" and severity in _FINDING_SEVERITY_PRIORITY:
        return 1 + _FINDING_SEVERITY_PRIORITY[severity], f"finding severity={severity}"

    if normalized_kind in {"finding", "issue", "smell"}:
        return 3, f"ordinary {normalized_kind}"

    return _ORDINARY_PRIORITY, "ordinary content"


def _normalize(value: str) -> str:
    return value.casefold().strip().replace(" ", "_").replace("-", "_")
