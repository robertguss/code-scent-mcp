import json
from typing import final

import pytest

from codescent.services.subjective_review import (
    FindingMetadata,
    SamplingSubjectiveReviewProvider,
    build_subjective_review_prompt,
)


@final
class _Reply:
    def __init__(self, text: str) -> None:
        self._text = text

    @property
    def text(self) -> str:
        return self._text


@final
class _Channel:
    def __init__(self, text: str) -> None:
        self._text = text

    async def sample(self, messages: str) -> _Reply:
        _ = messages
        return _Reply(self._text)


@final
class _RaisingChannel:
    async def sample(self, messages: str) -> _Reply:
        _ = messages
        message = "Client does not support sampling"
        raise ValueError(message)


@pytest.mark.anyio
async def test_sampling_provider_parses_json_array_into_findings() -> None:
    items = [
        {"file_path": "a.py", "title": "T1", "message": "M1", "confidence": 0.7},
        {"file_path": "b.py", "title": "T2", "message": "M2", "confidence": 5},
    ]
    channel = _Channel(json.dumps(items))

    provider = await SamplingSubjectiveReviewProvider.from_sampling(channel, "p")
    findings = provider.review("p")

    assert provider.available is True
    assert len(findings) == 2
    assert all(finding.subjective for finding in findings)
    assert all(finding.provider == "sampling" for finding in findings)
    assert all(finding.provenance == "subjective" for finding in findings)
    assert all(finding.confidence_tier == "subjective" for finding in findings)
    assert findings[0].confidence == 0.7
    assert findings[1].confidence == 1.0  # clamped into [0, 1]
    assert findings[0].id != findings[1].id


@pytest.mark.anyio
async def test_sampling_provider_handles_code_fenced_json() -> None:
    body = json.dumps([{"file_path": "a.py", "title": "T", "message": "M"}])
    channel = _Channel("```json\n" + body + "\n```")

    provider = await SamplingSubjectiveReviewProvider.from_sampling(channel, "p")
    findings = provider.review("p")

    assert len(findings) == 1
    assert findings[0].file_path == "a.py"
    assert findings[0].confidence == 0.5  # default when omitted


@pytest.mark.anyio
async def test_sampling_provider_falls_back_for_non_json_response() -> None:
    channel = _Channel("Looks risky but I cannot be certain.")

    provider = await SamplingSubjectiveReviewProvider.from_sampling(channel, "p")
    findings = provider.review("p")

    assert len(findings) == 1
    assert findings[0].subjective is True
    assert "risky" in findings[0].message


@pytest.mark.anyio
async def test_sampling_provider_degrades_when_client_cannot_sample() -> None:
    provider = await SamplingSubjectiveReviewProvider.from_sampling(
        _RaisingChannel(),
        "p",
    )

    assert provider.available is False
    assert provider.review("p") == ()


def test_prompt_carries_scrubbed_metadata_never_source() -> None:
    metadata = (
        FindingMetadata(
            rule_id="python.large_function",
            file_path="src/app.py",
            severity="warning",
            title="Large function",
            message="api_key=sk-SECRETVALUE12345 and admin@example.com leaked",
        ),
    )

    prompt = build_subjective_review_prompt(metadata)

    assert "CodeScent subjective review prompt" in prompt
    assert "python.large_function" in prompt
    assert "src/app.py" in prompt
    assert "sk-SECRETVALUE12345" not in prompt
    assert "admin@example.com" not in prompt
    assert "[redacted]" in prompt


def test_empty_metadata_keeps_base_prompt() -> None:
    assert build_subjective_review_prompt() == build_subjective_review_prompt(())
    assert "CodeScent subjective review prompt" in build_subjective_review_prompt()
