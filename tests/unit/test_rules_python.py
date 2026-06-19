from pathlib import Path
from textwrap import dedent

from codescent.core.models import MaintainabilityThresholds, ProjectConfig
from codescent.engine.rules.python import scan_python_health

# The fixtures here are deliberately tiny; exercise rule logic at the strict
# (historical) thresholds rather than the laxer production defaults.
STRICT_CONFIG = ProjectConfig(thresholds=MaintainabilityThresholds.strict())


def test_fixture_rules_find_expected_findings() -> None:
    findings = scan_python_health(
        Path("tests/fixtures/python-basic"),
        config=STRICT_CONFIG,
    )
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
    first = scan_python_health(repo, config=STRICT_CONFIG)

    _ = source.write_text(f"\n\n\ndef process() -> None:\n{body}\n")
    second = scan_python_health(repo, config=STRICT_CONFIG)

    first_large = next(
        finding for finding in first if finding.rule_id == "python.large_function"
    )
    second_large = next(
        finding for finding in second if finding.rule_id == "python.large_function"
    )
    assert first_large.stable_key == second_large.stable_key


def test_scan_python_health_includes_structural_duplicate_findings(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _write(
        repo / "src" / "alpha.py",
        """
        def summarize_orders(orders):
            total = 0
            for order in orders:
                if order.active:
                    total += order.amount * 2
            return total
        """,
    )
    _write(
        repo / "src" / "beta.py",
        """
        def build_invoice_lines(records):
            subtotal = 0
            for record in records:
                if record.enabled:
                    subtotal += record.price * 7
            return subtotal
        """,
    )

    findings = scan_python_health(repo)
    duplicate = next(
        finding
        for finding in findings
        if finding.rule_id == "python.structural_near_duplicate"
    )

    assert duplicate.file_path == "src/alpha.py"
    assert duplicate.symbol == "summarize_orders"
    assert duplicate.evidence["count"] == 2
    assert duplicate.evidence["locations"] == (
        "src/alpha.py:2-7:summarize_orders; src/beta.py:2-7:build_invoice_lines"
    )


def _write(path: Path, source: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(dedent(source))
