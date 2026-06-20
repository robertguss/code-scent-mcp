from pathlib import Path

from codescent.core.models import MaintainabilityThresholds, ProjectConfig
from codescent.engine.rules.ts_react_next import scan_ts_react_next_health

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "ts-react-next-basic"

# The fixture components are deliberately tiny; exercise rule logic at the
# strict (historical) thresholds rather than the laxer production defaults.
STRICT_CONFIG = ProjectConfig(thresholds=MaintainabilityThresholds.strict())


def test_ts_react_next_rules_find_expected_fixture_smells_with_evidence() -> None:
    findings = scan_ts_react_next_health(FIXTURE_ROOT, config=STRICT_CONFIG)
    by_rule = {finding.rule_id: finding for finding in findings}

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
        for finding in findings
        if finding.rule_id == "typescript.missing_nearby_test"
    }
    assert "tests/task-card.test.jsx" in missing_test_targets
    assert all(finding.evidence for finding in by_rule.values())
