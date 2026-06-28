from pathlib import Path
from textwrap import dedent

from codescent.engine.rules.dead_code import build_name_use_index, scan_dead_code


def test_name_use_index_collects_used_names_and_candidates(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(
        repo / "src" / "pkg" / "a.py",
        """
        __all__ = ["exported_fn"]

        def used_fn() -> str:
            return "used"

        def tested_fn() -> str:
            return "tested"

        def exported_fn() -> str:
            return "exported"

        def orphan_fn() -> str:
            return "orphan"

        class OrphanClass:
            pass

        def main() -> None:
            pass

        def wrapper() -> object:
            def inner() -> str:
                return "inner"
            return inner()
        """,
    )
    _write(
        repo / "src" / "pkg" / "b.py",
        """
        from pkg.a import used_fn, wrapper

        def call_used() -> str:
            return used_fn() + str(wrapper())
        """,
    )
    _write(
        repo / "tests" / "test_a.py",
        """
        from pkg.a import tested_fn

        def helper_in_test() -> str:
            return tested_fn()
        """,
    )

    index = build_name_use_index(repo)

    assert {"used_fn", "tested_fn"} <= index.used_names
    # __all__ exports are recognized as entry points (reachable from outside the
    # internal call graph) rather than internal "used" names.
    assert index.entry_points.is_entry_point("exported_fn")
    assert [candidate.name for candidate in index.candidates] == [
        "orphan_fn",
        "OrphanClass",
        "call_used",
    ]
    assert all(candidate.name != "inner" for candidate in index.candidates)
    assert all(candidate.path != "tests/test_a.py" for candidate in index.candidates)


def test_name_use_index_excludes_dunders_and_entrypoint_names(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _write(
        repo / "module.py",
        """
        def __main__() -> None:
            pass

        def app() -> None:
            pass

        def run() -> None:
            pass

        def unused() -> None:
            pass
        """,
    )

    index = build_name_use_index(repo)

    assert [candidate.name for candidate in index.candidates] == ["unused"]


def test_scan_dead_code_flags_only_unreferenced_module_level_symbols(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _write(
        repo / "src" / "pkg" / "a.py",
        """
        def used_fn() -> str:
            return "used"

        def orphan_fn() -> str:
            return "orphan"
        """,
    )
    _write(
        repo / "src" / "pkg" / "b.py",
        """
        from pkg.a import used_fn

        RESULT = used_fn()
        """,
    )

    findings = scan_dead_code(repo)

    assert [finding.symbol for finding in findings] == ["pkg.a.orphan_fn"]
    orphan = findings[0]
    assert orphan.rule_id == "python.dead_code_candidate"
    assert orphan.title == "Dead code candidate"
    assert orphan.confidence == 0.6
    assert orphan.evidence == {
        "start_line": 5,
        "end_line": 6,
        "kind": "function",
    }
    assert orphan.suggested_action == (
        "Verify no dynamic entrypoint or external caller depends on this symbol "
        "before removing it."
    )


def test_scan_dead_code_excludes_exports_tests_dunders_nested_and_entrypoints(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _write(
        repo / "src" / "pkg" / "module.py",
        """
        __all__ = ["exported_fn"]

        def exported_fn() -> str:
            return "exported"

        def tested_fn() -> str:
            return "tested"

        def __main__() -> None:
            pass

        def main() -> None:
            pass

        def app() -> None:
            pass

        def run() -> None:
            pass

        def wrapper() -> str:
            def inner() -> str:
                return "inner"
            return inner()

        RESULT = wrapper()
        """,
    )
    _write(
        repo / "tests" / "test_module.py",
        """
        from pkg.module import tested_fn

        def helper_in_test() -> str:
            return tested_fn()
        """,
    )

    findings = scan_dead_code(repo)

    assert findings == ()


def test_scan_dead_code_is_bounded_by_limit(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(
        repo / "module.py",
        """
        def first() -> None:
            pass

        def second() -> None:
            pass
        """,
    )

    findings = scan_dead_code(repo, limit=1)

    assert len(findings) == 1
    assert findings[0].symbol == "module.first"


def _write(path: Path, source: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(dedent(source))
