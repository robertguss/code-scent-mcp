from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import scripts.dogfood_scan as dogfood
from pydantic import TypeAdapter

from codescent.engine.rules.model import FindingSpec, build_finding
from codescent.smoke.lx_data_lake_contract import JsonValue

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PAYLOAD = TypeAdapter(dict[str, JsonValue])


def test_dogfood_gate_passes_on_clean_tree(tmp_path: Path) -> None:
    out = tmp_path / "dogfood.json"

    result = subprocess.run(
        [sys.executable, "scripts/dogfood_scan.py", "--out", str(out)],
        cwd=_REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = _PAYLOAD.validate_json(result.stdout)
    assert payload["ok"] is True
    assert payload["violation_count"] == 0


def test_dogfood_gate_fails_when_findings_are_not_allowlisted(tmp_path: Path) -> None:
    empty_allowlist = tmp_path / "empty.json"
    _ = empty_allowlist.write_text(json.dumps({"findings": {}}))

    payload = dogfood.dogfood_scan(
        repo=_REPO_ROOT,
        allowlist_path=empty_allowlist,
        out=tmp_path / "scan.json",
    )

    gated_findings = payload["gated_findings"]
    assert payload["ok"] is False
    assert isinstance(gated_findings, int)
    assert gated_findings > 0
    assert payload["violation_count"] == gated_findings
    assert payload["network_attempts"] == 0


def test_compute_violations_flags_only_unknown_keys() -> None:
    finding = build_finding(
        FindingSpec(
            rule_id="python.large_function",
            title="Large function",
            message="synthetic",
            file_path="synthetic.py",
            symbol="synthetic.fn",
            severity="warning",
            confidence=0.9,
            evidence={"line_count": 999},
            suggested_action="split",
        ),
    )

    assert dogfood.compute_violations([finding], set()) == [finding]
    assert dogfood.compute_violations([finding], {finding.stable_key}) == []
