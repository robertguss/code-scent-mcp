from pathlib import Path
from typing import ClassVar

import pytest
from fastmcp import Client
from mcp.types import ContentBlock, TextContent
from pydantic import BaseModel, ConfigDict, Field

from codescent.core.models import MaintainabilityThresholds, ProjectConfig
from codescent.mcp.finding_payloads import INLINE_ITEM_LIMIT
from codescent.mcp.server import mcp
from codescent.services.config import ConfigService
from codescent.services.result_store import MAX_RETRIEVE_LIMIT

# Each inline item now carries confidence_tier + a small provenance object, so a
# capped (<=25 item) preview is a few KB larger than before. Boundedness is still
# enforced by the item-count cap + retrieval handle, not by raw byte size; this
# guard just asserts the preview stays small (a few KB, not the 338 KB dump bug).
MAX_BOUNDED_PAYLOAD_CHARS = 12288
# Tiny fixtures need the strict (historical) thresholds to produce findings.
STRICT_CONFIG = ProjectConfig(thresholds=MaintainabilityThresholds.strict())


class ScanToolPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    ok: bool
    status: str
    findings_created: int = Field(ge=0)
    rule_ids: tuple[str, ...]
    finding_ids: tuple[str, ...]


class CalibrationRuleModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="allow")

    rule_id: str
    base_confidence: float
    adjusted_confidence: float
    calibrated: bool


class CalibrationToolModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="allow")

    ok: bool
    confidence_recalibration: bool
    rules: tuple[CalibrationRuleModel, ...]


class CalibrationBlockModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="allow")

    calibrated: bool


class ScoreExplanationModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="allow")

    finding_id: str
    calibration: CalibrationBlockModel


class ImprovementClusterModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="allow")

    theme: str
    rule_id: str
    scope: str
    size: int
    effort: str
    roi: float
    health_gain: float


class ImprovementPlanPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    ok: bool
    kind: str
    total_clusters: int
    total_findings: int
    clusters: tuple[ImprovementClusterModel, ...]
    returned_count: int
    omitted_count: int


class BoundedScanPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    ok: bool
    total_count: int
    finding_ids: tuple[str, ...]
    items: tuple[dict[str, object], ...]


class BoundedReportPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    ok: bool
    total_count: int
    items: tuple[dict[str, object], ...]
    returned_count: int
    omitted_count: int
    result_id: str | None
    retrieval_available: bool
    retrieval_hints: tuple[str, ...]


class RetrievedItemsPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    items: tuple[dict[str, object], ...]


class MarkToolPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    ok: bool
    finding_id: str
    status: str
    requested_status: str
    gated: bool
    message: str


class RecordVerificationPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    ok: bool
    finding_id: str
    verification_id: int
    command: str
    exit_code: int
    output_summary: str
    output_truncated: bool


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
    assert mark_payload.requested_status == "in_progress"
    assert mark_payload.gated is False
    assert mark_payload.message == ""
    assert detail_payload.ok is True
    assert detail_payload.finding_id == scan_payload.finding_ids[0]
    assert detail_payload.evidence
    assert detail_payload.status_history[-1]["event_type"] == "status_changed"
    assert detail_payload.score_inputs["confidence"]
    assert rescan_payload.ok is True
    assert source_snapshot(repo) == before


@pytest.mark.anyio
async def test_record_verification_tool_records_caller_supplied_result(
    tmp_path: Path,
) -> None:
    repo = _repo_with_todo(tmp_path)
    before = source_snapshot(repo)
    scan_result = await _scan_repo(repo)
    finding_id = scan_result.finding_ids[0]

    async with Client(mcp) as client:
        record_result = await client.call_tool(
            "record_verification",
            {
                "repo": str(repo),
                "finding_id": finding_id,
                "command": "uv run pytest tests/integration/test_findings.py",
                "exit_code": 0,
                "output_summary": "x" * 1100,
            },
        )
        mark_result = await client.call_tool(
            "mark_finding",
            {
                "repo": str(repo),
                "finding_id": finding_id,
                "status": "resolved",
            },
        )

    record_payload = RecordVerificationPayload.model_validate_json(
        _text_content(record_result.content),
    )
    mark_payload = MarkToolPayload.model_validate_json(
        _text_content(mark_result.content),
    )
    assert record_payload.ok is True
    assert record_payload.finding_id == finding_id
    assert record_payload.exit_code == 0
    assert record_payload.output_truncated is True
    assert len(record_payload.output_summary) == 1000
    assert mark_payload.status == "resolved"
    assert mark_payload.gated is False
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
    # A successful health check is ok=True even for an unchanged file (R6); the
    # not-changed status is a note, not a failure signal.
    assert unchanged.ok is True
    assert any("not currently changed" in note for note in unchanged.risk_notes)
    assert source_snapshot(repo)["src/pkg/config.py"].endswith(
        "RISK_SENTINEL = True\n",
    )
    assert before["src/pkg/config.py"] in source_snapshot(repo)["src/pkg/config.py"]


