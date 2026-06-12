from pathlib import Path
from typing import ClassVar

import pytest
from fastmcp import Client
from mcp.types import ContentBlock, TextContent
from pydantic import BaseModel, ConfigDict, Field

from codescent.mcp.server import mcp


class ScanToolPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    ok: bool
    status: str
    findings_created: int = Field(ge=0)
    rule_ids: tuple[str, ...]
    finding_ids: tuple[str, ...]


class MarkToolPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    ok: bool
    finding_id: str
    status: str


class FindingDetailPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    ok: bool
    finding_id: str
    evidence: dict[str, str | int | float | bool | None]
    status_history: tuple[dict[str, str | int | float | bool | None], ...]
    score_inputs: dict[str, str | int | float | bool | None]


class ScoreExplanationPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    ok: bool
    finding_id: str
    score_inputs: dict[str, str | int | float | bool | None]
    reasons: tuple[str, ...]
    next_steps: tuple[str, ...]
    subjective: bool


class ChangedFileHealthPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    ok: bool
    path: str
    risk_score: float = Field(ge=0, le=1)
    risk_level: str
    finding_ids: tuple[str, ...]
    suggested_tests: tuple[str, ...]
    recommended_commands: tuple[str, ...]
    risk_notes: tuple[str, ...]


class DiffRiskPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    ok: bool
    changed_files: tuple[str, ...]
    risk_score: float = Field(ge=0, le=1)
    risk_level: str
    findings: tuple[dict[str, str | float], ...]
    suggested_tests: tuple[str, ...]
    recommended_commands: tuple[str, ...]


@pytest.mark.anyio
async def test_finding_tools_are_source_read_only(tmp_path: Path) -> None:
    repo = _repo_with_todo(tmp_path)
    before = source_snapshot(repo)

    async with Client(mcp) as client:
        tools = await client.list_tools()
        scan_result = await client.call_tool(
            "scan_code_health",
            {"repo": str(repo)},
        )
        report_result = await client.call_tool(
            "get_smell_report",
            {"repo": str(repo)},
        )
        next_result = await client.call_tool(
            "get_next_improvement",
            {"repo": str(repo)},
        )

    tool_names = {tool.name for tool in tools}
    assert {
        "scan_code_health",
        "get_smell_report",
        "get_next_improvement",
        "get_backlog",
        "get_progress",
        "get_regressions",
        "mark_finding",
        "rescan",
    } <= tool_names
    assert source_snapshot(repo) == before

    scan_payload = ScanToolPayload.model_validate_json(
        _text_content(scan_result.content),
    )
    assert scan_payload.ok is True
    assert scan_payload.findings_created >= 2
    assert "python.todo_cluster" in scan_payload.rule_ids
    assert "finding_id" in _text_content(report_result.content)
    assert "finding_id" in _text_content(next_result.content)

    async with Client(mcp) as client:
        mark_result = await client.call_tool(
            "mark_finding",
            {
                "repo": str(repo),
                "finding_id": scan_payload.finding_ids[0],
                "status": "in_progress",
            },
        )
        detail_result = await client.call_tool(
            "get_finding",
            {
                "repo": str(repo),
                "finding_id": scan_payload.finding_ids[0],
            },
        )
        rescan_result = await client.call_tool("rescan", {"repo": str(repo)})

    mark_payload = MarkToolPayload.model_validate_json(
        _text_content(mark_result.content),
    )
    detail_payload = FindingDetailPayload.model_validate_json(
        _text_content(detail_result.content),
    )
    rescan_payload = ScanToolPayload.model_validate_json(
        _text_content(rescan_result.content),
    )
    assert mark_payload.ok is True
    assert mark_payload.status == "in_progress"
    assert detail_payload.ok is True
    assert detail_payload.finding_id == scan_payload.finding_ids[0]
    assert detail_payload.evidence
    assert detail_payload.status_history[-1]["event_type"] == "status_changed"
    assert detail_payload.score_inputs["confidence"]
    assert rescan_payload.ok is True
    assert source_snapshot(repo) == before


