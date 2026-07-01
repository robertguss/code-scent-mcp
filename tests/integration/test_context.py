import subprocess
from pathlib import Path
from typing import ClassVar

import pytest
from pydantic import BaseModel, ConfigDict, Field

from codescent.services.cbm_backend import CbmGraphBackend
from codescent.services.context import ContextService
from codescent.services.context_support import related_file_payload
from codescent.services.graph_backend import (
    CallEdge,
    Cluster,
    ComplexityProps,
    NativeGraphBackend,
    SymbolNode,
)
from codescent.services.repo_index import RepoIndexService


class SourceRangePayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    path: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    source: str


class FileContextPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    path: str
    summary: str
    symbols: tuple[str, ...]
    imports: tuple[str, ...]
    likely_tests: tuple[str, ...]
    related_files: tuple[str, ...]
    source_ranges: tuple[SourceRangePayload, ...]
    risk_notes: tuple[str, ...]
    next_tools: tuple[str, ...]
    warnings: tuple[str, ...]
    confidence: str
    index_fresh: bool
    index_was_stale: bool
    auto_refreshed: bool
    changed_files: tuple[str, ...]
    refresh_error: str | None


class SymbolSearchPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    name: str
    qualified_name: str
    path: str
    start_line: int
    end_line: int
    confidence: float


class SymbolContextPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    symbol: SymbolSearchPayload
    likely_tests: tuple[str, ...]
    source_ranges: tuple[SourceRangePayload, ...]
    risk_notes: tuple[str, ...]
    warnings: tuple[str, ...]
    confidence: str
    index_fresh: bool
    index_was_stale: bool
    auto_refreshed: bool
    changed_files: tuple[str, ...]
    refresh_error: str | None


def test_file_context_is_bounded_summary() -> None:
    _ = RepoIndexService("tests/fixtures/python-basic").index_repo()
    context = ContextService("tests/fixtures/python-basic").get_file_context(
        "src/acme_tasks/workflow.py",
    )
    payload = FileContextPayload.model_validate(context)

    assert payload.path == "src/acme_tasks/workflow.py"
    assert "summary" not in payload.summary.lower()
    assert payload.symbols == ("build_daily_plan",)
    assert payload.imports == ("__future__:annotations",)
    assert payload.likely_tests == ("tests/test_workflow.py",)
    assert payload.source_ranges
    assert payload.index_fresh is True
    assert payload.refresh_error is None
    assert payload.confidence in {"high", "medium"}
    assert all(
        source_range.end_line - source_range.start_line + 1 <= 8
        for source_range in payload.source_ranges
    )
    assert "archive completed tickets" not in payload.model_dump_json()
    assert (
        "get_symbol_context:acme_tasks.workflow.build_daily_plan" in payload.next_tools
    )


def test_file_context_related_files_are_broader_than_likely_tests(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "tests").mkdir()
    _ = (repo / "src" / "app.py").write_text(
        "from helper import render\n\ndef run() -> str:\n    return render()\n",
    )
    _ = (repo / "src" / "helper.py").write_text(
        "def render() -> str:\n    return 'ok'\n",
    )
    _ = (repo / "src" / "view.py").write_text(
        "def render_view() -> str:\n    return 'ok'\n",
    )
    _ = (repo / "tests" / "test_app.py").write_text(
        "from app import run\n\ndef test_run() -> None:\n    assert run() == 'ok'\n",
    )
    _git(repo, "init")
    _git(repo, "config", "user.email", "qa@example.invalid")
    _git(repo, "config", "user.name", "QA")
    _git(repo, "add", "src/app.py", "src/helper.py")
    _git(repo, "commit", "-m", "app helper")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "tests and view")

    context = ContextService(repo).get_file_context("src/app.py")
    payload = FileContextPayload.model_validate(context)

    assert payload.likely_tests == ("tests/test_app.py",)
    assert "tests/test_app.py" in payload.related_files
    assert "src/helper.py" in payload.related_files
    assert "src/view.py" in payload.related_files
    assert payload.related_files != payload.likely_tests
    assert any(not path.startswith("tests/") for path in payload.related_files)


