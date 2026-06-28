from pathlib import Path
from typing import ClassVar

import pytest
from fastmcp import Client
from mcp.types import ContentBlock, TextContent
from pydantic import BaseModel, ConfigDict

from codescent.mcp.server import mcp
from codescent.services.code_health import CodeHealthService


class FindingContextPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    ok: bool
    finding_id: str
    affected_files: tuple[str, ...]
    relevant_tests: tuple[str, ...]
    source_ranges: tuple[dict[str, str | int], ...]
    next_tools: tuple[str, ...]


class RefactorPlanPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    ok: bool
    goal: str
    non_goals: tuple[str, ...]
    affected_files: tuple[str, ...]
    verification_recommendations: tuple[str, ...]


class SuggestedTestsPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    ok: bool
    commands: tuple[str, ...]
    likely_tests: tuple[str, ...]
    executes_in_v1: bool


class ScaffoldFieldPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    language: str
    module: str
    symbol: str
    test_name: str
    filename: str
    code: str
    honest: bool
    notes: tuple[str, ...]


class SuggestedTestsWithScaffoldPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    ok: bool
    scaffold: ScaffoldFieldPayload | None = None


class SelectTestsPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    ok: bool
    changed_files: tuple[str, ...]
    test_files: tuple[str, ...]
    command: str
    executes_in_v1: bool


class VerifyChangePayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    ok: bool
    executes: bool
    recommendation_id: int
    recommended_commands: tuple[str, ...]
    likely_tests: tuple[str, ...]
    missing_characterization_tests: tuple[str, ...]


class ImpactPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    ok: bool
    target_type: str
    target: str
    affected_files: tuple[str, ...]
    likely_tests: tuple[str, ...]
    risk_notes: tuple[str, ...]
    confidence: float


@pytest.mark.anyio
async def test_planning_tools_are_bounded_and_do_not_execute(tmp_path: Path) -> None:
    repo = _repo_with_smell(tmp_path)
    scan = CodeHealthService(repo).scan()
    finding_id = next(
        item for item in scan.finding_ids if item.startswith("python.todo_cluster")
    )

    async with Client(mcp) as client:
        tools = await client.list_tools()
        context_result = await client.call_tool(
            "get_finding_context",
            {"repo": str(repo), "finding_id": finding_id},
        )
        plan_result = await client.call_tool(
            "plan_refactor",
            {"repo": str(repo), "finding_id": finding_id},
        )
        tests_result = await client.call_tool(
            "suggest_tests",
            {"repo": str(repo), "finding_id": finding_id},
        )
        selected_tests_result = await client.call_tool(
            "select_tests",
            {"repo": str(repo), "paths": ["src/pkg/config.py"]},
        )

    tool_names = {tool.name for tool in tools}
    assert {
        "get_finding_context",
        "plan_refactor",
        "suggest_tests",
        "select_tests",
    } <= tool_names

    context = FindingContextPayload.model_validate_json(
        _text_content(context_result.content),
    )
    plan = RefactorPlanPayload.model_validate_json(_text_content(plan_result.content))
    suggested = SuggestedTestsPayload.model_validate_json(
        _text_content(tests_result.content),
    )
    selected = SelectTestsPayload.model_validate_json(
        _text_content(selected_tests_result.content),
    )

    assert context.ok is True
    assert context.affected_files == ("src/pkg/config.py",)
    assert context.relevant_tests == ("tests/test_config.py",)
    assert context.source_ranges
    assert "plan_refactor" in context.next_tools
    assert "SECRET_SENTINEL" not in context.model_dump_json()
    assert plan.ok is True
    assert plan.non_goals
    assert plan.verification_recommendations == ("pytest tests/test_config.py",)
    assert suggested.ok is True
    assert suggested.executes_in_v1 is False
    assert selected.ok is True
    assert selected.changed_files == ("src/pkg/config.py",)
    assert selected.test_files == ("tests/test_config.py",)
    assert selected.command == "pytest tests/test_config.py"
    assert selected.executes_in_v1 is False
    assert not (repo / ".pytest_cache").exists()


@pytest.mark.anyio
async def test_get_impact_reports_blast_radius_without_false_certainty(
    tmp_path: Path,
) -> None:
    repo = _repo_with_smell(tmp_path)
    scan = CodeHealthService(repo).scan()
    finding_id = next(
        item for item in scan.finding_ids if item.startswith("python.todo_cluster")
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_impact",
            {"repo": str(repo), "finding_id": finding_id},
        )

    impact = ImpactPayload.model_validate_json(_text_content(result.content))

    assert impact.ok is True
    assert impact.target_type == "finding"
    assert impact.target == finding_id
    assert "src/pkg/config.py" in impact.affected_files
    assert impact.likely_tests == ("tests/test_config.py",)
    assert any("confidence" in note for note in impact.risk_notes)
    assert 0 < impact.confidence < 1
    assert "SECRET_SENTINEL" not in impact.model_dump_json()