@pytest.mark.anyio
async def test_explain_score_returns_deterministic_ranking_reasons(
    tmp_path: Path,
) -> None:
    repo = _repo_with_todo(tmp_path)
    scan_result = await _scan_repo(repo)
    finding_id = scan_result.finding_ids[0]

    async with Client(mcp) as client:
        result = await client.call_tool(
            "explain_score",
            {"repo": str(repo), "finding_id": finding_id},
        )

    explanation = ScoreExplanationPayload.model_validate_json(
        _text_content(result.content),
    )

    assert explanation.ok is True
    assert explanation.finding_id == finding_id
    assert explanation.score_inputs["confidence"]
    assert any("severity" in reason for reason in explanation.reasons)
    assert explanation.next_steps
    assert explanation.subjective is False


@pytest.mark.anyio
async def test_diff_risk_tools_report_changed_file_health_locally(
    tmp_path: Path,
) -> None:
    repo = _repo_with_todo(tmp_path)
    before = source_snapshot(repo)

    async with Client(mcp) as client:
        tools = await client.list_tools()
        _ = await client.call_tool("scan_code_health", {"repo": str(repo)})
        source = repo / "src" / "pkg" / "config.py"
        _ = source.write_text(source.read_text() + "\nRISK_SENTINEL = True\n")
        risk_result = await client.call_tool("review_diff_risk", {"repo": str(repo)})
        health_result = await client.call_tool(
            "get_changed_file_health",
            {"repo": str(repo), "path": "src/pkg/config.py"},
        )
        unchanged_result = await client.call_tool(
            "get_changed_file_health",
            {"repo": str(repo), "path": "tests/test_config.py"},
        )

    tool_names = {tool.name for tool in tools}
    assert {"review_diff_risk", "get_changed_file_health"} <= tool_names

    risk = DiffRiskPayload.model_validate_json(_text_content(risk_result.content))
    health = ChangedFileHealthPayload.model_validate_json(
        _text_content(health_result.content),
    )
    unchanged = ChangedFileHealthPayload.model_validate_json(
        _text_content(unchanged_result.content),
    )

    assert risk.ok is True
    assert risk.changed_files == ("src/pkg/config.py",)
    assert 0 < risk.risk_score <= 1
    assert risk.risk_level in {"low", "medium", "high"}
    assert risk.findings
    assert all("source_content" not in finding for finding in risk.findings)
    assert "tests/test_config.py" in risk.suggested_tests
    assert "pytest tests/test_config.py" in risk.recommended_commands
    assert health.ok is True
    assert health.path == "src/pkg/config.py"
    assert health.finding_ids
    assert health.suggested_tests == ("tests/test_config.py",)
    assert health.recommended_commands == ("pytest tests/test_config.py",)
    assert any("changed" in note for note in health.risk_notes)
    assert unchanged.ok is False
    assert any("not currently changed" in note for note in unchanged.risk_notes)
    assert source_snapshot(repo)["src/pkg/config.py"].endswith(
        "RISK_SENTINEL = True\n",
    )
    assert before["src/pkg/config.py"] in source_snapshot(repo)["src/pkg/config.py"]


async def _scan_repo(repo: Path) -> ScanToolPayload:
    async with Client(mcp) as client:
        scan_result = await client.call_tool(
            "scan_code_health",
            {"repo": str(repo)},
        )
    return ScanToolPayload.model_validate_json(_text_content(scan_result.content))


def source_snapshot(repo: Path) -> dict[str, str]:
    return {
        path.relative_to(repo).as_posix(): path.read_text()
        for path in repo.rglob("*.py")
        if ".codescent" not in path.parts
    }


def _repo_with_todo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    source = repo / "src" / "pkg" / "config.py"
    test = repo / "tests" / "test_config.py"
    source.parent.mkdir(parents=True)
    test.parent.mkdir(parents=True)
    _ = source.write_text(
        """STATUS = "pending-review"
OTHER_STATUS = "pending-review"
THIRD_STATUS = "pending-review"


def load_config() -> str:
    # TODO: split config
    # FIXME: preserve compatibility
    # HACK: keep old queue name
    return STATUS
""",
    )
    _ = test.write_text(
        """from pkg.config import load_config


def test_load_config() -> None:
    assert load_config() == "pending-review"
""",
    )
    return repo


def _text_content(content: list[ContentBlock]) -> str:
    assert len(content) == 1
    first = content[0]
    assert isinstance(first, TextContent)
    return first.text
