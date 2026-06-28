from __future__ import annotations

import json

from codescent.core.models import FindingStatus
from codescent.engine.rules.model import (
    CONFIDENCE_TIER_HEURISTIC,
    CONFIDENCE_TIER_VERIFIED,
    FindingSpec,
    build_finding,
)
from codescent.mcp.finding_payloads import (
    decode_provenance,
    finding_payload,
    scan_finding_item,
)
from codescent.services.risk import RiskFinding, rank_findings
from codescent.storage.repositories import FindingRow


def _spec(rule_id: str, symbol: str | None) -> FindingSpec:
    return FindingSpec(
        rule_id=rule_id,
        title="t",
        message="m",
        file_path="src/pkg/a.py",
        symbol=symbol,
        severity="warning",
        confidence=0.9,
        evidence={"count": 1},
        suggested_action="a",
    )


def test_python_resolved_finding_is_verified() -> None:
    finding = build_finding(_spec("python.large_function", "pkg.a.build"))

    assert finding.confidence_tier == CONFIDENCE_TIER_VERIFIED
    assert finding.provenance == {
        "rule_id": "python.large_function",
        "language": "python",
        "resolution": "ast",
        "symbol_resolved": True,
    }


def test_regex_ts_finding_is_heuristic() -> None:
    # Even with a (regex-resolved) symbol, a TS-pack finding is never verified.
    finding = build_finding(_spec("typescript.large_component", "components.List"))

    assert finding.confidence_tier == CONFIDENCE_TIER_HEURISTIC
    assert finding.provenance["language"] == "typescript"
    assert finding.provenance["resolution"] == "regex"
    assert finding.provenance["symbol_resolved"] is True


def test_python_file_level_finding_is_heuristic() -> None:
    # A symbol-less (file-level) python finding has nothing resolved -> heuristic.
    finding = build_finding(_spec("python.large_file", None))

    assert finding.confidence_tier == CONFIDENCE_TIER_HEURISTIC
    assert finding.provenance["symbol_resolved"] is False
    assert finding.provenance["resolution"] == "ast"


def test_build_finding_honors_explicit_override() -> None:
    spec = _spec("python.large_file", None)
    overridden = FindingSpec(
        rule_id=spec.rule_id,
        title=spec.title,
        message=spec.message,
        file_path=spec.file_path,
        symbol=spec.symbol,
        severity=spec.severity,
        confidence=spec.confidence,
        evidence=spec.evidence,
        suggested_action=spec.suggested_action,
        confidence_tier=CONFIDENCE_TIER_VERIFIED,
    )

    assert build_finding(overridden).confidence_tier == CONFIDENCE_TIER_VERIFIED


def test_tier_and_provenance_are_not_in_stable_key() -> None:
    # Identity must not depend on derived metadata, so a verified and a
    # heuristic-overridden build of the same rule/file/symbol share a stable_key.
    base = _spec("python.large_function", "pkg.a.build")
    heuristic_variant = FindingSpec(
        rule_id=base.rule_id,
        title=base.title,
        message=base.message,
        file_path=base.file_path,
        symbol=base.symbol,
        severity=base.severity,
        confidence=base.confidence,
        evidence=base.evidence,
        suggested_action=base.suggested_action,
        confidence_tier=CONFIDENCE_TIER_HEURISTIC,
    )

    assert build_finding(base).stable_key == build_finding(heuristic_variant).stable_key


def _risk_finding(tier: str, *, severity: str = "warning") -> RiskFinding:
    return RiskFinding(
        finding_id=f"{severity}:{tier}",
        rule_id="python.large_function",
        file_path="src/pkg/a.py",
        severity=severity,
        confidence=0.9,
        confidence_tier=tier,
        status="open",
    )


def test_rank_findings_orders_verified_above_heuristic_at_equal_severity() -> None:
    heuristic = _risk_finding(CONFIDENCE_TIER_HEURISTIC)
    verified = _risk_finding(CONFIDENCE_TIER_VERIFIED)

    ranked = rank_findings((heuristic, verified))

    assert ranked[0] is verified
    assert ranked[1] is heuristic


def test_rank_findings_severity_dominates_tier() -> None:
    error_heuristic = _risk_finding(CONFIDENCE_TIER_HEURISTIC, severity="error")
    warning_verified = _risk_finding(CONFIDENCE_TIER_VERIFIED, severity="warning")

    ranked = rank_findings((warning_verified, error_heuristic))

    assert ranked[0] is error_heuristic


def test_scan_finding_item_carries_tier_and_provenance() -> None:
    item = scan_finding_item(build_finding(_spec("python.large_function", "pkg.a.b")))

    assert item["confidence_tier"] == CONFIDENCE_TIER_VERIFIED
    assert item["provenance"] == {
        "rule_id": "python.large_function",
        "language": "python",
        "resolution": "ast",
        "symbol_resolved": True,
    }


def test_finding_payload_decodes_persisted_provenance() -> None:
    provenance = {
        "rule_id": "typescript.large_component",
        "language": "typescript",
        "resolution": "regex",
        "symbol_resolved": True,
    }
    row = FindingRow(
        id="id1",
        stable_key="sk1",
        rule_id="typescript.large_component",
        file_path="components/list.tsx",
        severity="warning",
        confidence=0.8,
        status=FindingStatus.OPEN,
        title="t",
        message="m",
        evidence_json="{}",
        suggested_action="a",
        events=(),
        confidence_tier=CONFIDENCE_TIER_HEURISTIC,
        provenance_json=json.dumps(provenance),
    )

    item = finding_payload(row)

    assert item["confidence_tier"] == CONFIDENCE_TIER_HEURISTIC
    assert item["provenance"] == provenance


def test_decode_provenance_is_bounded_and_scalar() -> None:
    assert decode_provenance("not json") == {}
    assert decode_provenance("[1, 2]") == {}
    # Non-scalar nested values are dropped to keep the payload bounded.
    assert decode_provenance('{"language": "python", "nested": {"x": 1}}') == {
        "language": "python",
    }
