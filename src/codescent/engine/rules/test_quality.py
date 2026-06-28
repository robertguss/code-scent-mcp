"""Deterministic test-quality smells for Python and TS/JS test files.

Flags low-value tests that erode the safety net:

* assertion-free tests (no assertion of any kind),
* no-op / always-pass tests (``assert True`` / ``expect(true).toBe(true)`` /
  empty or ``pass``-only bodies),
* over-mocked tests (many mocks, few/no real assertions),
* skip/xfail clusters (a file with several skipped/``xfail``/``.skip``/``xit``
  tests).

Python detection uses the stdlib ``ast`` (no new dependency); TS/JS detection is
regex-heuristic over source text (this repo never uses tree-sitter). Every
finding is heuristic, bounded, and deterministically ordered so repeated scans
yield identical ids. Findings carry the test name + line in ``evidence`` rather
than a resolved ``symbol`` -- the smell is a heuristic judgement, not a
symbol-resolution fact, so the tier stays ``heuristic`` even for ``python.*``.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from codescent.core.models import ProjectConfig
from codescent.core.paths import resolve_repo_root
from codescent.engine.inventory import build_file_inventory
from codescent.engine.rules.model import (
    CONFIDENCE_TIER_HEURISTIC,
    CodeHealthFinding,
    EvidenceValue,
    FindingSpec,
    build_finding,
)
from codescent.engine.source_read import read_source_text

if TYPE_CHECKING:
    from pathlib import Path

MAX_TEST_QUALITY_FINDINGS: Final = 200
OVER_MOCK_MIN_MOCKS: Final = 3
OVER_MOCK_RATIO: Final = 2
SKIP_CLUSTER_MIN: Final = 3

PY_ASSERTION_FREE_RULE_ID: Final = "python.assertion_free_test"
PY_NO_OP_RULE_ID: Final = "python.no_op_test"
PY_OVER_MOCK_RULE_ID: Final = "python.over_mocked_test"
PY_SKIP_CLUSTER_RULE_ID: Final = "python.skipped_test_cluster"
TS_ASSERTION_FREE_RULE_ID: Final = "typescript.assertion_free_test"
TS_NO_OP_RULE_ID: Final = "typescript.no_op_test"
TS_OVER_MOCK_RULE_ID: Final = "typescript.over_mocked_test"
TS_SKIP_CLUSTER_RULE_ID: Final = "typescript.skipped_test_cluster"

_TS_LANGUAGES: Final = frozenset({"javascript", "typescript"})
_PY_MOCK_NAMES: Final = frozenset(
    {
        "AsyncMock",
        "MagicMock",
        "Mock",
        "NonCallableMagicMock",
        "NonCallableMock",
        "create_autospec",
        "patch",
    },
)
_PY_ASSERT_CALL_NAMES: Final = frozenset({"fail", "raises", "warns"})
_SKIP_TOKENS: Final = ("skip", "xfail")

_ADD_ASSERTION = "Add a meaningful assertion on the behavior under test."
_REDUCE_MOCKING = (
    "Reduce mocking and assert real behavior, or delete the test if it only "
    "exercises mocks."
)
_UNSKIP_OR_DELETE = (
    "Unskip the tests once they pass, or delete them if they are obsolete; a "
    "growing skip cluster hides untested behavior."
)


@dataclass(frozen=True, slots=True)
class _Smell:
    rule_id: str
    title: str
    severity: str
    confidence: float
    suggested_action: str


_PY_ASSERTION_FREE: Final = _Smell(
    PY_ASSERTION_FREE_RULE_ID, "Assertion-free test", "warning", 0.8, _ADD_ASSERTION
)
_PY_NO_OP: Final = _Smell(
    PY_NO_OP_RULE_ID, "No-op test", "warning", 0.8, _ADD_ASSERTION
)
_PY_OVER_MOCK: Final = _Smell(
    PY_OVER_MOCK_RULE_ID, "Over-mocked test", "warning", 0.7, _REDUCE_MOCKING
)
_PY_SKIP_CLUSTER: Final = _Smell(
    PY_SKIP_CLUSTER_RULE_ID,
    "Skipped/xfail test cluster",
    "info",
    0.7,
    _UNSKIP_OR_DELETE,
)
_TS_ASSERTION_FREE: Final = _Smell(
    TS_ASSERTION_FREE_RULE_ID, "Assertion-free test", "warning", 0.7, _ADD_ASSERTION
)
_TS_NO_OP: Final = _Smell(
    TS_NO_OP_RULE_ID, "No-op test", "warning", 0.7, _ADD_ASSERTION
)
_TS_OVER_MOCK: Final = _Smell(
    TS_OVER_MOCK_RULE_ID, "Over-mocked test", "warning", 0.7, _REDUCE_MOCKING
)
_TS_SKIP_CLUSTER: Final = _Smell(
    TS_SKIP_CLUSTER_RULE_ID, "Skipped test cluster", "info", 0.7, _UNSKIP_OR_DELETE
)


def _finding(
    smell: _Smell,
    path: str,
    message: str,
    evidence: dict[str, EvidenceValue],
) -> CodeHealthFinding:
    return build_finding(
        FindingSpec(
            rule_id=smell.rule_id,
            title=smell.title,
            message=message,
            file_path=path,
            symbol=None,
            severity=smell.severity,
            confidence=smell.confidence,
            evidence=evidence,
            suggested_action=smell.suggested_action,
            confidence_tier=CONFIDENCE_TIER_HEURISTIC,
        ),
    )


# Python smells, detected with the stdlib ast module.
@dataclass(frozen=True, slots=True)
class _PyTest:
    name: str
    line: int
    node: ast.FunctionDef | ast.AsyncFunctionDef


@dataclass(frozen=True, slots=True)
class _PyCounts:
    total_asserts: int
    nontrivial_asserts: int
    trivial_true_asserts: int
    mock_count: int
    trivial_body: bool


def scan_python_test_quality(
    root: Path | str,
    *,
    config: ProjectConfig | None = None,
    limit: int = MAX_TEST_QUALITY_FINDINGS,
) -> tuple[CodeHealthFinding, ...]:
    """Flag low-value Python test functions (assertion-free/no-op/over-mocked).

    Also emits one per-file finding for skip/``xfail`` clusters. Returns a
    bounded, deterministically ordered tuple; degrades to zero findings on
    unparseable files.
    """
    if limit < 1:
        return ()
    repo_root = resolve_repo_root(root)
    project_config = config or ProjectConfig()
    findings: list[CodeHealthFinding] = []
    for item in build_file_inventory(repo_root, config=project_config):
        if item.language != "python" or not item.is_test:
            continue
        source = read_source_text(repo_root / item.path)
        if source.text is None:
            continue
        findings.extend(_python_file_findings(item.path, source.text))
    return tuple(_ordered(findings)[:limit])


def _python_file_findings(path: str, text: str) -> list[CodeHealthFinding]:
    try:
        tree = ast.parse(text, filename=path)
    except SyntaxError:
        return []
    findings: list[CodeHealthFinding] = []
    for test in _collect_py_tests(tree):
        if _has_skip_decorator(test.node):
            continue
        finding = _python_test_finding(path, test)
        if finding is not None:
            findings.append(finding)
    skip_count = _count_py_skips(tree)
    if skip_count >= SKIP_CLUSTER_MIN:
        findings.append(_python_skip_cluster_finding(path, skip_count))
    return findings


def _python_test_finding(path: str, test: _PyTest) -> CodeHealthFinding | None:
    counts = _python_counts(test.node)
    evidence: dict[str, EvidenceValue] = {"test": test.name, "line": test.line}
    if counts.trivial_body:
        return _finding(
            _PY_NO_OP,
            path,
            f"Test {test.name} has an empty/``pass``-only body and asserts nothing.",
            evidence,
        )
    if counts.trivial_true_asserts > 0 and counts.nontrivial_asserts == 0:
        return _finding(
            _PY_NO_OP,
            path,
            f"Test {test.name} only asserts a constant truthy value (always passes).",
            evidence,
        )
    if counts.mock_count >= OVER_MOCK_MIN_MOCKS and counts.mock_count > (
        OVER_MOCK_RATIO * counts.total_asserts
    ):
        return _finding(
            _PY_OVER_MOCK,
            path,
            (
                f"Test {test.name} creates {counts.mock_count} mocks but makes "
                f"{counts.total_asserts} assertions."
            ),
            {
                **evidence,
                "mock_count": counts.mock_count,
                "assert_count": counts.total_asserts,
            },
        )
    if counts.total_asserts == 0:
        return _finding(
            _PY_ASSERTION_FREE,
            path,
            f"Test {test.name} contains no assertion.",
            evidence,
        )
    return None


def _python_skip_cluster_finding(path: str, count: int) -> CodeHealthFinding:
    return _finding(
        _PY_SKIP_CLUSTER,
        path,
        f"{path} has {count} skipped/xfail tests.",
        {"count": count, "threshold": SKIP_CLUSTER_MIN},
    )


def _collect_py_tests(tree: ast.Module) -> list[_PyTest]:
    tests: list[_PyTest] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and _is_test_name(
            node.name,
        ):
            tests.append(_PyTest(node.name, node.lineno, node))
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            tests.extend(
                _PyTest(f"{node.name}.{member.name}", member.lineno, member)
                for member in node.body
                if isinstance(member, ast.FunctionDef | ast.AsyncFunctionDef)
                and _is_test_name(member.name)
            )
    return tests


def _count_py_skips(tree: ast.Module) -> int:
    count = 0
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            count += int(_has_skip_decorator(node))
            count += sum(
                int(_has_skip_decorator(member))
                for member in node.body
                if isinstance(member, ast.FunctionDef | ast.AsyncFunctionDef)
                and _is_test_name(member.name)
            )
        elif (
            isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            and _is_test_name(node.name)
            and _has_skip_decorator(node)
        ):
            count += 1
    return count


def _python_counts(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> _PyCounts:
    total_assert_stmts = 0
    trivial_true = 0
    assert_calls = 0
    mock_count = 0
    for child in ast.walk(node):
        if isinstance(child, ast.Assert):
            total_assert_stmts += 1
            if _is_always_true_assert(child):
                trivial_true += 1
        elif isinstance(child, ast.Call):
            name = _dotted(child.func)
            if _is_assert_name(name):
                assert_calls += 1
            elif _is_mock_name(name):
                mock_count += 1
    total_asserts = total_assert_stmts + assert_calls
    nontrivial = (total_assert_stmts - trivial_true) + assert_calls
    return _PyCounts(
        total_asserts=total_asserts,
        nontrivial_asserts=nontrivial,
        trivial_true_asserts=trivial_true,
        mock_count=mock_count,
        trivial_body=_is_trivial_body(node.body),
    )


def _has_skip_decorator(
    node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
) -> bool:
    return any(_is_skip_decorator(decorator) for decorator in node.decorator_list)


def _is_skip_decorator(decorator: ast.expr) -> bool:
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    name = _dotted(target).lower()
    return any(token in name for token in _SKIP_TOKENS)


def _is_trivial_body(body: list[ast.stmt]) -> bool:
    return all(_is_noop_stmt(stmt) for stmt in body)


def _is_noop_stmt(stmt: ast.stmt) -> bool:
    if isinstance(stmt, ast.Pass):
        return True
    # Docstrings and bare ``...`` are both ``Expr`` wrapping a ``Constant``.
    return isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant)


def _is_always_true_assert(node: ast.Assert) -> bool:
    return isinstance(node.test, ast.Constant) and bool(node.test.value)


def _is_assert_name(name: str) -> bool:
    last = name.rsplit(".", 1)[-1]
    return last.startswith("assert") or last in _PY_ASSERT_CALL_NAMES


def _is_mock_name(name: str) -> bool:
    return any(part in _PY_MOCK_NAMES for part in name.split("."))


def _dotted(node: ast.expr) -> str:
    parts: list[str] = []
    current: ast.expr = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    return ".".join(reversed(parts))


def _is_test_name(name: str) -> bool:
    return name.startswith("test")


# TypeScript and JavaScript smells, detected with regex heuristics only.
_TS_TEST_CALL_RE: Final = re.compile(
    r"\b(?P<fn>it|test|fit|xit)(?P<mod>(?:\.\w+)*)\s*\("
)
_TS_SKIP_RE: Final = re.compile(
    r"\b(?:x(?:it|test|describe)\b|(?:it|test|describe)\.(?:skip|todo)\b)",
)
_TS_TITLE_RE: Final = re.compile(r"^\s*(['\"`])(?P<title>.*?)\1", re.DOTALL)
_TS_EXPECT_RE: Final = re.compile(r"\bexpect\s*\(")
_TS_ASSERT_RE: Final = re.compile(r"\bassert\s*[(.]")
_TS_EMPTY_BODY_RE: Final = re.compile(
    r"=>\s*\{\s*\}|function\s*\*?\s*\([^)]*\)\s*\{\s*\}"
)
_TS_ALWAYS_PASS_PATTERNS: Final = (
    r"expect\(\s*true\s*\)\s*\.\s*toBe\(\s*true\s*\)",
    r"expect\(\s*true\s*\)\s*\.\s*toBeTruthy\(\s*\)",
    r"expect\(\s*false\s*\)\s*\.\s*toBe\(\s*false\s*\)",
    r"expect\(\s*1\s*\)\s*\.\s*toBe\(\s*1\s*\)",
    r"assert\(\s*true\s*\)",
    r"assert\.ok\(\s*true\s*\)",
)
_TS_MOCK_PATTERNS: Final = (
    r"\b(?:jest|vi)\s*\.\s*(?:fn|spyOn|mock)\b",
    r"\bsinon\s*\.\s*(?:stub|mock|fake|spy)\b",
    r"\.\s*mock(?:Return|Resolved|Rejected)?Value(?:Once)?\b",
    r"\.\s*mockImplementation(?:Once)?\b",
    r"\bcreateMock\b",
)
_TS_ALWAYS_PASS_RE: Final = re.compile("|".join(_TS_ALWAYS_PASS_PATTERNS))
_TS_MOCK_RE: Final = re.compile("|".join(_TS_MOCK_PATTERNS))


@dataclass(frozen=True, slots=True)
class _TsCounts:
    total_asserts: int
    nontrivial_asserts: int
    trivial_pass: int
    mock_count: int
    empty_body: bool


def scan_typescript_test_quality(
    root: Path | str,
    *,
    config: ProjectConfig | None = None,
    limit: int = MAX_TEST_QUALITY_FINDINGS,
) -> tuple[CodeHealthFinding, ...]:
    """Flag low-value TS/JS tests via regex heuristics over test-file source.

    Mirrors the Python scanner (assertion-free/no-op/over-mocked + skip
    clusters) but never parses an AST -- TS/JS support in this repo is regex
    only. Returns a bounded, deterministically ordered tuple.
    """
    if limit < 1:
        return ()
    repo_root = resolve_repo_root(root)
    project_config = config or ProjectConfig()
    findings: list[CodeHealthFinding] = []
    for item in build_file_inventory(repo_root, config=project_config):
        if item.language not in _TS_LANGUAGES or not item.is_test:
            continue
        source = read_source_text(repo_root / item.path)
        if source.text is None:
            continue
        findings.extend(_typescript_file_findings(item.path, source.text))
    return tuple(_ordered(findings)[:limit])


def _typescript_file_findings(path: str, text: str) -> list[CodeHealthFinding]:
    findings: list[CodeHealthFinding] = []
    for match in _TS_TEST_CALL_RE.finditer(text):
        modifier = match.group("mod") or ""
        if match.group("fn") == "xit" or _has_skip_modifier(modifier):
            continue
        if "each" in modifier:  # ponytail: .each() reshapes args; skip rather than FP.
            continue
        open_index = match.end() - 1
        region = text[open_index + 1 : _match_paren(text, open_index) - 1]
        finding = _typescript_test_finding(
            path,
            region,
            _line_at(text, match.start()),
        )
        if finding is not None:
            findings.append(finding)
    skip_count = len(_TS_SKIP_RE.findall(text))
    if skip_count >= SKIP_CLUSTER_MIN:
        findings.append(_typescript_skip_cluster_finding(path, skip_count))
    return findings


def _typescript_test_finding(
    path: str,
    region: str,
    line: int,
) -> CodeHealthFinding | None:
    counts = _typescript_counts(region)
    title = _ts_title(region)
    evidence: dict[str, EvidenceValue] = {"test": title, "line": line}
    if counts.empty_body:
        return _finding(
            _TS_NO_OP,
            path,
            f"Test {title} has an empty body and asserts nothing.",
            evidence,
        )
    if counts.trivial_pass > 0 and counts.nontrivial_asserts == 0:
        return _finding(
            _TS_NO_OP,
            path,
            f"Test {title} only asserts a constant truthy value (always passes).",
            evidence,
        )
    if counts.mock_count >= OVER_MOCK_MIN_MOCKS and counts.mock_count > (
        OVER_MOCK_RATIO * counts.total_asserts
    ):
        return _finding(
            _TS_OVER_MOCK,
            path,
            (
                f"Test {title} creates {counts.mock_count} mocks but makes "
                f"{counts.total_asserts} assertions."
            ),
            {
                **evidence,
                "mock_count": counts.mock_count,
                "assert_count": counts.total_asserts,
            },
        )
    if counts.total_asserts == 0:
        return _finding(
            _TS_ASSERTION_FREE,
            path,
            f"Test {title} contains no assertion.",
            evidence,
        )
    return None


def _typescript_skip_cluster_finding(path: str, count: int) -> CodeHealthFinding:
    return _finding(
        _TS_SKIP_CLUSTER,
        path,
        f"{path} has {count} skipped/todo tests.",
        {"count": count, "threshold": SKIP_CLUSTER_MIN},
    )


def _typescript_counts(region: str) -> _TsCounts:
    expect_count = len(_TS_EXPECT_RE.findall(region))
    assert_count = len(_TS_ASSERT_RE.findall(region))
    total = expect_count + assert_count
    trivial = len(_TS_ALWAYS_PASS_RE.findall(region))
    return _TsCounts(
        total_asserts=total,
        nontrivial_asserts=total - trivial,
        trivial_pass=trivial,
        mock_count=len(_TS_MOCK_RE.findall(region)),
        empty_body=bool(_TS_EMPTY_BODY_RE.search(region)),
    )


def _has_skip_modifier(modifier: str) -> bool:
    return ".skip" in modifier or ".todo" in modifier


def _ts_title(region: str) -> str:
    match = _TS_TITLE_RE.match(region)
    if match is None:
        return "(anonymous)"
    return match.group("title").strip() or "(anonymous)"


def _match_paren(source: str, open_index: int) -> int:
    """Return the index just past the ``)`` matching ``source[open_index]``.

    Skips parentheses inside strings and comments so ``expect(foo())`` does not
    confuse the matcher. Template-literal interpolations are treated as opaque
    string content (ponytail: naive, fine for test bodies).
    """
    depth = 0
    index = open_index
    length = len(source)
    while index < length:
        char = source[index]
        if char in "\"'`":
            index = _skip_string(source, index)
            continue
        if char == "/" and index + 1 < length:
            advanced = _skip_comment(source, index)
            if advanced is not None:
                index = advanced
                continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    return length


def _skip_string(source: str, index: int) -> int:
    quote = source[index]
    index += 1
    length = len(source)
    while index < length:
        char = source[index]
        if char == "\\":
            index += 2
            continue
        if char == quote:
            return index + 1
        index += 1
    return length


def _skip_comment(source: str, index: int) -> int | None:
    nxt = source[index + 1]
    if nxt == "/":
        end = source.find("\n", index)
        return len(source) if end == -1 else end
    if nxt == "*":
        end = source.find("*/", index + 2)
        return len(source) if end == -1 else end + 2
    return None


def _line_at(source: str, index: int) -> int:
    return source.count("\n", 0, index) + 1


# --------------------------------------------------------------------------- #
# Shared ordering
# --------------------------------------------------------------------------- #
def _ordered(findings: list[CodeHealthFinding]) -> list[CodeHealthFinding]:
    return sorted(
        findings,
        key=lambda finding: (
            finding.file_path,
            int(finding.evidence.get("line", 0)),
            finding.rule_id,
            str(finding.evidence.get("test", "")),
        ),
    )
