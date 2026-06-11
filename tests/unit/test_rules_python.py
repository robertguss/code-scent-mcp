from pathlib import Path

from codescent.engine.rules.python import scan_python_health


def test_fixture_rules_find_expected_findings() -> None:
    findings = scan_python_health(Path("tests/fixtures/python-basic"))
    by_rule = {finding.rule_id: finding for finding in findings}

    assert set(by_rule) >= {
        "python.large_file",
        "python.large_function",
        "python.large_class",
        "python.too_many_imports",
        "python.deep_nesting",
        "python.todo_cluster",
        "python.duplicate_literal",
        "python.missing_nearby_test",
        "python.mixed_responsibilities",
        "python.suspicious_slop_candidate",
    }
    assert by_rule["python.large_file"].file_path == "src/acme_tasks/oversized.py"
    assert by_rule["python.large_function"].symbol == (
        "acme_tasks.workflow.build_daily_plan"
    )
    assert by_rule["python.todo_cluster"].evidence["count"] == 3


def test_finding_stable_key_survives_line_shift(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = repo / "src" / "pkg" / "workflow.py"
    source.parent.mkdir(parents=True)
    body = "\n".join(f"    step_{index} = {index}" for index in range(25))
    _ = source.write_text(f"def process() -> None:\n{body}\n")
    first = scan_python_health(repo)

    _ = source.write_text(f"\n\n\ndef process() -> None:\n{body}\n")
    second = scan_python_health(repo)

    first_large = next(
        finding for finding in first if finding.rule_id == "python.large_function"
    )
    second_large = next(
        finding for finding in second if finding.rule_id == "python.large_function"
    )
    assert first_large.stable_key == second_large.stable_key
