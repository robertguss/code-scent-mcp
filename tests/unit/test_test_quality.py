from __future__ import annotations

from textwrap import dedent
from typing import TYPE_CHECKING

from codescent.engine.rules.test_quality import (
    scan_python_test_quality,
    scan_typescript_test_quality,
)

if TYPE_CHECKING:
    from pathlib import Path


def _write(path: Path, source: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(dedent(source))


def _rule_ids(repo: Path, *, language: str) -> list[str]:
    scanner = (
        scan_python_test_quality
        if language == "python"
        else scan_typescript_test_quality
    )
    return sorted(finding.rule_id for finding in scanner(repo))


# --------------------------------------------------------------------------- #
# Python
# --------------------------------------------------------------------------- #
def test_python_flags_assertion_free_test(tmp_path: Path) -> None:
    _write(
        tmp_path / "tests" / "suite.py",
        """
        def test_no_assert() -> None:
            value = 1 + 1
            print(value)
        """,
    )

    findings = scan_python_test_quality(tmp_path)

    assert [f.rule_id for f in findings] == ["python.assertion_free_test"]
    assert findings[0].evidence["test"] == "test_no_assert"
    assert findings[0].confidence_tier == "heuristic"
    assert findings[0].symbol is None


def test_python_flags_no_op_assert_true_and_pass_body(tmp_path: Path) -> None:
    _write(
        tmp_path / "tests" / "suite.py",
        """
        def test_always_true() -> None:
            assert True

        def test_only_pass() -> None:
            pass
        """,
    )

    assert _rule_ids(tmp_path, language="python") == [
        "python.no_op_test",
        "python.no_op_test",
    ]


def test_python_flags_over_mocked_test(tmp_path: Path) -> None:
    _write(
        tmp_path / "tests" / "suite.py",
        """
        from unittest.mock import MagicMock, patch

        @patch("os.getcwd")
        def test_mockfest(mock_cwd: MagicMock) -> None:
            a = MagicMock()
            b = MagicMock()
            a.go()
            b.go()
        """,
    )

    findings = scan_python_test_quality(tmp_path)

    assert [f.rule_id for f in findings] == ["python.over_mocked_test"]
    assert findings[0].evidence["mock_count"] == 3
    assert findings[0].evidence["assert_count"] == 0


def test_python_flags_skip_cluster(tmp_path: Path) -> None:
    _write(
        tmp_path / "tests" / "suite.py",
        """
        import pytest

        @pytest.mark.skip
        def test_a() -> None:
            assert work() == 1

        @pytest.mark.skip
        def test_b() -> None:
            assert work() == 2

        @pytest.mark.xfail
        def test_c() -> None:
            assert work() == 3

        def work() -> int:
            return 0
        """,
    )

    findings = scan_python_test_quality(tmp_path)

    assert [f.rule_id for f in findings] == ["python.skipped_test_cluster"]
    assert findings[0].evidence["count"] == 3


def test_python_skip_decorated_tests_are_not_double_flagged(tmp_path: Path) -> None:
    # Two skips is below the cluster threshold, and a skipped empty body must not
    # be re-flagged as no-op.
    _write(
        tmp_path / "tests" / "suite.py",
        """
        import pytest

        @pytest.mark.skip
        def test_empty() -> None:
            pass

        @pytest.mark.skip
        def test_also_empty() -> None:
            pass
        """,
    )

    assert scan_python_test_quality(tmp_path) == ()


def test_python_healthy_tests_produce_no_findings(tmp_path: Path) -> None:
    _write(
        tmp_path / "tests" / "suite.py",
        """
        from unittest.mock import MagicMock

        def test_real_assert() -> None:
            assert sum([1, 2]) == 3

        def test_unittest_style() -> None:
            value = {"a": 1}
            assert value["a"] == 1

        def test_one_mock_real_assert() -> None:
            svc = MagicMock()
            svc.fetch.return_value = 7
            assert svc.fetch() == 7
        """,
    )

    assert scan_python_test_quality(tmp_path) == ()


def test_python_ignores_non_test_files(tmp_path: Path) -> None:
    # A non-test module with an assertion-free function named like a test must be
    # ignored (gated on is_test path).
    _write(
        tmp_path / "src" / "module.py",
        """
        def test_like_helper() -> None:
            value = 1
            print(value)
        """,
    )

    assert scan_python_test_quality(tmp_path) == ()


# --------------------------------------------------------------------------- #
# TypeScript / JavaScript
# --------------------------------------------------------------------------- #
def test_typescript_flags_assertion_free_test(tmp_path: Path) -> None:
    _write(
        tmp_path / "tests" / "suite.test.ts",
        """
        it("does nothing", () => {
          const value = compute();
          console.log(value);
        });
        """,
    )

    findings = scan_typescript_test_quality(tmp_path)

    assert [f.rule_id for f in findings] == ["typescript.assertion_free_test"]
    assert findings[0].evidence["test"] == "does nothing"
    assert findings[0].confidence_tier == "heuristic"


def test_typescript_flags_no_op_always_pass_and_empty(tmp_path: Path) -> None:
    _write(
        tmp_path / "tests" / "suite.test.ts",
        """
        it("always passes", () => {
          expect(true).toBe(true);
        });

        test("empty body", () => {});
        """,
    )

    assert _rule_ids(tmp_path, language="typescript") == [
        "typescript.no_op_test",
        "typescript.no_op_test",
    ]


def test_typescript_flags_over_mocked_test(tmp_path: Path) -> None:
    _write(
        tmp_path / "tests" / "suite.test.ts",
        """
        it("mocks everything", () => {
          const a = vi.fn();
          const b = vi.fn();
          const c = vi.spyOn(globalThis, "fetch");
          a();
          b();
          void c;
        });
        """,
    )

    findings = scan_typescript_test_quality(tmp_path)

    assert [f.rule_id for f in findings] == ["typescript.over_mocked_test"]
    assert findings[0].evidence["mock_count"] == 3


def test_typescript_flags_skip_cluster(tmp_path: Path) -> None:
    _write(
        tmp_path / "tests" / "suite.test.ts",
        """
        it.skip("a", () => {
          expect(run()).toBe(1);
        });

        it.skip("b", () => {
          expect(run()).toBe(2);
        });

        it.todo("c");
        """,
    )

    findings = scan_typescript_test_quality(tmp_path)

    assert [f.rule_id for f in findings] == ["typescript.skipped_test_cluster"]
    assert findings[0].evidence["count"] == 3


def test_typescript_healthy_tests_produce_no_findings(tmp_path: Path) -> None:
    _write(
        tmp_path / "tests" / "suite.test.ts",
        """
        it("adds", () => {
          expect(add(1, 2)).toBe(3);
        });

        it("verifies one call", () => {
          const spy = vi.fn();
          spy("x");
          expect(spy).toHaveBeenCalledWith("x");
        });
        """,
    )

    assert scan_typescript_test_quality(tmp_path) == ()


def test_scanners_are_bounded_and_deterministic(tmp_path: Path) -> None:
    _write(
        tmp_path / "tests" / "suite.py",
        """
        def test_a() -> None:
            value = 1
            print(value)

        def test_b() -> None:
            value = 2
            print(value)
        """,
    )

    first = scan_python_test_quality(tmp_path)
    second = scan_python_test_quality(tmp_path)
    bounded = scan_python_test_quality(tmp_path, limit=1)

    assert tuple(f.id for f in first) == tuple(f.id for f in second)
    assert len(bounded) == 1
