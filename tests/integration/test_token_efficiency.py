from __future__ import annotations

import json
from pathlib import Path

import pytest

from codescent.core.token_estimate import estimate_tokens
from codescent.evals.token_efficiency import (
    TokenEfficiencyReport,
    build_token_efficiency_report,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path("tests/fixtures/python-basic")
BASELINE_PATH = REPO_ROOT / "evals" / "token_baselines.json"
WIN_SCENARIOS = ("find_symbol", "start_task")


@pytest.mark.parametrize(
    "text",
    [
        "",
        "a",
        "hello world",
        "def load_config(environment: str) -> dict[str, str]:",
        json.dumps({"path": "src/app.py", "score": 100.0, "reasons": ["x"]}),
        "export_" * 40,
    ],
)
def test_estimate_tokens_is_deterministic_and_monotonic(text: str) -> None:
    assert estimate_tokens(text) == estimate_tokens(text)
    for cut in range(len(text) + 1):
        assert estimate_tokens(text[:cut]) <= estimate_tokens(text)


def test_estimate_tokens_empty_is_zero_and_grows() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("x") >= 1
    assert estimate_tokens("a" * 100) > estimate_tokens("a" * 10)


def test_report_schema_and_positive_counts() -> None:
    report = build_token_efficiency_report(FIXTURE)

    assert report.repo == FIXTURE.as_posix()
    assert len(report.scenarios) >= 3

    for scenario in report.scenarios:
        assert scenario.codescent_tokens > 0
        assert scenario.naive_tokens > 0
        assert scenario.delta == scenario.naive_tokens - scenario.codescent_tokens

    assert report.summary.codescent_tokens == sum(
        item.codescent_tokens for item in report.scenarios
    )
    assert report.summary.naive_tokens == sum(
        item.naive_tokens for item in report.scenarios
    )


def test_codescent_beats_naive_for_symbol_and_context() -> None:
    report = build_token_efficiency_report(FIXTURE)
    by_name = {item.scenario: item for item in report.scenarios}

    for name in WIN_SCENARIOS:
        scenario = by_name[name]
        assert scenario.codescent_tokens < scenario.naive_tokens
        assert scenario.delta > 0

    assert report.summary.codescent_tokens < report.summary.naive_tokens


def test_report_is_reproducible() -> None:
    first = build_token_efficiency_report(FIXTURE)
    second = build_token_efficiency_report(FIXTURE)
    assert first == second


def test_committed_baseline_matches_fresh_run() -> None:
    committed = TokenEfficiencyReport.model_validate_json(
        BASELINE_PATH.read_text(encoding="utf-8"),
    )
    fresh = build_token_efficiency_report(FIXTURE)
    assert committed == fresh
