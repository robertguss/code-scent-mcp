"""Tests for the U10 per-rule eval-precision harness + CI gate.

`pythonpath = ["."]` (pyproject pytest config) makes the top-level ``evals``
package importable here.
"""

import subprocess
from pathlib import Path

from evals.precision_harness import (
    DEFAULT_BASELINES_PATH,
    CorpusLabels,
    PrecisionBaselines,
    RuleLabels,
    check_regression,
    compute_precision,
    load_baselines,
    load_labels,
    precision_from_labels,
)

ROOT = Path(__file__).resolve().parents[2]


def _labels(**rules: RuleLabels) -> CorpusLabels:
    return CorpusLabels(corpus_root="x", rules=dict(rules))


def test_precision_math_tiny_corpus() -> None:
    labels = _labels(rule=RuleLabels(smelly=("s.py",), clean=("c.py",)))

    perfect = precision_from_labels(labels, {("rule", "s.py")})
    assert perfect.precision_map() == {"rule": 1.0}
    assert perfect.rules[0].true_positives == 1
    assert perfect.rules[0].false_positives == 0
    assert perfect.rules[0].missed_smelly == ()

    half = precision_from_labels(labels, {("rule", "s.py"), ("rule", "c.py")})
    assert half.precision_map() == {"rule": 0.5}
    assert half.rules[0].true_positives == 1
    assert half.rules[0].false_positives == 1

    vacuous = precision_from_labels(labels, set())
    assert vacuous.precision_map() == {"rule": 1.0}
    assert vacuous.rules[0].true_positives == 0
    assert vacuous.rules[0].missed_smelly == ("s.py",)


def test_unlabeled_rules_are_reported_as_gaps() -> None:
    labels = _labels(rule=RuleLabels(smelly=("s.py",), clean=("c.py",)))
    report = precision_from_labels(labels, {("rule", "s.py"), ("other.rule", "z.py")})
    assert report.unlabeled_rule_ids == ("other.rule",)


def test_gate_detects_simulated_precision_drop() -> None:
    labels = _labels(rule=RuleLabels(smelly=("s.py",), clean=("c.py",)))
    dropped = precision_from_labels(labels, {("rule", "s.py"), ("rule", "c.py")})  # 0.5

    regressions = check_regression(dropped, {"rule": 1.0})
    assert len(regressions) == 1
    assert regressions[0].rule_id == "rule"
    assert regressions[0].measured == 0.5
    assert regressions[0].baseline == 1.0


def test_gate_passes_when_no_drop() -> None:
    labels = _labels(rule=RuleLabels(smelly=("s.py",), clean=("c.py",)))
    healthy = precision_from_labels(labels, {("rule", "s.py")})  # 1.0
    assert check_regression(healthy, {"rule": 1.0}) == ()


def test_gate_flags_vanished_rule() -> None:
    labels = _labels(rule=RuleLabels(smelly=("s.py",), clean=("c.py",)))
    report = precision_from_labels(labels, {("rule", "s.py")})
    regressions = check_regression(report, {"deleted.rule": 1.0})
    assert [r.rule_id for r in regressions] == ["deleted.rule"]
    assert regressions[0].measured == 0.0


def test_baselines_file_is_inspectable_and_consistent() -> None:
    baselines = load_baselines(DEFAULT_BASELINES_PATH)
    labels = load_labels()

    assert baselines  # non-empty
    assert all(0.0 <= value <= 1.0 for value in baselines.values())
    # Every baseline corresponds to a labeled rule (no stale entries).
    assert set(baselines) <= set(labels.rules)

    # The on-disk shape parses into the typed model (inspectable JSON contract).
    parsed = PrecisionBaselines.model_validate_json(DEFAULT_BASELINES_PATH.read_text())
    assert parsed.baselines == baselines


def test_seeded_corpus_meets_recorded_baselines() -> None:
    report = compute_precision()
    measured = report.precision_map()
    baselines = load_baselines(DEFAULT_BASELINES_PATH)

    assert set(measured) == set(baselines)
    assert check_regression(report, baselines) == ()
    # Every covered rule is currently a clean 1.0 on the seeded corpus.
    assert all(value == 1.0 for value in measured.values())


def test_smelly_fixtures_stay_smelly() -> None:
    """Each intentionally-smelly fixture must keep triggering its rule (AGENTS.md)."""
    report = compute_precision()
    for rule in report.rules:
        assert rule.true_positives == rule.smelly_total, rule.rule_id
        assert rule.missed_smelly == (), rule.rule_id


def test_cli_check_passes_on_seeded_corpus() -> None:
    completed = subprocess.run(
        ["uv", "run", "python", "evals/run_precision.py", "--check"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    # Substring checks keep the assertions free of `Any` (json.loads -> Any).
    assert '"passed": true' in completed.stdout
    assert '"regressions": []' in completed.stdout


def test_cli_check_fails_on_simulated_precision_drop(tmp_path: Path) -> None:
    # Simulate a real precision drop: relabel a clean fixture that the rule
    # actually fires on, turning a true negative into a false positive.
    labels = load_labels()
    dropped_rule = "python.missing_nearby_test"
    rules = dict(labels.rules)
    rules[dropped_rule] = RuleLabels(
        smelly=rules[dropped_rule].smelly,
        clean=("pkg/tidy.py",),  # tidy.py *does* trigger missing_nearby_test -> FP
    )
    tampered = labels.model_copy(update={"rules": rules})
    labels_path = tmp_path / "labels.json"
    _ = labels_path.write_text(tampered.model_dump_json())

    completed = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "evals/run_precision.py",
            "--check",
            "--labels",
            labels_path.as_posix(),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 1, completed.stdout
    assert '"passed": false' in completed.stdout
    assert dropped_rule in completed.stdout
