from pathlib import Path

from codescent.services.code_health import CodeHealthService

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "ts-react-next-basic"


def test_ts_react_next_rules_find_expected_fixture_smells_with_evidence() -> None:
    result = CodeHealthService(FIXTURE_ROOT).scan()
    by_rule = {finding.rule_id: finding for finding in result.findings}

    expected_rules = {
        "typescript.large_component",
        "react.too_many_hooks",
        "next.route_handler_too_much",
        "typescript.missing_nearby_test",
    }

    assert expected_rules <= set(by_rule)
    assert by_rule["typescript.large_component"].file_path == (
        "components/task-list.tsx"
    )
    assert by_rule["react.too_many_hooks"].evidence["hook_count"] == 2
    assert by_rule["next.route_handler_too_much"].symbol == "app.api.tasks.route.GET"
    missing_test_targets = {
        finding.evidence["expected_test"]
        for finding in result.findings
        if finding.rule_id == "typescript.missing_nearby_test"
    }
    assert "tests/task-card.test.jsx" in missing_test_targets
    assert all(finding.evidence for finding in by_rule.values())
