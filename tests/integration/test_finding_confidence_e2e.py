from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest
from fastmcp import Client
from mcp.types import ContentBlock, TextContent

from codescent.core.models import MaintainabilityThresholds, ProjectConfig
from codescent.mcp.finding_payloads import INLINE_ITEM_LIMIT
from codescent.mcp.server import mcp
from codescent.services.code_health import CodeHealthService
from codescent.services.config import ConfigService
from codescent.services.risk import RiskFinding, rank_findings

if TYPE_CHECKING:
    from codescent.engine.rules.model import CodeHealthFinding

logger = logging.getLogger(__name__)

# Strict thresholds so the tiny mixed fixture produces a rich finding set.
STRICT_CONFIG = ProjectConfig(thresholds=MaintainabilityThresholds.strict())
TS_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "ts-react-next-basic"

_TS_PREFIXES = ("typescript.", "react.", "next.")


def _mixed_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    # TS half: the known-good regex-pack fixture (without its committed state).
    _ = shutil.copytree(TS_FIXTURE, repo, ignore=shutil.ignore_patterns(".codescent"))
    # Python half: a large function anchored to a resolved AST symbol -> verified.
    py = repo / "src" / "pkg" / "workflow.py"
    py.parent.mkdir(parents=True)
    body = "\n".join(f"    step_{index} = {index}" for index in range(40))
    _ = py.write_text(f"def build_plan() -> int:\n{body}\n    return 0\n")
    ConfigService(repo).save(STRICT_CONFIG)
    return repo


def _text(content: list[ContentBlock]) -> str:
    assert len(content) == 1
    first = content[0]
    assert isinstance(first, TextContent)
    return first.text


def _items(text: str) -> list[dict[str, object]]:
    payload = cast("dict[str, object]", json.loads(text))
    raw_items = payload["items"]
    assert isinstance(raw_items, list)
    items = cast("list[object]", raw_items)
    return [cast("dict[str, object]", item) for item in items if isinstance(item, dict)]


def _as_risk(finding: CodeHealthFinding) -> RiskFinding:
    return RiskFinding(
        finding_id=finding.id,
        rule_id=finding.rule_id,
        file_path=finding.file_path,
        severity=finding.severity,
        confidence=finding.confidence,
        confidence_tier=finding.confidence_tier,
        status="open",
    )


@pytest.mark.anyio
async def test_mixed_scan_tiers_provenance_ranking_and_bounded_payload(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    repo = _mixed_repo(tmp_path)

    findings = CodeHealthService(repo).scan().findings
    rule_ids = sorted({finding.rule_id for finding in findings})
    logger.info("mixed scan produced %d findings: %s", len(findings), rule_ids)

    python_symbol_findings = [
        finding
        for finding in findings
        if finding.rule_id.startswith("python.") and finding.symbol is not None
    ]
    ts_findings = [
        finding for finding in findings if finding.rule_id.startswith(_TS_PREFIXES)
    ]

    assert python_symbol_findings, "expected at least one resolved Python finding"
    assert ts_findings, "expected at least one regex/TS finding"

    # Python AST findings anchored to a symbol are verified; provenance present.
    for finding in python_symbol_findings:
        logger.info("python %s tier=%s", finding.rule_id, finding.confidence_tier)
        assert finding.confidence_tier == "verified"
        assert finding.provenance["language"] == "python"
        assert finding.provenance["resolution"] == "ast"
        assert finding.provenance["symbol_resolved"] is True

    # Regex/TS findings are always heuristic, even when a symbol was matched.
    for finding in ts_findings:
        logger.info("ts %s tier=%s", finding.rule_id, finding.confidence_tier)
        assert finding.confidence_tier == "heuristic"
        assert finding.provenance["language"] == "typescript"
        assert finding.provenance["resolution"] == "regex"

    # Ranking: at equal severity, verified outranks heuristic.
    verified = _as_risk(python_symbol_findings[0])
    heuristic = _as_risk(
        next(
            finding for finding in ts_findings if finding.severity == verified.severity
        ),
    )
    ranked = rank_findings((heuristic, verified))
    logger.info("ranked tiers: %s", [finding.confidence_tier for finding in ranked])
    assert ranked[0].confidence_tier == "verified"

    # MCP payloads expose the fields and stay bounded.
    async with Client(mcp) as client:
        scan_raw = await client.call_tool("scan_code_health", {"repo": str(repo)})
        report_raw = await client.call_tool("get_smell_report", {"repo": str(repo)})

    scan = _items(_text(scan_raw.content))
    report = _items(_text(report_raw.content))

    assert scan
    assert report
    assert len(scan) <= INLINE_ITEM_LIMIT
    assert len(report) <= INLINE_ITEM_LIMIT
    for item in (*scan, *report):
        assert item["confidence_tier"] in {"verified", "heuristic"}
        provenance = item["provenance"]
        assert isinstance(provenance, dict)
        assert set(cast("dict[str, object]", provenance)) == {
            "rule_id",
            "language",
            "resolution",
            "symbol_resolved",
        }
