from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict, final

# Runtime import (not type-checking-only): FastMCP resolves this tool's
# annotations at registration to detect and inject the Context parameter.
from fastmcp import Context  # noqa: TC002

from codescent.services.findings import FindingsService
from codescent.services.subjective_review import (
    PRIVACY_NOTICE,
    FindingMetadata,
    SamplingSubjectiveReviewProvider,
    SubjectiveReviewResult,
    SubjectiveReviewService,
    build_subjective_review_prompt,
    subjective_findings_payload,
)

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from codescent.services.subjective_review import SamplingReply

_NEXT_TOOLS = ("get_backlog", "explain_finding")
_UNAVAILABLE_MESSAGE = (
    "The MCP client does not support sampling, so no subjective review was "
    "performed. CodeScent never calls a model itself."
)


@final
class _ContextSamplingChannel:
    """Bridges the FastMCP ``Context`` to the service's ``SamplingChannel``.

    Keeps the service layer free of any FastMCP import while still routing the
    sampling request through the live MCP session (the client samples).
    """

    def __init__(self, ctx: Context) -> None:
        self._ctx = ctx

    async def sample(self, messages: str) -> SamplingReply:
        return await self._ctx.sample(messages)


class SubjectiveReviewToolPayload(TypedDict):
    ok: bool
    kind: str
    enabled: bool
    sampling_available: bool
    provider: str
    message: str
    privacy_notice: str
    subjective_findings: list[dict[str, str | float | bool]]
    next_tools: tuple[str, ...]


def register_subjective_tools(mcp: FastMCP) -> None:
    _ = mcp.tool(
        description=(
            "OPT-IN subjective second opinion: asks YOUR MCP client's own LLM "
            "(via MCP sampling) to judge deterministic findings. Disabled unless "
            "privacy.allow_llm_review=true. The CodeScent server makes NO network "
            "call; the client samples. Only secret/PII-scrubbed finding metadata "
            "is sent, never source. Results are labeled subjective and never "
            "replace deterministic findings. e.g. subjective_review(repo='.')."
        ),
    )(subjective_review)


async def subjective_review(
    repo: str = ".",
    ctx: Context | None = None,
) -> SubjectiveReviewToolPayload:
    service = SubjectiveReviewService(repo)
    if not service.is_enabled():
        return _disabled_payload(service.review(provider_name="sampling"))
    if ctx is None:
        return _unavailable_payload()
    prompt = build_subjective_review_prompt(_deterministic_metadata(repo))
    channel = _ContextSamplingChannel(ctx)
    provider = await SamplingSubjectiveReviewProvider.from_sampling(channel, prompt)
    if not provider.available:
        return _unavailable_payload()
    result = service.review(
        provider_name="sampling",
        provider=provider,
        allow_subjective=True,
        prompt=prompt,
    )
    return _enabled_payload(result)


def _deterministic_metadata(repo: str) -> tuple[FindingMetadata, ...]:
    report = FindingsService(repo).get_smell_report()
    return tuple(
        FindingMetadata(
            rule_id=finding.rule_id,
            file_path=finding.file_path,
            severity=finding.severity,
            title=finding.title,
            message=finding.message,
        )
        for finding in report.findings
    )


def _disabled_payload(result: SubjectiveReviewResult) -> SubjectiveReviewToolPayload:
    return {
        "ok": True,
        "kind": "subjective_review",
        "enabled": False,
        "sampling_available": False,
        "provider": result.provider,
        "message": result.privacy_notice,
        "privacy_notice": result.privacy_notice,
        "subjective_findings": [],
        "next_tools": _NEXT_TOOLS,
    }


def _unavailable_payload() -> SubjectiveReviewToolPayload:
    return {
        "ok": True,
        "kind": "subjective_review",
        "enabled": True,
        "sampling_available": False,
        "provider": "unavailable",
        "message": _UNAVAILABLE_MESSAGE,
        "privacy_notice": PRIVACY_NOTICE,
        "subjective_findings": [],
        "next_tools": _NEXT_TOOLS,
    }


def _enabled_payload(result: SubjectiveReviewResult) -> SubjectiveReviewToolPayload:
    count = len(result.subjective_findings)
    return {
        "ok": True,
        "kind": "subjective_review",
        "enabled": True,
        "sampling_available": True,
        "provider": result.provider,
        "message": f"Client sampling returned {count} subjective finding(s).",
        "privacy_notice": result.privacy_notice,
        "subjective_findings": subjective_findings_payload(result.subjective_findings),
        "next_tools": _NEXT_TOOLS,
    }
