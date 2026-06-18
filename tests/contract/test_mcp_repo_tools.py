from pathlib import Path
from typing import ClassVar

import pytest
from fastmcp import Client
from mcp.types import ContentBlock, TextContent
from pydantic import BaseModel, ConfigDict, Field

from codescent.mcp.server import mcp
from codescent.services.code_health import CodeHealthService


class RepoMapPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(
        frozen=True,
        from_attributes=True,
    )

    ok: bool
    read_only: bool
    file_count: int = Field(ge=0)
    test_file_count: int = Field(ge=0)
    languages: dict[str, int]
    top_level: tuple[str, ...]
    entrypoints: tuple[str, ...]
    sample_files: tuple[str, ...]


class RepoStatusPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(
        frozen=True,
        from_attributes=True,
    )

    ok: bool
    read_only: bool
    index_fresh: bool
    indexed_files: int = Field(ge=0)
    changed_files: tuple[str, ...]
    finding_count: int = Field(ge=0)
    database_ok: bool
    git_available: bool
    git_status: str


class StartTaskPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    ok: bool
    query: str
    relevant_files: tuple[str, ...]
    relevant_symbols: tuple[str, ...]
    related_tests: tuple[str, ...]
    open_findings: tuple[dict[str, str], ...]
    index_fresh: bool
    index_was_stale: bool
    auto_refreshed: bool
    changed_files: tuple[str, ...]
    refresh_error: str | None
    warnings: tuple[str, ...]
    confidence: str
    next_tools: tuple[str, ...]


@pytest.mark.anyio
async def test_mcp_lists_repo_tools() -> None:
    async with Client(mcp) as client:
        tools = await client.list_tools()

    repo_tools = {tool.name: tool for tool in tools}

    assert {"get_repo_map", "get_repo_status", "start_task"} <= repo_tools.keys()
    for tool_name in ("get_repo_map", "get_repo_status"):
        description = repo_tools[tool_name].description or ""
        assert "CodeScent before broad grep" in description
        assert "large reads" in description
        assert "read-only" in description
    start_task_description = repo_tools["start_task"].description or ""
    assert "CodeScent FIRST" in start_task_description
    assert "bounded brief" in start_task_description
    assert "auto-refresh metadata" in start_task_description
    assert "Read-only" in start_task_description


@pytest.mark.anyio
async def test_get_repo_map_and_status_are_bounded(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = repo / "src" / "acme" / "cli.py"
    test_file = repo / "tests" / "test_cli.py"
    source.parent.mkdir(parents=True)
    test_file.parent.mkdir()
    _ = source.write_text("SECRET_SENTINEL = 'do not leak source'\n")
    _ = test_file.write_text("def test_cli() -> None:\n    assert True\n")

    async with Client(mcp) as client:
        map_result = await client.call_tool("get_repo_map", {"repo": str(repo)})
        status_result = await client.call_tool("get_repo_status", {"repo": str(repo)})

    repo_map = RepoMapPayload.model_validate_json(_text_content(map_result.content))
    repo_status = RepoStatusPayload.model_validate_json(
        _text_content(status_result.content),
    )

    assert repo_map.ok is True
    assert repo_map.read_only is True
    assert repo_map.file_count == 2
    assert repo_map.test_file_count == 1
    assert repo_map.languages == {"python": 2}
    assert repo_map.top_level == ("src", "tests")
    assert repo_map.entrypoints == ("src/acme/cli.py",)
    assert set(repo_map.sample_files) == {
        "src/acme/cli.py",
        "tests/test_cli.py",
    }
    assert "SECRET_SENTINEL" not in repo_map.model_dump_json()

    assert repo_status.ok is True
    assert repo_status.read_only is True
    assert repo_status.index_fresh is False
    assert repo_status.indexed_files == 0
    assert repo_status.changed_files == (
        "src/acme/cli.py",
        "tests/test_cli.py",
    )
    assert repo_status.database_ok is False
    assert not (repo / ".codescent").exists()


@pytest.mark.anyio
async def test_start_task_returns_useful_bounded_brief(tmp_path: Path) -> None:
    repo = _repo_with_task_target(tmp_path)
    _ = CodeHealthService(repo).scan()

    async with Client(mcp) as client:
        result = await client.call_tool(
            "start_task",
            {
                "repo": str(repo),
                "query": "do thing",
                "focus_path": "src/app/x.py",
            },
        )

    payload = StartTaskPayload.model_validate_json(_text_content(result.content))

    assert payload.ok is True
    assert payload.query == "do thing"
    assert "src/app/x.py" in payload.relevant_files
    assert "app.x.do_thing" in payload.relevant_symbols
    assert payload.related_tests == ("tests/test_x.py",)
    assert any(
        finding["file_path"] == "src/app/x.py" for finding in payload.open_findings
    )
    assert payload.index_fresh is True
    assert payload.index_was_stale is False
    assert payload.auto_refreshed is False
    assert payload.refresh_error is None
    assert payload.confidence == "high"
    assert payload.warnings == ()
    assert "select_tests" in payload.next_tools
    assert len(payload.relevant_files) <= 8
    assert len(payload.relevant_symbols) <= 12
    assert len(payload.related_tests) <= 8
    assert len(payload.open_findings) <= 10
    assert "TODO" not in payload.model_dump_json()


@pytest.mark.anyio
async def test_start_task_auto_refreshes_stale_index(tmp_path: Path) -> None:
    repo = _repo_with_task_target(tmp_path)

    async with Client(mcp) as client:
        result = await client.call_tool(
            "start_task",
            {
                "repo": str(repo),
                "query": "do thing",
                "focus_path": "src/app/x.py",
            },
        )

    payload = StartTaskPayload.model_validate_json(_text_content(result.content))

    assert payload.ok is True
    assert payload.index_fresh is True
    assert payload.index_was_stale is True
    assert payload.auto_refreshed is True
    assert payload.refresh_error is None
    assert set(payload.changed_files) == {"src/app/x.py", "tests/test_x.py"}
    assert "src/app/x.py" in payload.relevant_files
    assert "app.x.do_thing" in payload.relevant_symbols
    assert payload.confidence == "medium"
    assert any("automatically refreshed" in warning for warning in payload.warnings)


def _repo_with_task_target(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    source = repo / "src" / "app" / "x.py"
    test = repo / "tests" / "test_x.py"
    source.parent.mkdir(parents=True)
    test.parent.mkdir()
    _ = source.write_text(
        """def do_thing() -> str:
    # TODO: split orchestration
    # FIXME: keep compatibility
    # HACK: preserve old behavior
    return "done"
""",
    )
    _ = test.write_text(
        """from app.x import do_thing


def test_do_thing() -> None:
    assert do_thing() == "done"
""",
    )
    return repo


def _text_content(content: list[ContentBlock]) -> str:
    assert len(content) == 1
    first = content[0]
    assert isinstance(first, TextContent)
    return first.text