@pytest.mark.anyio
async def test_verify_change_records_recommendations_without_execution(
    tmp_path: Path,
) -> None:
    repo = _repo_with_smell(tmp_path)
    scan = CodeHealthService(repo).scan()
    finding_id = next(
        item for item in scan.finding_ids if item.startswith("python.todo_cluster")
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "verify_change",
            {"repo": str(repo), "finding_id": finding_id},
        )

    payload = VerifyChangePayload.model_validate_json(_text_content(result.content))

    assert payload.ok is True
    assert payload.executes is False
    assert payload.recommendation_id > 0
    assert payload.recommended_commands == ("pytest tests/test_config.py",)
    assert payload.likely_tests == ("tests/test_config.py",)
    assert payload.missing_characterization_tests == ()
    assert not (repo / ".pytest_cache").exists()


class VerifyRefactorPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="allow")

    ok: bool
    preserved: bool
    language: str
    changed_symbols: tuple[str, ...]
    violations: tuple[dict[str, str], ...]


@pytest.mark.anyio
async def test_verify_refactor_checks_public_surface(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    _ = (repo / "src" / "config.py").write_text(
        "def load_config(path):\n    return path\n"
    )

    # No git baseline -> nothing to compare against, but it runs and is bounded.
    async with Client(mcp) as client:
        tools = await client.list_tools()
        result = await client.call_tool(
            "verify_refactor",
            {"repo": str(repo), "path": "src/config.py", "base_ref": ""},
        )

    assert "verify_refactor" in {tool.name for tool in tools}
    payload = VerifyRefactorPayload.model_validate_json(_text_content(result.content))
    assert payload.ok is True
    assert payload.language == "python"
    assert payload.preserved is True


@pytest.mark.anyio
async def test_suggest_tests_scaffold_field_is_opt_in_and_honest(
    tmp_path: Path,
) -> None:
    repo = _repo_with_smell(tmp_path)
    scan = CodeHealthService(repo).scan()
    finding_id = next(
        item for item in scan.finding_ids if item.startswith("python.todo_cluster")
    )

    async with Client(mcp) as client:
        default_result = await client.call_tool(
            "suggest_tests",
            {"repo": str(repo), "finding_id": finding_id},
        )
        scaffold_result = await client.call_tool(
            "suggest_tests",
            {"repo": str(repo), "finding_id": finding_id, "scaffold": True},
        )

    # Opt-in: the scaffold field is absent unless requested.
    default_json = _text_content(default_result.content)
    assert '"scaffold"' not in default_json

    payload = SuggestedTestsWithScaffoldPayload.model_validate_json(
        _text_content(scaffold_result.content),
    )
    assert payload.ok is True
    scaffold = payload.scaffold
    assert scaffold is not None
    assert scaffold.language == "python"
    assert scaffold.honest is True
    assert scaffold.filename.startswith("test_")
    # Honest skeleton: imports the target, no fake-green assertion.
    assert "from pkg.config import load_config" in scaffold.code
    assert "raise NotImplementedError(" in scaffold.code
    assert "assert True" not in scaffold.code
    # Bounded: one short skeleton.
    assert scaffold.code.count("def test_") == 1
    assert "SECRET_SENTINEL" not in scaffold.code
    assert not (repo / ".pytest_cache").exists()


def _repo_with_smell(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    source = repo / "src" / "pkg" / "config.py"
    test = repo / "tests" / "test_config.py"
    source.parent.mkdir(parents=True)
    test.parent.mkdir()
    _ = source.write_text(
        """SECRET_SENTINEL = "do not leak"
STATUS = "pending-review"
OTHER_STATUS = "pending-review"
THIRD_STATUS = "pending-review"


def load_config() -> str:
    # TODO: split config
    # FIXME: preserve compatibility
    # HACK: keep old queue name
    return STATUS
""",
    )
    _ = test.write_text(
        """from pkg.config import load_config


def test_load_config() -> None:
    assert load_config() == "pending-review"
""",
    )
    return repo


def _text_content(content: list[ContentBlock]) -> str:
    assert len(content) == 1
    first = content[0]
    assert isinstance(first, TextContent)
    return first.text
