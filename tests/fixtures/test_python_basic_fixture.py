from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "python-basic"
EXPECTED_MANIFEST = ROOT / "evals" / "fixtures" / "python-basic.expected.json"


class ExpectedFinding(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    id: str


class ExpectedContextLimits(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    default_source_line_cap: int
    max_source_line_cap: int


class ExpectedManifest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    fixture_root: str
    files: tuple[str, ...]
    findings: tuple[ExpectedFinding, ...]
    context_limits: ExpectedContextLimits


def test_fixture_contains_expected_smells() -> None:
    assert FIXTURE_ROOT.is_dir()
    assert EXPECTED_MANIFEST.is_file()

    source_files = sorted(FIXTURE_ROOT.rglob("*.py"))
    test_files = sorted((FIXTURE_ROOT / "tests").rglob("test_*.py"))

    assert len(source_files) >= 5
    assert len(test_files) >= 3

    manifest = ExpectedManifest.model_validate_json(EXPECTED_MANIFEST.read_text())
    finding_ids = {finding.id for finding in manifest.findings}
    expected_ids = {
        "PYBASIC-LARGE-FUNCTION",
        "PYBASIC-LARGE-FILE",
        "PYBASIC-TODO-CLUSTER",
        "PYBASIC-DUPLICATE-LITERAL",
        "PYBASIC-MISSING-TEST",
    }

    assert expected_ids <= finding_ids
    assert manifest.fixture_root == "tests/fixtures/python-basic"
    assert len(manifest.files) >= 5
    assert manifest.context_limits.default_source_line_cap == 80
    assert manifest.context_limits.max_source_line_cap == 200
