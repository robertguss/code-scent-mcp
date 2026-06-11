from pathlib import Path
from typing import ClassVar

import pytest
from fastmcp import Client
from mcp.types import ContentBlock, TextContent
from pydantic import BaseModel, ConfigDict, Field

from codescent.mcp.server import mcp


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


@pytest.mark.anyio
async def test_mcp_lists_repo_tools() -> None:
    async with Client(mcp) as client:
        tools = await client.list_tools()

    repo_tools = {tool.name: tool for tool in tools}

    assert {"get_repo_map", "get_repo_status"} <= repo_tools.keys()
    for tool_name in ("get_repo_map", "get_repo_status"):
        description = repo_tools[tool_name].description or ""
        assert "CodeScent before broad grep" in description
        assert "large reads" in description
        assert "read-only" in description


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


def _text_content(content: list[ContentBlock]) -> str:
    assert len(content) == 1
    first = content[0]
    assert isinstance(first, TextContent)
    return first.text
