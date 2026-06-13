from __future__ import annotations

from tests.fixtures.headroom_influence_fixtures import (
    build_symbol_search_fixtures,
    build_test_output_fixtures,
)


def test_symbol_search_fixtures_cover_empty_exact_and_mixed_roles() -> None:
    fixtures = build_symbol_search_fixtures()

    assert fixtures == build_symbol_search_fixtures()

    empty = fixtures["empty"]
    exact_matches = fixtures["large_exact_matches"]
    mixed_matches = fixtures["mixed_definition_reference"]

    assert empty == ()
    assert len(exact_matches) == 24
    assert exact_matches == tuple(
        sorted(
            exact_matches,
            key=lambda result: (
                result["path"],
                result["line"],
                result["name"],
            ),
        )
    )
    assert exact_matches[0]["path"] == "src/acme/pipeline/module_00.py"
    assert exact_matches[-1]["path"] == "src/acme/pipeline/module_05.py"
    assert {result["kind"] for result in exact_matches} >= {
        "function",
        "class",
        "method",
        "variable",
        "module",
    }
    assert {result["role"] for result in mixed_matches} == {"definition", "reference"}
    assert {result["match_type"] for result in mixed_matches} == {"exact", "partial"}
    assert any(result["kind"] == "module" for result in mixed_matches)


def test_pytest_output_fixtures_cover_failure_and_environment_shapes() -> None:
    fixtures = build_test_output_fixtures()

    assert fixtures == build_test_output_fixtures()

    empty = fixtures["empty"]
    failing = fixtures["failing_assertion"]
    traceback = fixtures["traceback_root_cause"]
    environmental = fixtures["environmental_failure"]
    non_utf8_safe = fixtures["non_utf8_safe_text"]
    very_long_single_line = fixtures["very_long_single_line"]

    assert empty["failed_test_names"] == ()
    assert empty["stdout"] == ""
    assert empty["stderr"] == ""
    assert empty["exit_code"] == 0

    assert failing["failed_test_names"] == ("tests/test_numbers.py::test_sum",)
    assert failing["assertion_summary"] == "assert 2 == 3"
    assert failing["traceback_root_cause"] == "assert 2 == 3"
    assert failing["relevant_files"] == (
        "src/numbers.py",
        "tests/test_numbers.py",
    )
    assert failing["rerun_command"] == "pytest tests/test_numbers.py -q"

    assert traceback["failed_test_names"] == ("tests/test_loader.py::test_imports",)
    assert traceback["traceback_root_cause"] == "ValueError: invalid manifest header"
    assert traceback["deterministic"] is True
    assert "Traceback (most recent call last):" in traceback["stderr"]

    assert environmental["deterministic"] is False
    assert environmental["traceback_root_cause"] == (
        "OSError: [Errno 24] Too many open files"
    )

    assert "\ufffd" in non_utf8_safe["stdout"]
    assert non_utf8_safe["assertion_summary"] == (
        "assert decoded_text == 'replacement sentinel'"
    )

    assert "\n" not in very_long_single_line["stdout"]
    assert len(very_long_single_line["stdout"]) == 4096
