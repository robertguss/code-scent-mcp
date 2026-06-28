import json
import logging
from pathlib import Path
from typing import ClassVar, cast

import pytest
from fastmcp import Client
from mcp.types import ContentBlock, TextContent
from pydantic import BaseModel, ConfigDict

from codescent.core.public_surface import registered_mcp_tool_names
from codescent.mcp.server import mcp
from codescent.services.explain import EXPLAIN_SNIPPET_LINE_CAP, MAX_SNIPPET_CHARS

logger = logging.getLogger(__name__)


class SnippetModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="allow")

    path: str
    start_line: int
    end_line: int
    source: str


class ExplainPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="allow")

    ok: bool
    finding_id: str
    rule_id: str
    confidence_tier: str
    why: str
    fix: str
    snippet: SnippetModel
    snippet_truncated: bool


def _repo_with_dead_code(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    module = repo / "pkg" / "mod.py"
    module.parent.mkdir(parents=True)
    body = "\n".join(f"    # filler {index}" for index in range(60))
    _ = module.write_text(f"def unused_helper() -> int:\n{body}\n    return 0\n")
    return repo


def _text_content(content: list[ContentBlock]) -> str:
    assert len(content) == 1
    first = content[0]
    assert isinstance(first, TextContent)
    return first.text


def _dead_code_finding_id(content: list[ContentBlock]) -> str:
    payload = cast("dict[str, object]", json.loads(_text_content(content)))
    items = payload.get("items")
    assert isinstance(items, list)
    for raw in cast("list[object]", items):
        assert isinstance(raw, dict)
        item = cast("dict[str, object]", raw)
        if item.get("rule_id") == "python.dead_code_candidate":
            finding_id = item.get("finding_id")
            assert isinstance(finding_id, str)
            return finding_id
    msg = "scan did not surface a dead_code_candidate finding"
    raise AssertionError(msg)


def test_explain_finding_is_in_registered_surface() -> None:
    assert "explain_finding" in registered_mcp_tool_names()


@pytest.mark.anyio
async def test_explain_finding_e2e_returns_bounded_why_fix_snippet(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger=logger.name)
    repo = _repo_with_dead_code(tmp_path)

    async with Client(mcp) as client:
        tools = await client.list_tools()
        scan_raw = await client.call_tool("scan_code_health", {"repo": str(repo)})
        finding_id = _dead_code_finding_id(scan_raw.content)
        logger.info("e2e: scanned %s -> finding_id=%s", repo, finding_id)
        explain_raw = await client.call_tool(
            "explain_finding",
            {"repo": str(repo), "finding_id": finding_id},
        )

    assert "explain_finding" in {tool.name for tool in tools}
    payload = ExplainPayload.model_validate_json(_text_content(explain_raw.content))
    snippet_lines = payload.snippet.source.count("\n") + 1
    logger.info(
        "e2e: explain_finding ok=%s rule=%s snippet_lines=%d why_len=%d fix_len=%d",
        payload.ok,
        payload.rule_id,
        snippet_lines,
        len(payload.why),
        len(payload.fix),
    )

    # One bounded payload combining why + fix + a bounded source snippet.
    assert payload.ok is True
    assert payload.finding_id == finding_id
    assert payload.why  # why it matters (finding message)
    assert payload.fix  # suggested fix (suggested_action)
    assert payload.snippet.source  # bounded source snippet
    assert payload.confidence_tier in {"verified", "heuristic"}
    # Bounded: clipped, never an unbounded source dump.
    assert len(payload.snippet.source) <= MAX_SNIPPET_CHARS
    span = payload.snippet.end_line - payload.snippet.start_line + 1
    assert span <= EXPLAIN_SNIPPET_LINE_CAP
    # Verbose e2e logging actually happened.
    assert any(
        "explain_finding ok=" in record.getMessage() for record in caplog.records
    )
