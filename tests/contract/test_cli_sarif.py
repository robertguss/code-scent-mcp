from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import cast

from typer.testing import CliRunner

from codescent.cli.main import app
from tests.sarif_support import validate_sarif

RUNNER = CliRunner()
_FIXTURE = Path("tests/fixtures/python-basic")
_GITHUB_LINE = re.compile(r"^::(error|warning|notice) file=[^,]+,line=\d+::.+$")


def _repo(tmp_path: Path) -> str:
    repo = tmp_path / "repo"
    _ = shutil.copytree(_FIXTURE, repo, ignore=shutil.ignore_patterns(".codescent"))
    return str(repo)


def test_ci_emits_schema_valid_sarif(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    result = RUNNER.invoke(
        app,
        ["ci", "--repo", repo, "--format", "sarif", "--threshold", "warn"],
    )

    document = cast("dict[str, object]", json.loads(result.output))
    validate_sarif(document)
    # The fixture trips findings, so the run carries at least one result.
    assert '"ruleId"' in result.output


def test_ci_emits_github_annotations(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    result = RUNNER.invoke(
        app,
        ["ci", "--repo", repo, "--format", "github", "--threshold", "warn"],
    )

    lines = result.output.strip().splitlines()
    assert lines
    for line in lines:
        assert _GITHUB_LINE.fullmatch(line) is not None


def test_review_diff_emits_sarif_and_github(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    sarif = RUNNER.invoke(app, ["review-diff", "--repo", repo, "--format", "sarif"])
    github = RUNNER.invoke(app, ["review-diff", "--repo", repo, "--format", "github"])

    assert sarif.exit_code == 0
    validate_sarif(cast("dict[str, object]", json.loads(sarif.output)))
    assert github.exit_code == 0
    for line in github.output.strip().splitlines():
        assert _GITHUB_LINE.fullmatch(line) is not None


def test_existing_json_format_unchanged(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    result = RUNNER.invoke(
        app,
        ["ci", "--repo", repo, "--format", "json", "--threshold", "warn"],
    )

    payload = cast("dict[str, object]", json.loads(result.output))
    assert "risk_level" in payload
    assert "ruleId" not in result.output


def test_invalid_format_is_rejected(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    result = RUNNER.invoke(app, ["ci", "--repo", repo, "--format", "xml"])

    assert result.exit_code != 0