def test_symbol_context_includes_likely_tests() -> None:
    service = ContextService("tests/fixtures/python-basic")
    matches = service.find_symbol("build_daily_plan")
    context = service.get_symbol_context("acme_tasks.workflow.build_daily_plan")

    match_payloads = tuple(
        SymbolSearchPayload.model_validate(match) for match in matches
    )
    payload = SymbolContextPayload.model_validate(context)

    assert match_payloads[0].qualified_name == "acme_tasks.workflow.build_daily_plan"
    assert payload.symbol.qualified_name == "acme_tasks.workflow.build_daily_plan"
    assert payload.likely_tests == ("tests/test_workflow.py",)
    assert payload.source_ranges[0].path == "src/acme_tasks/workflow.py"
    assert (
        payload.source_ranges[0].end_line - payload.source_ranges[0].start_line + 1 <= 8
    )
    assert any("low-confidence" in note for note in payload.risk_notes)
    assert payload.index_fresh is True
    assert payload.refresh_error is None


def test_reference_graph_context_is_bounded_and_confidence_labeled() -> None:
    service = ContextService("tests/fixtures/python-basic")

    references = service.find_references("print", limit=1)
    callers = service.find_callers("print", limit=1)
    callees = service.find_callees("build_daily_plan", limit=1)

    assert len(references["results"]) == 1
    assert len(callers["results"]) == 1
    assert len(callees["results"]) == 1
    assert references["next_cursor"] == 1
    assert references["results"][0]["certainty"] in {"low", "medium", "high"}
    assert callers["results"][0]["caller"] is not None
    # R8: build_daily_plan calls only ``list.append`` (a builtin), which is now
    # filtered from callees, leaving the cross-file test call as the sole result.
    assert callees["results"][0]["text"] != "append"
    assert callees["results"][0]["path"] == "tests/test_workflow.py"

    missing = service.find_references("not_a_real_reference_name", limit=1)

    assert missing["results"] == ()
    assert missing["confidence"] == "low"
    assert any("no graph results found" in warning for warning in missing["warnings"])
    assert "search_files" in missing["next_tools"]
    assert missing["index_fresh"] is True


def _callgraph_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    _ = (repo / "src" / "app.py").write_text(
        """\
def helper() -> int:
    return 1


def caller() -> int:
    values: list[int] = []
    values.append(helper())
    return len(values)


def only_builtins() -> int:
    return len([])
""",
    )
    _ = RepoIndexService(repo).index_repo()
    return repo


def test_find_callees_filters_builtins(tmp_path: Path) -> None:
    callees = ContextService(_callgraph_repo(tmp_path)).find_callees("caller", limit=20)
    texts = {result["text"] for result in callees["results"]}

    assert "helper" in texts
    assert "append" not in texts
    assert "len" not in texts


def test_find_callees_only_builtins_returns_empty(tmp_path: Path) -> None:
    callees = ContextService(_callgraph_repo(tmp_path)).find_callees(
        "only_builtins",
        limit=20,
    )

    assert callees["results"] == ()


def test_find_callers_lifts_resolved_definition_site_above_low(
    tmp_path: Path,
) -> None:
    callers = ContextService(_callgraph_repo(tmp_path)).find_callers("helper", limit=20)
    resolved = [result for result in callers["results"] if result["caller"] is not None]

    assert resolved
    assert all(result["confidence"] > 0.4 for result in resolved)
    assert all(result["certainty"] in {"medium", "high"} for result in resolved)


class _FakeCbmClient:
    """Healthy cbm double: python edges plus one non-Hybrid-LSP edge to tier out."""

    def healthy(self) -> bool:
        return True

    def symbols(self) -> tuple[SymbolNode, ...]:
        return (
            SymbolNode(
                "pkg.mod.caller_fn",
                "caller_fn",
                "function",
                "src/mod.py",
                1,
                5,
                0.9,
                "python",
            ),
            SymbolNode(
                "pkg.mod.helper",
                "helper",
                "function",
                "src/mod.py",
                7,
                9,
                0.9,
                "python",
            ),
        )

    def complexity(self) -> tuple[ComplexityProps, ...]:
        return ()

    def call_edges(self) -> tuple[CallEdge, ...]:
        return (
            CallEdge("src/mod.py", "helper", 3, 0.95, "python"),
            CallEdge("src/mod.py", "len", 4, 0.95, "python"),
            CallEdge("src/legacy/store.exs", "helper", 2, 1.0, "elixir"),
        )

    def clusters(self) -> tuple[Cluster, ...]:
        return ()


