from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import cast

from typer.testing import CliRunner

from codescent.cli.main import app
from codescent.services.ci import CiService, ci_github_annotations, ci_sarif_document
from tests.sarif_support import validate_sarif

RUNNER = CliRunner()
_FIXTURE = Path("tests/fixtures/python-basic")
_GITHUB_LINE = re.compile(r"^::(error|warning|notice) file=[^,]+,line=\d+::.+$")


def _repo(tmp_path: Path) -> str:
    repo = tmp_path / "repo"
    _ = shutil.copytree(_FIXTURE, repo, ignore=shutil.ignore_patterns(".codescent"))
    return str(repo)


def test_ci_sarif_and_github_e2e_against_fixture(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    # Golden = service-level serialization of the same deterministic scan.
    report = CiService(repo).run(threshold="warn")
    golden_sarif = ci_sarif_document(report)
    golden_github = ci_github_annotations(report)
    print(f"[e2e] fixture findings: expected >0  found={len(report.findings)}")
    assert report.findings

    sarif_result = RUNNER.invoke(
        app,
        ["ci", "--repo", repo, "--format", "sarif", "--threshold", "warn"],
    )
    github_result = RUNNER.invoke(
        app,
        ["ci", "--repo", repo, "--format", "github", "--threshold", "warn"],
    )

    cli_sarif = cast("dict[str, object]", json.loads(sarif_result.output))
    print(f"[e2e] schema-validate SARIF: {len(report.findings)} results")
    validate_sarif(cli_sarif)

    print("[e2e] golden compare: CLI SARIF == service SARIF")
    assert cli_sarif == golden_sarif

    github_lines = github_result.output.strip().splitlines()
    expected_count = len(report.findings)
    found_count = len(github_lines)
    print(f"[e2e] github annotations: expected={expected_count} found={found_count}")
    assert found_count == expected_count
    assert github_result.output.strip() == golden_github.strip()
    for line in github_lines:
        print(f"[e2e] annotation: {line}")
        assert _GITHUB_LINE.fullmatch(line) is not None
