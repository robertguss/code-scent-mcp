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

    tool_names = {tool.name for tool in tools}
    assert {"get_finding_context", "plan_refactor", "suggest_tests"} <= tool_names

    context = FindingContextPayload.model_validate_json(
        _text_content(context_result.content),
    )
    plan = RefactorPlanPayload.model_validate_json(_text_content(plan_result.content))
    suggested = SuggestedTestsPayload.model_validate_json(
        _text_content(tests_result.content),
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