def _repo_for_freshness(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    _ = (repo / "src" / "mod.py").write_text(
        """\
def caller_fn() -> int:
    helper()
    return 1


def helper() -> int:
    return 1
""",
    )
    _ = RepoIndexService(repo).index_repo()
    return repo


def _use_fake_cbm(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_backend(repo_root: Path | str) -> CbmGraphBackend:
        return CbmGraphBackend(
            client=_FakeCbmClient(),
            native=NativeGraphBackend(repo_root=repo_root),
        )

    monkeypatch.setattr(
        "codescent.services.context.select_graph_backend",
        _fake_backend,
    )


def test_find_callers_uses_cbm_call_graph_when_present(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _repo_for_freshness(tmp_path)
    _use_fake_cbm(monkeypatch)

    callers = ContextService(repo).find_callers("helper", limit=20)
    results = callers["results"]

    assert results
    # cbm-sourced: high confidence (0.95), caller resolved from cbm symbols...
    assert results[0]["text"] == "helper"
    assert results[0]["caller"] == "pkg.mod.caller_fn"
    assert results[0]["certainty"] == "high"
    # ...and the non-Hybrid-LSP (elixir) edge is tiered out, never contaminating.
    assert all(result["path"] != "src/legacy/store.exs" for result in results)


def test_find_callees_uses_cbm_call_graph_and_filters_builtins(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _repo_for_freshness(tmp_path)
    _use_fake_cbm(monkeypatch)

    callees = ContextService(repo).find_callees("caller_fn", limit=20)
    texts = {result["text"] for result in callees["results"]}

    assert "helper" in texts
    assert "len" not in texts


def test_find_callees_native_branch_applies_builtin_filter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _callgraph_repo(tmp_path)

    # Force the native backend: cbm-absent behavior is byte-for-byte U6.
    def _force_native(repo_root: Path | str) -> NativeGraphBackend:
        return NativeGraphBackend(repo_root=repo_root)

    monkeypatch.setattr(
        "codescent.services.context.select_graph_backend",
        _force_native,
    )

    callees = ContextService(repo).find_callees("caller", limit=20)
    texts = {result["text"] for result in callees["results"]}

    assert "helper" in texts
    assert "append" not in texts
    assert "len" not in texts


class _NestedCbmClient:
    """cbm double where a method nests inside a class the query also matches."""

    def healthy(self) -> bool:
        return True

    def symbols(self) -> tuple[SymbolNode, ...]:
        return (
            SymbolNode("Worker", "Worker", "class", "src/mod.py", 1, 20, 0.9, "python"),
            SymbolNode(
                "Worker.run", "run", "method", "src/mod.py", 2, 20, 0.9, "python"
            ),
        )

    def complexity(self) -> tuple[ComplexityProps, ...]:
        return ()

    def call_edges(self) -> tuple[CallEdge, ...]:
        return (CallEdge("src/mod.py", "foo", 5, 0.9, "python"),)

    def clusters(self) -> tuple[Cluster, ...]:
        return ()


def test_find_callees_cbm_attributes_edge_to_innermost_symbol(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _repo_for_freshness(tmp_path)

    def _nested(repo_root: Path | str) -> CbmGraphBackend:
        return CbmGraphBackend(
            client=_NestedCbmClient(),
            native=NativeGraphBackend(repo_root=repo_root),
        )

    monkeypatch.setattr(
        "codescent.services.context.select_graph_backend",
        _nested,
    )

    callees = ContextService(repo).find_callees("worker", limit=20)
    callers = [
        result["caller"] for result in callees["results"] if result["text"] == "foo"
    ]

    # The foo() call at line 5 sits inside both Worker (1-20) and Worker.run
    # (2-20); it must be attributed once, to the innermost symbol -- not emitted
    # again for the enclosing class (which would diverge from the native path).
    assert callers == ["Worker.run"]


def test_related_files_include_import_test_directory_and_git_reasons(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "tests").mkdir()
    _ = (repo / "src" / "app.py").write_text(
        "from helper import render\n\ndef run() -> str:\n    return render()\n",
    )
    _ = (repo / "src" / "helper.py").write_text(
        "def render() -> str:\n    return 'ok'\n",
    )
    _ = (repo / "src" / "view.py").write_text(
        "def render_view() -> str:\n    return 'ok'\n",
    )
    _ = (repo / "tests" / "test_app.py").write_text(
        "from app import run\n\ndef test_run() -> None:\n    assert run() == 'ok'\n",
    )
    _git(repo, "init")
    _git(repo, "config", "user.email", "qa@example.invalid")
    _git(repo, "config", "user.name", "QA")
    _git(repo, "add", "src/app.py", "src/helper.py")
    _git(repo, "commit", "-m", "app helper")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "tests and view")

    related = ContextService(repo).get_related_files("src/app.py", limit=10)
    by_path = {item["path"]: item for item in related["results"]}

    assert related["next_cursor"] is None
    assert "test_match" in by_path["tests/test_app.py"]["reasons"]
    assert "import_graph" in by_path["tests/test_app.py"]["reasons"]
    assert "git_history" in by_path["src/helper.py"]["reasons"]
    assert "co_change" in by_path["src/helper.py"]["reasons"]
    assert "directory_proximity" in by_path["src/view.py"]["reasons"]
    assert any("search_similarity" in item["reasons"] for item in related["results"])
    assert all(0 <= item["confidence"] <= 1 for item in related["results"])


def test_co_change_reason_weight_sits_between_git_and_import() -> None:
    git_history = related_file_payload(path="peer.py", reasons={"git_history"})
    co_change = related_file_payload(path="peer.py", reasons={"co_change"})
    import_graph = related_file_payload(path="peer.py", reasons={"import_graph"})

    assert git_history["confidence"] < co_change["confidence"]
    assert co_change["confidence"] < import_graph["confidence"]
    assert co_change["reasons"] == ("co_change",)


def test_context_hot_paths_use_persisted_index_after_indexing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    _ = (repo / "src" / "app.py").write_text(
        "from helper import render\n\n\ndef run() -> str:\n    return render()\n",
    )
    _ = (repo / "src" / "helper.py").write_text(
        "def render() -> str:\n    return 'ok'\n",
    )

    _ = RepoIndexService(repo).index_repo()

    def fail_reparse(*_args: object, **_kwargs: object) -> object:
        message = "context lookup reparsed the repo after indexing"
        raise AssertionError(message)

    monkeypatch.setattr("codescent.services.symbols.build_pack_registry", fail_reparse)

    service = ContextService(repo)
    matches = service.find_symbol("run")

    assert matches
    context = service.get_symbol_context(matches[0]["qualified_name"])
    file_context = service.get_file_context("src/app.py")
    related = service.get_related_files("src/app.py")
    related_by_path = {item["path"]: item for item in related["results"]}

    assert context["symbol"]["qualified_name"] == matches[0]["qualified_name"]
    assert file_context["path"] == "src/app.py"
    assert file_context["symbols"] == ("run",)
    assert file_context["imports"] == ("helper:render",)
    assert "import_graph" in related_by_path["src/helper.py"]["reasons"]


def test_context_auto_refreshes_unindexed_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    _ = (repo / "src" / "app.py").write_text(
        "def run() -> str:\n    return 'ok'\n",
    )

    service = ContextService(repo)

    file_context = FileContextPayload.model_validate(
        service.get_file_context("src/app.py"),
    )
    matches = service.find_symbol("run")

    assert matches[0]["qualified_name"] == "app.run"
    assert file_context.index_fresh is True
    assert file_context.index_was_stale is True
    assert file_context.auto_refreshed is True
    assert file_context.refresh_error is None
    assert file_context.symbols == ("run",)
    assert (repo / ".codescent" / "index.sqlite").exists()


def _repo_with_many_related(tmp_path: Path, sibling_count: int) -> Path:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    _ = (repo / "src" / "app.py").write_text(
        "def run() -> str:\n    return 'ok'\n",
    )
    for index in range(sibling_count):
        _ = (repo / "src" / f"mod{index:02d}.py").write_text(
            f"def helper_{index:02d}() -> int:\n    return {index}\n",
        )
    _ = RepoIndexService(repo).index_repo()
    return repo


def test_file_context_related_files_bounded_and_paginated(tmp_path: Path) -> None:
    repo = _repo_with_many_related(tmp_path, sibling_count=25)
    service = ContextService(repo)

    first = service.get_file_context("src/app.py")
    assert len(first["related_files"]) == 20
    assert first["related_files_next_cursor"] == 20

    second = service.get_file_context("src/app.py", related_cursor=20)
    assert second["related_files_next_cursor"] is None
    assert 0 < len(second["related_files"]) <= 20
    assert not set(first["related_files"]) & set(second["related_files"])


def test_file_context_related_files_under_cap_returns_all(tmp_path: Path) -> None:
    repo = _repo_with_many_related(tmp_path, sibling_count=3)
    context = ContextService(repo).get_file_context("src/app.py")

    assert context["related_files_next_cursor"] is None
    assert len(context["related_files"]) == 3


def test_file_context_top_page_matches_get_related_files(tmp_path: Path) -> None:
    repo = _repo_with_many_related(tmp_path, sibling_count=25)
    service = ContextService(repo)

    file_context = service.get_file_context("src/app.py")
    related = service.get_related_files("src/app.py", limit=20)

    assert file_context["related_files"] == tuple(
        item["path"] for item in related["results"]
    )


def _git(repo: Path, *args: str) -> None:
    _ = subprocess.run(["git", *args], cwd=repo, check=True)
