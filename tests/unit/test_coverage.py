from pathlib import Path
from textwrap import dedent

from codescent.services.coverage import FileCoverage, coverage_findings, load_coverage


def test_load_coverage_reads_cobertura_uncovered_lines(tmp_path: Path) -> None:
    source = tmp_path / "src" / "pkg" / "module.py"
    source.parent.mkdir(parents=True)
    _ = source.write_text("def covered() -> None:\n    pass\n")
    other = tmp_path / "pkg" / "other.py"
    other.parent.mkdir(parents=True)
    _ = other.write_text("def uncovered() -> None:\n    pass\n")
    _ = (tmp_path / "coverage.xml").write_text(
        """
        <coverage>
          <sources>
            <source>src</source>
          </sources>
          <packages>
            <package name="pkg">
              <classes>
                <class filename="pkg/module.py">
                  <lines>
                    <line number="1" hits="0" />
                    <line number="2" hits="3" />
                  </lines>
                </class>
                <class filename="pkg/other.py">
                  <lines>
                    <line number="4" hits="0" />
                    <line number="5" hits="0" />
                    <line number="bad" hits="0" />
                  </lines>
                </class>
              </classes>
            </package>
          </packages>
        </coverage>
        """,
    )

    assert load_coverage(tmp_path) == (
        FileCoverage(path="pkg/other.py", uncovered_lines=frozenset({4, 5})),
        FileCoverage(path="src/pkg/module.py", uncovered_lines=frozenset({1})),
    )


def test_load_coverage_returns_empty_for_missing_report(tmp_path: Path) -> None:
    assert load_coverage(tmp_path) == ()


def test_load_coverage_returns_empty_for_malformed_report(tmp_path: Path) -> None:
    _ = (tmp_path / "coverage.xml").write_text("<coverage>")

    assert load_coverage(tmp_path) == ()


def test_load_coverage_skips_files_that_cannot_be_matched(
    tmp_path: Path,
) -> None:
    _ = (tmp_path / "coverage.xml").write_text(
        """
        <coverage>
          <packages>
            <package name="pkg">
              <classes>
                <class filename="../outside.py">
                  <lines>
                    <line number="1" hits="0" />
                  </lines>
                </class>
                <class filename="missing.py">
                  <lines>
                    <line number="2" hits="0" />
                  </lines>
                </class>
              </classes>
            </package>
          </packages>
        </coverage>
        """,
    )

    assert load_coverage(tmp_path) == ()


def test_coverage_findings_map_uncovered_lines_to_symbols(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src" / "pkg" / "module.py"
    source.parent.mkdir(parents=True)
    _ = source.write_text(
        dedent(
            """\
            def alpha() -> int:
                first = 1
                return first

            def beta() -> int:
                second = 2
                if second:
                    return second
                return 0
            """,
        ),
    )
    _ = (tmp_path / "coverage.xml").write_text(
        """
        <coverage>
          <packages>
            <package name="pkg">
              <classes>
                <class filename="src/pkg/module.py">
                  <lines>
                    <line number="2" hits="0" />
                    <line number="6" hits="0" />
                    <line number="8" hits="0" />
                    <line number="99" hits="0" />
                  </lines>
                </class>
              </classes>
            </package>
          </packages>
        </coverage>
        """,
    )

    findings = coverage_findings(tmp_path)

    assert [finding.symbol for finding in findings] == (
        ["pkg.module.beta", "pkg.module.alpha"]
    )
    beta = findings[0]
    assert beta.rule_id == "python.uncovered_symbol"
    assert beta.file_path == "src/pkg/module.py"
    assert beta.severity == "info"
    assert beta.confidence == 0.95
    assert beta.evidence == {
        "uncovered_in_symbol": 2,
        "start_line": 5,
        "end_line": 9,
    }


def test_coverage_findings_are_bounded_by_limit(tmp_path: Path) -> None:
    source = tmp_path / "module.py"
    _ = source.write_text(
        dedent(
            """\
            def one() -> int:
                return 1

            def two() -> int:
                return 2
            """,
        ),
    )
    _ = (tmp_path / "coverage.xml").write_text(
        """
        <coverage>
          <packages>
            <package name="pkg">
              <classes>
                <class filename="module.py">
                  <lines>
                    <line number="2" hits="0" />
                    <line number="5" hits="0" />
                  </lines>
                </class>
              </classes>
            </package>
          </packages>
        </coverage>
        """,
    )

    findings = coverage_findings(tmp_path, limit=1)

    assert len(findings) == 1
    assert findings[0].symbol == "module.one"
