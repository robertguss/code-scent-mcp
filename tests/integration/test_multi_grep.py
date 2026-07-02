"""One-pass multi-pattern literal grep (plan unit U10 / bead P2.3).

Trace MANY identifiers in a single sweep: ``multi_grep`` finds every line
matching ANY literal pattern in one pass, and ``multi_search_content`` routes
its matching through it. The pyahocorasick automaton tier is the live path in
the dev/CI env (the accelerator is installed via the dev group); forcing the
factory to ``None`` proves the native fallback yields the IDENTICAL match set,
so the base install (no pyahocorasick) still works.
"""

from __future__ import annotations

import importlib.util
from typing import TYPE_CHECKING, cast

import codescent.engine.search.multi_grep as multi_grep_module
from codescent.engine.search.multi_grep import MultiMatcher, multi_grep
from codescent.services.search import SearchService

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    import pytest

FIXTURE = "tests/fixtures/python-basic"

# Smart-case fixtures shared by the automaton/native parity checks: an
# all-lowercase pattern matches case-insensitively, an upper-bearing one
# case-sensitively, and "load" / "load_export" overlap on the same line.
_LINES = ("def load_export(rows):", "    return Builder()", "value = load")
_PATTERNS = ("load", "load_export", "Builder", "absent")
_EXPECTED = {
    "load": (0, 2),
    "load_export": (0,),
    "Builder": (1,),
    "absent": (),
}


def _write(repo: Path, relative: str, text: str) -> None:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(text)


def test_one_call_traces_many_identifiers_across_files() -> None:
    patterns = (
        "build_daily_plan",
        "summarize_payroll_run",
        "save_plan",
        "load_config",
        "render_priority_report",
        "load_export_rows",
        "LegacyExportMapper",
        "export_field_names",
    )

    results = SearchService(FIXTURE).multi_search_content(patterns, limit=20)
    paths = tuple(result["path"] for result in results)

    expected_files = {
        "src/acme_tasks/workflow.py",
        "src/acme_tasks/cli.py",
        "src/acme_tasks/payroll.py",
        "src/acme_tasks/storage.py",
        "src/acme_tasks/config.py",
        "src/acme_tasks/report.py",
        "src/acme_tasks/oversized.py",
    }
    # One call: every file where ANY of the eight literals matches is present.
    assert expected_files <= set(paths)
    # Deduped by file: a file matching several patterns appears exactly once.
    assert len(paths) == len(set(paths))


def test_results_are_bounded_and_deduped_by_file(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    for index in range(12):
        _write(
            repo,
            f"src/mod_{index:02d}.py",
            "alpha_token = 1\nbeta_token = 2\ngamma_token = 3\n",
        )
    patterns = ("alpha_token", "beta_token", "gamma_token")

    results = SearchService(repo).multi_search_content(patterns, limit=5)
    paths = tuple(result["path"] for result in results)

    assert len(results) == 5  # cap respected even though 12 files match.
    assert len(paths) == len(set(paths))  # deduped by file.
    # A single file matched all three patterns -> one entry carrying all reasons.
    sample = results[0]
    assert "query:alpha_token" in sample["reasons"]
    assert "query:beta_token" in sample["reasons"]
    assert "query:gamma_token" in sample["reasons"]


def test_pyahocorasick_tier_is_used_and_correct() -> None:
    # The dev/CI env installs pyahocorasick, so the automaton tier is the live
    # path here -- this asserts that path is exercised and returns correct hits.
    assert importlib.util.find_spec("ahocorasick") is not None

    assert multi_grep(_PATTERNS, _LINES) == _EXPECTED


def test_matcher_compiles_automaton_once_across_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # dzte: the automaton is built once per query (at MultiMatcher construction),
    # not once per scanned file. Count constructions to prove scans reuse it.
    import ahocorasick  # noqa: PLC0415

    built = 0
    real_constructor = cast("Callable[[], object]", ahocorasick.Automaton)

    def counting_factory() -> Callable[[], object]:
        def make() -> object:
            nonlocal built
            built += 1
            return real_constructor()

        return make

    monkeypatch.setattr(multi_grep_module, "_automaton_factory", counting_factory)

    matcher = MultiMatcher(_PATTERNS)  # compiles sensitive + insensitive automatons
    built_after_compile = built
    assert built_after_compile == 2

    for _ in range(3):
        assert matcher.scan(_LINES) == _EXPECTED
    # Three scans built no further automatons: construction is per query, not file.
    assert built == built_after_compile


def test_native_fallback_matches_automaton_tier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    automaton_result = multi_grep(_PATTERNS, _LINES)

    # Force pyahocorasick "unavailable" so the native single-scan tier runs.
    monkeypatch.setattr(multi_grep_module, "_automaton_factory", lambda: None)
    native_result = multi_grep(_PATTERNS, _LINES)

    assert native_result == _EXPECTED
    assert native_result == automaton_result


def test_empty_pattern_list_is_bounded_empty(tmp_path: Path) -> None:
    assert multi_grep((), ("anything", "here")) == {}

    repo = tmp_path / "repo"
    _write(repo, "src/module.py", "value = 1\n")
    assert SearchService(repo).multi_search_content((), limit=5) == ()


def test_overlapping_patterns_dedupe_by_file(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(repo, "src/loader.py", "def load_export():\n    return load()\n")

    results = SearchService(repo).multi_search_content(
        ("load", "load_export"),
        limit=10,
    )
    paths = tuple(result["path"] for result in results)

    assert paths == ("src/loader.py",)  # overlapping literals -> single entry.
    assert "query:load" in results[0]["reasons"]
    assert "query:load_export" in results[0]["reasons"]