@pytest.mark.anyio
async def test_list_tools_bound_output_and_offer_retrieval(tmp_path: Path) -> None:
    # Regression for docs/ideas/boundedness-bug-fix.md: get_smell_report once
    # returned every finding inline (338 KB on the CodeScent repo) and was
    # rejected by the client. With many findings, the list/aggregate tools must
    # cap inline output and hand back a retrieval handle for the rest.
    file_count = 40
    repo = _repo_with_many_findings(tmp_path, file_count)

    async with Client(mcp) as client:
        scan_raw = await client.call_tool("scan_code_health", {"repo": str(repo)})
        report_raw = await client.call_tool("get_smell_report", {"repo": str(repo)})

    scan_text = _text_content(scan_raw.content)
    report_text = _text_content(report_raw.content)
    scan = BoundedScanPayload.model_validate_json(scan_text)
    report = BoundedReportPayload.model_validate_json(report_text)

    # Inline output is bounded for both the scan and the report.
    assert scan.total_count >= file_count
    assert len(scan.finding_ids) <= INLINE_ITEM_LIMIT
    assert len(scan.items) <= INLINE_ITEM_LIMIT
    assert report.total_count >= file_count
    assert len(report.items) == INLINE_ITEM_LIMIT
    assert report.returned_count == INLINE_ITEM_LIMIT
    assert report.omitted_count == report.total_count - INLINE_ITEM_LIMIT

    # The serialized payloads stay small — the whole point of the fix.
    assert len(scan_text) < MAX_BOUNDED_PAYLOAD_CHARS
    assert len(report_text) < MAX_BOUNDED_PAYLOAD_CHARS

    # Omission must come with a usable retrieval handle.
    assert report.retrieval_available is True
    result_id = report.result_id
    assert result_id is not None
    assert result_id.startswith("ctx_")
    assert report.retrieval_hints

    # Round-trip: the omitted findings are recoverable, not lost. A single
    # retrieve call is itself bounded (MAX_RETRIEVE_LIMIT), so it returns the
    # capped slice but must surface findings beyond the inline preview.
    async with Client(mcp) as client:
        exact_raw = await client.call_tool(
            "retrieve_result",
            {
                "repo": str(repo),
                "result_id": result_id,
                "mode": "exact",
                "limit": MAX_RETRIEVE_LIMIT,
            },
        )
    exact = RetrievedItemsPayload.model_validate_json(_text_content(exact_raw.content))
    assert len(exact.items) == min(report.total_count, MAX_RETRIEVE_LIMIT)
    inline_ids = {item["finding_id"] for item in report.items}
    retrieved_ids = {item["finding_id"] for item in exact.items}
    assert len(retrieved_ids - inline_ids) > 0


@pytest.mark.anyio
async def test_get_calibration_reports_per_rule_signal(tmp_path: Path) -> None:
    repo = _repo_with_many_findings(tmp_path, 4)

    async with Client(mcp) as client:
        tools = await client.list_tools()
        _ = await client.call_tool("scan_code_health", {"repo": str(repo)})
        result = await client.call_tool("get_calibration", {"repo": str(repo)})

    assert "get_calibration" in {tool.name for tool in tools}
    payload = CalibrationToolModel.model_validate_json(_text_content(result.content))
    assert payload.ok is True
    assert payload.confidence_recalibration is True
    # Fresh repo: verdicts are below the sample size, so nothing is calibrated yet
    # and confidence is unchanged (cold start).
    for rule in payload.rules:
        assert rule.calibrated is False
        assert rule.adjusted_confidence == rule.base_confidence


