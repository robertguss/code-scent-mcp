import json
import subprocess
from pathlib import Path

import pytest

from codescent.evals import (
    EvalOutput,
    ExpectedFinding,
    ExpectedManifest,
    generate_scale_fixture,
    run_deterministic_eval,
)


def test_eval_scores_fixture_workflow(tmp_path: Path) -> None:
    out = tmp_path / "eval.json"

    result = run_deterministic_eval(
        repo=Path("tests/fixtures/python-basic"),
        expected=Path("evals/fixtures/python-basic.expected.json"),
        out=out,
    )
    payload = EvalOutput.model_validate_json(out.read_text())

    assert result.passed is True
    assert result.score >= 0.9
    assert payload.metrics["finding_precision"] == 1.0
    assert payload.metrics["source_read_only"] == 1.0
    assert payload.workflow.success is True


def test_ts_react_next_pack_meets_expected_eval_thresholds(tmp_path: Path) -> None:
    out = tmp_path / "ts-eval.json"

    result = run_deterministic_eval(
        repo=Path("tests/fixtures/ts-react-next-basic"),
        expected=Path("evals/fixtures/ts-react-next.expected.json"),
        out=out,
    )
    payload = EvalOutput.model_validate_json(out.read_text())

    assert result.passed is True
    assert result.score >= 0.9
    assert payload.metrics["finding_precision"] == 1.0
    assert payload.metrics["source_read_only"] == 1.0
    assert payload.workflow.success is True


def test_eval_fails_on_missing_expected_finding(tmp_path: Path) -> None:
    expected = tmp_path / "expected.json"
    source = ExpectedManifest.model_validate_json(
        Path("evals/fixtures/python-basic.expected.json").read_text(),
    )
    missing = ExpectedFinding(
        id="MISSING",
        rule_id="python.not_real",
        file="src/acme_tasks/config.py",
    )
    modified = source.model_copy(update={"findings": (*source.findings, missing)})
    _ = expected.write_text(modified.model_dump_json())

    result = run_deterministic_eval(
        repo=Path("tests/fixtures/python-basic"),
        expected=expected,
        out=tmp_path / "eval.json",
    )

    assert result.passed is False
    assert result.metrics["finding_precision"] < 1.0


def test_eval_fails_on_unexpected_actual_finding(tmp_path: Path) -> None:
    expected = tmp_path / "expected.json"
    source = ExpectedManifest.model_validate_json(
        Path("evals/fixtures/python-basic.expected.json").read_text(),
    )
    modified = source.model_copy(update={"findings": source.findings[:-1]})
    _ = expected.write_text(modified.model_dump_json())

    result = run_deterministic_eval(
        repo=Path("tests/fixtures/python-basic"),
        expected=expected,
        out=tmp_path / "eval.json",
    )

    assert result.passed is False
    assert result.metrics["finding_precision"] < 1.0


def test_eval_rejects_wrong_fixture_root(tmp_path: Path) -> None:
    expected = tmp_path / "expected.json"
    source = ExpectedManifest.model_validate_json(
        Path("evals/fixtures/python-basic.expected.json").read_text(),
    )
    _ = expected.write_text(
        source.model_copy(update={"fixture_root": "different"}).model_dump_json()
    )

    with pytest.raises(ValueError, match="fixture_root"):
        _ = run_deterministic_eval(
            repo=Path("tests/fixtures/python-basic"),
            expected=expected,
            out=tmp_path / "eval.json",
        )


def test_eval_scores_generated_scale_fixture(tmp_path: Path) -> None:
    repo, expected = generate_scale_fixture(
        source_repo=Path("tests/fixtures/python-basic"),
        source_manifest=Path("evals/fixtures/python-basic.expected.json"),
        output_root=tmp_path,
        module_count=8,
    )
    out = tmp_path / "scale-eval.json"

    result = run_deterministic_eval(repo=repo, expected=expected, out=out)
    payload = EvalOutput.model_validate_json(out.read_text())

    assert result.passed is True
    assert payload.metrics["source_read_only"] == 1.0
    assert (repo / "src" / "scale_generated" / "module_007.py").is_file()


def test_eval_cli_exits_nonzero_on_failed_score(tmp_path: Path) -> None:
    expected = tmp_path / "expected.json"
    source = ExpectedManifest.model_validate_json(
        Path("evals/fixtures/python-basic.expected.json").read_text(),
    )
    missing = ExpectedFinding(
        id="MISSING",
        rule_id="python.not_real",
        file="src/acme_tasks/config.py",
    )
    modified = source.model_copy(update={"findings": (*source.findings, missing)})
    _ = expected.write_text(modified.model_dump_json())

    completed = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "evals/run_deterministic.py",
            "--repo",
            "tests/fixtures/python-basic",
            "--expected",
            expected.as_posix(),
            "--out",
            (tmp_path / "eval.json").as_posix(),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    assert json.loads(completed.stdout)["passed"] is False
