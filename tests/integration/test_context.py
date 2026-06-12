import subprocess
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from codescent.services.context import ContextService


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


def test_file_context_is_bounded_summary() -> None:
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
    assert all(
        source_range.end_line - source_range.start_line + 1 <= 8
        for source_range in payload.source_ranges
    )
    assert "archive completed tickets" not in payload.model_dump_json()
    assert (
        "get_symbol_context:acme_tasks.workflow.build_daily_plan" in payload.next_tools
    )


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
    assert callees["results"][0]["path"] == "src/acme_tasks/workflow.py"


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
    assert "directory_proximity" in by_path["src/view.py"]["reasons"]
    assert any("search_similarity" in item["reasons"] for item in related["results"])
    assert all(0 <= item["confidence"] <= 1 for item in related["results"])


def _git(repo: Path, *args: str) -> None:
    _ = subprocess.run(["git", *args], cwd=repo, check=True)
