"""Contract tests for the `refactor_preflight` MCP tool: surface, docs, payload."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import ClassVar

import pytest
from fastmcp import Client
from mcp.types import ContentBlock, TextContent
from pydantic import BaseModel, ConfigDict

from codescent.core.public_surface import registered_mcp_tool_names
from codescent.mcp.server import mcp
from codescent.services.code_health import CodeHealthService
from codescent.services.refactor_preflight import SECTION_ITEM_CAP

DOCS = Path("docs/mcp-tools.md")
CORE = "src/pkg/core.py"


class ImpactModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    ok: bool
    target_type: str
    target: str
    affected_files: tuple[str, ...]
    likely_tests: tuple[str, ...]
    risk_notes: tuple[str, ...]
    confidence: float


class CoChangeModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    path: str
    commits: int


class SelectionModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    ok: bool
    changed_files: tuple[str, ...]
    test_files: tuple[str, ...]
    command: str
    executes_in_v1: bool


class HealthModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="allow")

    ok: bool
    path: str
    risk_score: float
    risk_level: str
    finding_ids: tuple[str, ...]
    suggested_tests: tuple[str, ...]
    recommended_commands: tuple[str, ...]
    risk_notes: tuple[str, ...]


class PreflightModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    ok: bool
    target_type: str
    target: str
    file_path: str
    impact: ImpactModel
    co_change: tuple[CoChangeModel, ...]
    test_selection: SelectionModel
    changed_file_health: HealthModel
    warnings: tuple[str, ...]
    next_tools: tuple[str, ...]


def test_refactor_preflight_is_registered_and_documented() -> None:
    assert "refactor_preflight" in registered_mcp_tool_names()
    assert "### `refactor_preflight`" in DOCS.read_text()


def test_refactor_preflight_docs_state_bounds_wording() -> None:
    text = DOCS.read_text()
    section = text.split("### `refactor_preflight`", maxsplit=1)[1].split(
        "\n### `",
        maxsplit=1,
    )[0]
    # Collapse prose-wrap so asserted phrases cannot be split across line breaks.
    collapsed = re.sub(r"\s+", " ", section)
    assert "most restrictive existing component cap" in collapsed
    assert "git co-change tops out at 10" in collapsed
    assert "source-read-only" in collapsed
    assert "no new analysis" in collapsed.lower()


@pytest.mark.anyio
async def test_refactor_preflight_listed_with_composition_description() -> None:
    async with Client(mcp) as client:
        tools = await client.list_tools()

    tool = {item.name: item for item in tools}["refactor_preflight"]
    description = tool.description or ""

    assert "refactor preflight" in description.lower()
    assert "read-only" in description.lower()


@pytest.mark.anyio
async def test_refactor_preflight_returns_bounded_bundle(tmp_path: Path) -> None:
    repo = _build_coupled_repo(tmp_path)
    _ = CodeHealthService(repo).scan()

    async with Client(mcp) as client:
        result = await client.call_tool(
            "refactor_preflight",
            {"repo": str(repo), "target": CORE, "target_type": "file"},
        )

    payload_json = _text_content(result.content)
    payload = PreflightModel.model_validate_json(payload_json)

    assert payload.ok is True
    assert payload.file_path == CORE
    # All four sections are present and carry the real component fields.
    assert CORE in payload.impact.affected_files
    assert payload.impact.target_type == "file"
    co_change_paths = {entry.path for entry in payload.co_change}
    assert "src/pkg/caller.py" in co_change_paths
    assert all(entry.commits >= 1 for entry in payload.co_change)
    assert payload.test_selection.executes_in_v1 is False
    assert payload.changed_file_health.path == CORE
    # Bounded: every list section honors the most restrictive cap.
    assert len(payload.co_change) <= SECTION_ITEM_CAP
    assert len(payload.impact.affected_files) <= SECTION_ITEM_CAP
    assert len(payload.test_selection.test_files) <= SECTION_ITEM_CAP
    assert len(payload.changed_file_health.finding_ids) <= SECTION_ITEM_CAP
    # No source content leaks through the adapter.
    assert "def compute" not in payload_json


def _build_coupled_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    _write(repo / "src" / "pkg" / "__init__.py", "")
    _write(repo / CORE, "def compute(value):\n    return value + 1\n")
    _write(
        repo / "src" / "pkg" / "caller.py",
        "from pkg.core import compute\n\n\ndef run(v):\n    return compute(v)\n",
    )
    _write(
        repo / "tests" / "test_core.py",
        "from pkg.core import compute\n\n\ndef test_x():\n    assert compute(1)\n",
    )
    _git(repo, "init")
    _git(repo, "config", "user.email", "qa@example.invalid")
    _git(repo, "config", "user.name", "QA")
    _commit(repo, "core+caller", "src/pkg/__init__.py", CORE, "src/pkg/caller.py")
    _write(repo / CORE, "def compute(value):\n    return value + 2\n")
    _commit(repo, "core again", CORE, "src/pkg/caller.py")
    return repo


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(content)


def _commit(repo: Path, message: str, *paths: str) -> None:
    _git(repo, "add", *paths)
    _git(repo, "commit", "-m", message)


def _git(repo: Path, *args: str) -> None:
    _ = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def _text_content(content: list[ContentBlock]) -> str:
    assert len(content) == 1
    first = content[0]
    assert isinstance(first, TextContent)
    return first.text
