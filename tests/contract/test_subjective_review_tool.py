import json
from pathlib import Path
from typing import cast

import pytest
from fastmcp import Client
from mcp.types import ContentBlock, TextContent

from codescent.core.models import PrivacySettings, ProjectConfig
from codescent.mcp.finding_tools import scan_code_health
from codescent.mcp.server import mcp
from codescent.services.config import ConfigService


def _payload(content: list[ContentBlock]) -> dict[str, object]:
    assert len(content) == 1
    first = content[0]
    assert isinstance(first, TextContent)
    return cast("dict[str, object]", json.loads(first.text))


def _write_source(repo: Path) -> None:
    source = repo / "src" / "app.py"
    source.parent.mkdir(parents=True)
    _ = source.write_text("def f() -> int:\n    return 1\n")


def _enable_review(repo: Path) -> None:
    _write_source(repo)
    _ = scan_code_health(str(repo))
    ConfigService(repo).save(
        ProjectConfig(privacy=PrivacySettings(allow_llm_review=True)),
    )


async def _fake_model(messages: object, params: object, context: object) -> str:
    _ = messages, params, context
    return json.dumps(
        [
            {
                "file_path": "src/app.py",
                "title": "Naming",
                "message": "Consider clearer names.",
                "confidence": 0.6,
            },
        ],
    )


@pytest.mark.anyio
async def test_subjective_review_is_clean_no_op_when_disabled(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    async with Client(mcp) as client:
        result = await client.call_tool("subjective_review", {"repo": str(repo)})

    payload = _payload(result.content)
    assert payload["ok"] is True
    assert payload["enabled"] is False
    assert payload["sampling_available"] is False
    assert payload["provider"] == "disabled"
    assert payload["subjective_findings"] == []


@pytest.mark.anyio
async def test_subjective_review_graceful_when_client_cannot_sample(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _enable_review(repo)

    # No sampling_handler -> the client advertises no sampling capability.
    async with Client(mcp) as client:
        result = await client.call_tool("subjective_review", {"repo": str(repo)})

    payload = _payload(result.content)
    assert payload["ok"] is True
    assert payload["enabled"] is True
    assert payload["sampling_available"] is False
    assert payload["provider"] == "unavailable"
    assert payload["subjective_findings"] == []


@pytest.mark.anyio
async def test_subjective_review_returns_labeled_findings_when_enabled(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _enable_review(repo)

    async with Client(mcp, sampling_handler=_fake_model) as client:
        result = await client.call_tool("subjective_review", {"repo": str(repo)})

    payload = _payload(result.content)
    assert payload["ok"] is True
    assert payload["enabled"] is True
    assert payload["sampling_available"] is True
    assert payload["provider"] == "sampling"
    findings = cast("list[dict[str, object]]", payload["subjective_findings"])
    assert findings
    assert all(item["subjective"] is True for item in findings)
    assert all(item["confidence_tier"] == "subjective" for item in findings)
    assert all(item["provenance"] == "subjective" for item in findings)
