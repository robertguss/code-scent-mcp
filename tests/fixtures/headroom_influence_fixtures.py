from __future__ import annotations

from typing import Final, TypedDict, Unpack

_SYMBOL_KIND_SEQUENCE: Final[tuple[str, ...]] = (
    "function",
    "class",
    "method",
    "variable",
    "module",
)

_LONG_SINGLE_LINE: Final[str] = "x" * 4096


class SymbolResult(TypedDict):
    name: str
    qualified_name: str
    path: str
    line: int
    end_line: int
    kind: str
    match_type: str
    role: str
    score: float
    snippet: str


class SymbolSearchFixtures(TypedDict):
    empty: tuple[()]
    large_exact_matches: tuple[SymbolResult, ...]
    mixed_definition_reference: tuple[SymbolResult, ...]


class TestOutputCase(TypedDict):
    name: str
    failed_test_names: tuple[str, ...]
    assertion_summary: str | None
    traceback_root_cause: str | None
    relevant_files: tuple[str, ...]
    rerun_command: str
    deterministic: bool
    stdout: str
    stderr: str
    exit_code: int


class TestOutputFixtures(TypedDict):
    empty: TestOutputCase
    failing_assertion: TestOutputCase
    traceback_root_cause: TestOutputCase
    environmental_failure: TestOutputCase
    non_utf8_safe_text: TestOutputCase
    very_long_single_line: TestOutputCase


def build_symbol_search_fixtures() -> SymbolSearchFixtures:
    exact_matches = tuple(
        _symbol_result(
            name=f"build_task_{group_index}_{offset_index}",
            qualified_name=(
                f"acme.pipeline.module_{group_index:02d}.build_task_"
                f"{group_index}_{offset_index}"
            ),
            path=f"src/acme/pipeline/module_{group_index:02d}.py",
            line=10 + (offset_index * 6),
            end_line=12 + (offset_index * 6),
            kind=_SYMBOL_KIND_SEQUENCE[
                (group_index * 4 + offset_index) % len(_SYMBOL_KIND_SEQUENCE)
            ],
            match_type="exact",
            role="definition",
            score=1.0 - ((group_index * 4 + offset_index) * 0.01),
            snippet=(f"def build_task_{group_index}_{offset_index}() -> None: ..."),
        )
        for group_index in range(6)
        for offset_index in range(4)
    )
    mixed_definition_reference = (
        _symbol_result(
            name="build_daily_plan",
            qualified_name="acme_tasks.workflow.build_daily_plan",
            path="src/acme_tasks/workflow.py",
            line=12,
            end_line=26,
            kind="function",
            match_type="exact",
            role="definition",
            score=0.99,
            snippet="def build_daily_plan() -> list[str]: ...",
        ),
        _symbol_result(
            name="build_daily_plan",
            qualified_name="acme_tasks.workflow.build_daily_plan",
            path="tests/test_workflow.py",
            line=8,
            end_line=8,
            kind="function",
            match_type="partial",
            role="reference",
            score=0.74,
            snippet="from acme_tasks.workflow import build_daily_plan",
        ),
        _symbol_result(
            name="workflow",
            qualified_name="acme_tasks.workflow",
            path="src/acme_tasks/__init__.py",
            line=1,
            end_line=1,
            kind="module",
            match_type="partial",
            role="reference",
            score=0.62,
            snippet="from .workflow import build_daily_plan",
        ),
    )

    return {
        "empty": (),
        "large_exact_matches": exact_matches,
        "mixed_definition_reference": mixed_definition_reference,
    }


def build_test_output_fixtures() -> TestOutputFixtures:
    return {
        "empty": _test_output_case(
            name="empty",
            failed_test_names=(),
            assertion_summary=None,
            traceback_root_cause=None,
            relevant_files=(),
            rerun_command="pytest -q",
            deterministic=True,
            stdout="",
            stderr="",
            exit_code=0,
        ),
        "failing_assertion": _test_output_case(
            name="failing_assertion",
            failed_test_names=("tests/test_numbers.py::test_sum",),
            assertion_summary="assert 2 == 3",
            traceback_root_cause="assert 2 == 3",
            relevant_files=("src/numbers.py", "tests/test_numbers.py"),
            rerun_command="pytest tests/test_numbers.py -q",
            deterministic=True,
            stdout="",
            stderr=(
                "=" * 35
                + " FAILURES "
                + "=" * 35
                + "\n"
                + "tests/test_numbers.py::test_sum\n"
                + "E       assert 2 == 3\n"
            ),
            exit_code=1,
        ),
        "traceback_root_cause": _test_output_case(
            name="traceback_root_cause",
            failed_test_names=("tests/test_loader.py::test_imports",),
            assertion_summary=None,
            traceback_root_cause="ValueError: invalid manifest header",
            relevant_files=("src/loader.py", "tests/test_loader.py"),
            rerun_command="pytest tests/test_loader.py -q",
            deterministic=True,
            stdout="",
            stderr=(
                "Traceback (most recent call last):\n"
                '  File "tests/test_loader.py", line 9, in test_imports\n'
                "    load_manifest()\n"
                '  File "src/loader.py", line 31, in load_manifest\n'
                "    raise ValueError('invalid manifest header')\n"
                "ValueError: invalid manifest header\n"
            ),
            exit_code=1,
        ),
        "environmental_failure": _test_output_case(
            name="environmental_failure",
            failed_test_names=("tests/test_network.py::test_fetch",),
            assertion_summary=None,
            traceback_root_cause="OSError: [Errno 24] Too many open files",
            relevant_files=("tests/test_network.py",),
            rerun_command="pytest tests/test_network.py -q",
            deterministic=False,
            stdout="",
            stderr=(
                "E       OSError: [Errno 24] Too many open files\n"
                "E       during local socket setup\n"
            ),
            exit_code=1,
        ),
        "non_utf8_safe_text": _test_output_case(
            name="non_utf8_safe_text",
            failed_test_names=("tests/test_decode.py::test_report",),
            assertion_summary="assert decoded_text == 'replacement sentinel'",
            traceback_root_cause="UnicodeDecodeError: replacement sentinel used",
            relevant_files=("tests/test_decode.py",),
            rerun_command="pytest tests/test_decode.py -q",
            deterministic=True,
            stdout="decoded with replacement sentinel: bad-bytes-\ufffd-sentinel",
            stderr="",
            exit_code=1,
        ),
        "very_long_single_line": _test_output_case(
            name="very_long_single_line",
            failed_test_names=("tests/test_stream.py::test_line_wrap",),
            assertion_summary="assert line_length <= 80",
            traceback_root_cause="AssertionError: line length exceeded 80 columns",
            relevant_files=("tests/test_stream.py",),
            rerun_command="pytest tests/test_stream.py -q",
            deterministic=True,
            stdout=_LONG_SINGLE_LINE,
            stderr="",
            exit_code=1,
        ),
    }


def _symbol_result(**payload: Unpack[SymbolResult]) -> SymbolResult:
    return payload


def _test_output_case(**payload: Unpack[TestOutputCase]) -> TestOutputCase:
    return payload
