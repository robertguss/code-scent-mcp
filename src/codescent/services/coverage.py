from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

from defusedxml.ElementTree import ParseError
from defusedxml.ElementTree import parse as parse_xml

from codescent.engine.parsers.python import parse_python_file
from codescent.engine.rules.model import (
    CodeHealthFinding,
    FindingSpec,
    build_finding,
)

if TYPE_CHECKING:
    from xml.etree import ElementTree as ET

MAX_COVERAGE_FINDINGS: Final = 200


@dataclass(frozen=True, slots=True)
class FileCoverage:
    path: str
    uncovered_lines: frozenset[int]


def load_coverage(
    repo_root: Path | str,
    *,
    coverage_path: str = "coverage.xml",
) -> tuple[FileCoverage, ...]:
    """Parse Cobertura XML and return uncovered lines by repo-relative file."""
    root = Path(repo_root).resolve()
    report_path = _coverage_report_path(root, coverage_path)
    if report_path is None or not report_path.is_file():
        return ()

    try:
        tree = parse_xml(report_path)
    except (ParseError, OSError):
        return ()

    coverage_root = tree.getroot()
    if coverage_root is None:
        return ()

    source_roots = _source_roots(root, coverage_root)
    uncovered_by_path: dict[str, set[int]] = {}
    for class_element in _elements_named(coverage_root, "class"):
        filename = class_element.get("filename")
        if not filename:
            continue
        normalized = _repo_relative_existing_path(root, filename, source_roots)
        if normalized is None:
            continue
        uncovered = _uncovered_lines(class_element)
        if not uncovered:
            continue
        uncovered_by_path.setdefault(normalized, set()).update(uncovered)

    return tuple(
        FileCoverage(path=path, uncovered_lines=frozenset(sorted(lines)))
        for path, lines in sorted(uncovered_by_path.items())
    )


def coverage_findings(
    repo_root: Path | str,
    *,
    coverage_path: str = "coverage.xml",
    limit: int = MAX_COVERAGE_FINDINGS,
) -> tuple[CodeHealthFinding, ...]:
    coverage = load_coverage(repo_root, coverage_path=coverage_path)
    if not coverage or limit < 1:
        return ()

    root = Path(repo_root).resolve()
    candidates: list[tuple[int, str, int, str, CodeHealthFinding]] = []
    for file_coverage in coverage:
        parsed = parse_python_file(root / file_coverage.path, file_coverage.path)
        for symbol in parsed.symbols:
            uncovered_in_symbol = sum(
                1
                for line in file_coverage.uncovered_lines
                if symbol.start_line <= line <= symbol.end_line
            )
            if uncovered_in_symbol == 0:
                continue
            candidates.append(
                (
                    uncovered_in_symbol,
                    file_coverage.path,
                    symbol.start_line,
                    symbol.qualified_name,
                    build_finding(
                        FindingSpec(
                            rule_id="python.uncovered_symbol",
                            title="Uncovered symbol",
                            message=(
                                f"{symbol.qualified_name} has uncovered lines "
                                "per coverage.xml."
                            ),
                            file_path=file_coverage.path,
                            symbol=symbol.qualified_name,
                            severity="info",
                            confidence=0.95,
                            evidence={
                                "uncovered_in_symbol": uncovered_in_symbol,
                                "start_line": symbol.start_line,
                                "end_line": symbol.end_line,
                            },
                            suggested_action=(
                                "Add a test exercising the uncovered lines "
                                "before changing behavior."
                            ),
                        ),
                    ),
                ),
            )

    ranked = sorted(candidates, key=lambda item: (-item[0], item[1], item[2], item[3]))
    return tuple(candidate[-1] for candidate in ranked[:limit])


def _coverage_report_path(repo_root: Path, coverage_path: str) -> Path | None:
    configured = Path(coverage_path)
    candidate = configured if configured.is_absolute() else repo_root / configured
    resolved = candidate.resolve()
    if not _is_relative_to(resolved, repo_root):
        return None
    return resolved


def _source_roots(repo_root: Path, root: ET.Element) -> tuple[Path, ...]:
    roots: list[Path] = []
    for source in _elements_named(root, "source"):
        if source.text is None:
            continue
        text = source.text.strip()
        if not text:
            continue
        source_path = Path(text)
        candidate = (
            source_path if source_path.is_absolute() else repo_root / source_path
        )
        resolved = candidate.resolve()
        if _is_relative_to(resolved, repo_root):
            roots.append(resolved)
    return tuple(roots)


def _repo_relative_existing_path(
    repo_root: Path,
    filename: str,
    source_roots: tuple[Path, ...],
) -> str | None:
    filename_path = Path(filename)
    raw_candidates: list[Path] = [
        filename_path if filename_path.is_absolute() else repo_root / filename_path,
    ]
    raw_candidates.extend(source_root / filename_path for source_root in source_roots)

    for candidate in raw_candidates:
        resolved = candidate.resolve()
        if (
            _is_relative_to(resolved, repo_root)
            and resolved.is_file()
            and not _has_parent_reference(filename_path)
        ):
            return resolved.relative_to(repo_root).as_posix()
    return None


def _uncovered_lines(class_element: ET.Element) -> set[int]:
    uncovered: set[int] = set()
    for line in _elements_named(class_element, "line"):
        if line.get("hits") != "0":
            continue
        number = line.get("number")
        if number is None:
            continue
        try:
            parsed = int(number)
        except ValueError:
            continue
        if parsed > 0:
            uncovered.add(parsed)
    return uncovered


def _elements_named(
    root: ET.Element,
    name: str,
) -> tuple[ET.Element, ...]:
    return tuple(element for element in root.iter() if _local_name(element.tag) == name)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", maxsplit=1)[-1]


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        _ = path.relative_to(parent)
    except ValueError:
        return False
    return True


def _has_parent_reference(path: Path) -> bool:
    return ".." in path.parts
