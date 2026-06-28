from __future__ import annotations

import shutil
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING

from codescent.core.models import ProjectConfig
from codescent.engine.packs import build_pack_registry
from codescent.services.code_health import CodeHealthService

if TYPE_CHECKING:
    from codescent.engine.rules.model import CodeHealthFinding

FLAWED_FIXTURE = Path("tests/fixtures/test-quality-flawed")
HEALTHY_FIXTURE = Path("tests/fixtures/test-quality-healthy")

TEST_QUALITY_RULE_IDS = frozenset(
    {
        "python.assertion_free_test",
        "python.no_op_test",
        "python.over_mocked_test",
        "python.skipped_test_cluster",
        "typescript.assertion_free_test",
        "typescript.no_op_test",
        "typescript.over_mocked_test",
        "typescript.skipped_test_cluster",
    },
)

EXPECTED_FLAWED_COUNTS = {
    "python.assertion_free_test": 1,
    "python.no_op_test": 2,
    "python.over_mocked_test": 1,
    "python.skipped_test_cluster": 1,
    "typescript.assertion_free_test": 1,
    "typescript.no_op_test": 2,
    "typescript.over_mocked_test": 1,
    "typescript.skipped_test_cluster": 1,
}


def _copy(source: Path, dest: Path) -> Path:
    _ = shutil.copytree(source, dest)
    shutil.rmtree(dest / ".codescent", ignore_errors=True)
    return dest


def _quality_findings(
    findings: tuple[CodeHealthFinding, ...],
) -> list[CodeHealthFinding]:
    return [f for f in findings if f.rule_id in TEST_QUALITY_RULE_IDS]


def test_flawed_fixture_produces_expected_test_quality_findings(
    tmp_path: Path,
) -> None:
    repo = _copy(FLAWED_FIXTURE, tmp_path / "repo")

    findings = _quality_findings(CodeHealthService(repo).scan().findings)
    counts = Counter(f.rule_id for f in findings)

    assert dict(counts) == EXPECTED_FLAWED_COUNTS
    # Every test-quality finding is heuristic with regex/ast provenance present.
    for finding in findings:
        assert finding.confidence_tier == "heuristic"
        assert finding.symbol is None
        assert set(finding.provenance) == {
            "rule_id",
            "language",
            "resolution",
            "symbol_resolved",
        }


def test_flawed_fixture_findings_are_deterministic(tmp_path: Path) -> None:
    first = CodeHealthService(_copy(FLAWED_FIXTURE, tmp_path / "a")).scan()
    second = CodeHealthService(_copy(FLAWED_FIXTURE, tmp_path / "b")).scan()

    first_ids = tuple(f.id for f in _quality_findings(first.findings))
    second_ids = tuple(f.id for f in _quality_findings(second.findings))

    assert first_ids == second_ids
    assert first_ids  # non-empty


def test_healthy_fixture_produces_no_test_quality_findings(tmp_path: Path) -> None:
    repo = _copy(HEALTHY_FIXTURE, tmp_path / "repo")

    findings = _quality_findings(CodeHealthService(repo).scan().findings)

    assert findings == []


def test_scanners_are_registered_in_their_packs(tmp_path: Path) -> None:
    repo = _copy(FLAWED_FIXTURE, tmp_path / "repo")
    registry = build_pack_registry(ProjectConfig())

    rule_ids = {f.rule_id for f in registry.scan_rule_packs(repo)}

    assert rule_ids >= TEST_QUALITY_RULE_IDS
