from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from pydantic import BaseModel, ConfigDict

from codescent.services.code_health import CodeHealthService

if TYPE_CHECKING:
    from codescent.engine.rules.model import CodeHealthFinding

CYCLE_FIXTURE = Path("tests/fixtures/python-import-cycle")
ACYCLIC_FIXTURE = Path("tests/fixtures/python-basic")
EXPECTED = Path("evals/fixtures/python-import-cycle.expected.json")
IMPORT_CYCLE_RULE_ID = "python.import_cycle"


class _ExpectedCycle(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    file: str
    severity: str
    cycle_size: int
    cycle_members: str
    cycle_path: str


class _ExpectedCycles(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    fixture_root: str
    rule_id: str
    findings: tuple[_ExpectedCycle, ...]


def _scan_copy(source: Path, tmp_path: Path) -> CodeHealthService:
    repo = tmp_path / "repo"
    _ = shutil.copytree(source, repo)
    shutil.rmtree(repo / ".codescent", ignore_errors=True)
    return CodeHealthService(repo)


def _cycle_findings(
    findings: tuple[CodeHealthFinding, ...],
) -> list[CodeHealthFinding]:
    return [finding for finding in findings if finding.rule_id == IMPORT_CYCLE_RULE_ID]


def test_cycle_fixture_matches_expected_finding(tmp_path: Path) -> None:
    expectation = _ExpectedCycles.model_validate_json(EXPECTED.read_text())

    scan = _scan_copy(CYCLE_FIXTURE, tmp_path).scan()
    cycle_findings = _cycle_findings(scan.findings)

    assert len(cycle_findings) == len(expectation.findings)
    for finding, expected in zip(cycle_findings, expectation.findings, strict=True):
        assert finding.file_path == expected.file
        assert finding.severity == expected.severity
        assert finding.evidence["cycle_size"] == expected.cycle_size
        assert finding.evidence["cycle_members"] == expected.cycle_members
        assert finding.evidence["cycle_path"] == expected.cycle_path


def test_cycle_fixture_finding_ids_are_stable_and_deterministic(
    tmp_path: Path,
) -> None:
    first = _scan_copy(CYCLE_FIXTURE, tmp_path / "a").scan()
    second = _scan_copy(CYCLE_FIXTURE, tmp_path / "b").scan()

    first_ids = tuple(finding.id for finding in _cycle_findings(first.findings))
    second_ids = tuple(finding.id for finding in _cycle_findings(second.findings))

    assert first_ids == second_ids
    assert all(":" in finding_id for finding_id in first_ids)


def test_acyclic_fixture_stays_clean(tmp_path: Path) -> None:
    scan = _scan_copy(ACYCLIC_FIXTURE, tmp_path).scan()

    assert _cycle_findings(scan.findings) == []
