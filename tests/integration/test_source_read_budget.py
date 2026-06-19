from collections.abc import Callable
from pathlib import Path

import pytest

from codescent.core.models import MaintainabilityThresholds, ProjectConfig
from codescent.engine.context import source_range
from codescent.engine.inventory import build_file_inventory
from codescent.services.code_health import CodeHealthService
from codescent.services.config import ConfigService
from codescent.services.repo_index import RepoIndexService
from codescent.services.search import SearchService

OVERSIZED_SOURCE_BYTES = 2_000_000
MAX_OMITTED_SOURCE_BYTES = 512
type ReadText = Callable[[Path, str | None, str | None], str]
type ReadBytes = Callable[[Path], bytes]


class OversizedSourceReadError(AssertionError):
    pass


def test_inventory_and_index_skip_oversized_supported_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    small = repo / "src" / "small.py"
    huge = repo / "src" / "huge.py"
    small.parent.mkdir(parents=True)
    _ = small.write_text("def small() -> str:\n    return 'ok'\n")
    _write_oversized_python(huge)
    _guard_oversized_reads(monkeypatch, huge)

    inventory = build_file_inventory(repo)
    indexed = RepoIndexService(repo).index_repo()
    paths = {item.path for item in inventory}

    assert "src/small.py" in paths
    assert "src/huge.py" not in paths
    assert set(indexed.file_hashes) == {"src/small.py"}


def test_search_content_skips_oversized_files_and_keeps_small_matches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    small = repo / "src" / "small.py"
    huge = repo / "src" / "huge.py"
    small.parent.mkdir(parents=True)
    _ = small.write_text("def small() -> str:\n    return 'needle'\n")
    _write_oversized_python(huge, marker="needle")
    _guard_oversized_reads(monkeypatch, huge)

    results = SearchService(repo).search_content("needle", limit=20)

    assert tuple(result["path"] for result in results) == ("src/small.py",)
    assert all(result["snippet"] for result in results)


def test_source_range_returns_bounded_payload_for_oversized_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    huge = repo / "src" / "huge.py"
    huge.parent.mkdir(parents=True)
    _write_oversized_python(huge)
    _guard_oversized_reads(monkeypatch, huge)

    result = source_range(
        repo,
        "src/huge.py",
        start_line=1,
        end_line=100,
        line_cap=3,
    )

    assert result.path == "src/huge.py"
    assert result.end_line - result.start_line + 1 <= 3
    assert len(result.source.encode()) <= MAX_OMITTED_SOURCE_BYTES


def test_code_health_scans_skip_oversized_python_and_typescript_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    python_small = repo / "src" / "config.py"
    python_huge = repo / "src" / "huge.py"
    ts_small = repo / "components" / "TaskList.tsx"
    ts_huge = repo / "components" / "HugePanel.tsx"
    python_small.parent.mkdir(parents=True)
    ts_small.parent.mkdir(parents=True)
    _ = python_small.write_text(
        """def load_config() -> dict[str, str]:
    # TODO: split config
    # FIXME: preserve compatibility
    # HACK: keep old queue name
    return {"status": "ok"}
""",
    )
    _ = ts_small.write_text(
        """export function TaskList() {
  const first = "one";
  const second = "two";
  const third = "three";
  const fourth = "four";
  const fifth = "five";
  const sixth = "six";
  const seventh = "seven";
  const eighth = "eight";
  const ninth = "nine";
  const tenth = "ten";
  const eleventh = "eleven";
  return (
    first + second + third + fourth + fifth + sixth + seventh + eighth + ninth
    + tenth + eleventh
  );
}
""",
    )
    _write_oversized_python(python_huge)
    _write_oversized_typescript(ts_huge)
    _guard_oversized_reads(monkeypatch, python_huge, ts_huge)

    ConfigService(repo).save(
        ProjectConfig(thresholds=MaintainabilityThresholds.strict()),
    )
    result = CodeHealthService(repo).scan()
    by_rule = {finding.rule_id: finding for finding in result.findings}
    finding_paths = {finding.file_path for finding in result.findings}

    assert by_rule["python.todo_cluster"].file_path == "src/config.py"
    assert by_rule["typescript.large_component"].file_path == (
        "components/TaskList.tsx"
    )
    assert "src/huge.py" not in finding_paths
    assert "components/HugePanel.tsx" not in finding_paths


def _guard_oversized_reads(
    monkeypatch: pytest.MonkeyPatch,
    *oversized_paths: Path,
) -> None:
    oversized = {path.resolve() for path in oversized_paths}
    original_read_text: ReadText = Path.read_text
    original_read_bytes: ReadBytes = Path.read_bytes

    def guarded_read_text(
        self: Path,
        encoding: str | None = None,
        errors: str | None = None,
    ) -> str:
        if self.resolve() in oversized:
            raise OversizedSourceReadError
        return original_read_text(self, encoding, errors)

    def guarded_read_bytes(self: Path) -> bytes:
        if self.resolve() in oversized:
            raise OversizedSourceReadError
        return original_read_bytes(self)

    monkeypatch.setattr(Path, "read_text", guarded_read_text)
    monkeypatch.setattr(Path, "read_bytes", guarded_read_bytes)


def _write_oversized_python(path: Path, *, marker: str = "payload") -> None:
    _ = path.write_text(
        f"def huge() -> str:\n    return '{marker}{'x' * OVERSIZED_SOURCE_BYTES}'\n",
    )


def _write_oversized_typescript(path: Path) -> None:
    source = "\n".join(
        (
            "export function HugePanel() {",
            f"  return '{'x' * OVERSIZED_SOURCE_BYTES}';",
            "}",
            "",
        ),
    )
    _ = path.write_text(source)