@pytest.mark.anyio
async def test_explain_score_carries_a_calibration_block(tmp_path: Path) -> None:
    repo = _repo_with_many_findings(tmp_path, 4)

    async with Client(mcp) as client:
        scan = await client.call_tool("scan_code_health", {"repo": str(repo)})
        scan_payload = BoundedScanPayload.model_validate_json(
            _text_content(scan.content),
        )
        finding_id = scan_payload.finding_ids[0]
        result = await client.call_tool(
            "explain_score",
            {"repo": str(repo), "finding_id": finding_id},
        )

    payload = ScoreExplanationModel.model_validate_json(_text_content(result.content))
    assert payload.calibration.calibrated is False


@pytest.mark.anyio
async def test_get_improvement_plan_returns_roi_ordered_clusters(
    tmp_path: Path,
) -> None:
    repo = _repo_with_many_findings(tmp_path, 6)

    async with Client(mcp) as client:
        tools = await client.list_tools()
        _ = await client.call_tool("scan_code_health", {"repo": str(repo)})
        plan_result = await client.call_tool(
            "get_improvement_plan",
            {"repo": str(repo)},
        )

    assert "get_improvement_plan" in {tool.name for tool in tools}
    plan = ImprovementPlanPayload.model_validate_json(
        _text_content(plan_result.content),
    )

    assert plan.ok is True
    assert plan.kind == "improvement_plan"
    assert plan.total_clusters >= 1
    assert plan.total_findings > 0
    assert len(plan.clusters) <= INLINE_ITEM_LIMIT
    assert plan.returned_count == len(plan.clusters)
    # Clusters are ROI-ordered and each carries effort/gain estimates.
    rois = [cluster.roi for cluster in plan.clusters]
    assert rois == sorted(rois, reverse=True)
    assert all(cluster.effort in {"S", "M", "L"} for cluster in plan.clusters)
    assert all(cluster.size >= 1 for cluster in plan.clusters)


class ProvenanceModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="allow")

    rule_id: str
    language: str
    resolution: str
    symbol_resolved: bool


class TieredItemModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="allow")

    finding_id: str
    rule_id: str
    confidence_tier: str
    provenance: ProvenanceModel


class TieredListPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    ok: bool
    items: tuple[TieredItemModel, ...]


class TieredDetailPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="allow")

    ok: bool
    finding_id: str
    confidence_tier: str
    provenance: ProvenanceModel


@pytest.mark.anyio
async def test_finding_payloads_expose_confidence_tier_and_provenance(
    tmp_path: Path,
) -> None:
    # The many-findings fixture yields python.large_function findings anchored to
    # a resolved symbol, so at least one finding is `verified`.
    repo = _repo_with_many_findings(tmp_path, 3)

    async with Client(mcp) as client:
        scan_raw = await client.call_tool("scan_code_health", {"repo": str(repo)})
        report_raw = await client.call_tool("get_smell_report", {"repo": str(repo)})
        scan = ScanToolPayload.model_validate_json(_text_content(scan_raw.content))
        detail_raw = await client.call_tool(
            "get_finding",
            {"repo": str(repo), "finding_id": scan.finding_ids[0]},
        )

    scan_items = TieredListPayload.model_validate_json(_text_content(scan_raw.content))
    report_items = TieredListPayload.model_validate_json(
        _text_content(report_raw.content),
    )
    detail = TieredDetailPayload.model_validate_json(_text_content(detail_raw.content))

    assert scan_items.items
    assert report_items.items
    for item in (*scan_items.items, *report_items.items):
        assert item.confidence_tier in {"verified", "heuristic"}
        assert item.provenance.rule_id == item.rule_id
        assert item.provenance.language == "python"
        assert item.provenance.resolution == "ast"
    # A symbol-anchored python finding is verified; the field is not always
    # heuristic.
    assert any(item.confidence_tier == "verified" for item in scan_items.items)
    assert detail.confidence_tier in {"verified", "heuristic"}
    assert detail.provenance.rule_id
    assert detail.provenance.resolution == "ast"


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
    ConfigService(repo).save(STRICT_CONFIG)
    return repo


def _repo_with_many_findings(tmp_path: Path, file_count: int) -> Path:
    repo = tmp_path / "repo"
    package = repo / "src" / "pkg"
    package.mkdir(parents=True)
    body = "\n".join(f"    value_{line} = {line}" for line in range(80))
    for index in range(file_count):
        module = package / f"module_{index}.py"
        _ = module.write_text(f"def build_{index}() -> int:\n{body}\n    return 0\n")
    return repo


def _text_content(content: list[ContentBlock]) -> str:
    assert len(content) == 1
    first = content[0]
    assert isinstance(first, TextContent)
    return first.text
