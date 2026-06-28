"""Contract tests for the `resume_task` MCP tool: surface, docs, and payload."""

from __future__ import annotations

import json
from pathlib import Path
from typing import ClassVar, cast

import pytest
from fastmcp import Client
from mcp.types import ContentBlock, TextContent
from pydantic import BaseModel, ConfigDict

from codescent.core.models import FindingStatus
from codescent.core.public_surface import registered_mcp_tool_names
from codescent.mcp.server import mcp
from codescent.storage import RepositoryStorage, initialize_storage
from codescent.storage.repositories import (
    FindingRepository,
    SessionEventRepository,
    SessionEventWrite,
)

DOCS = Path("docs/mcp-tools.md")
SENTINEL_TEXT = "SECRET_RESUME_SENTINEL"


class RatchetModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    baseline_accepted: bool
    baseline_finding_count: int


class ResumeTaskPayload(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")

    ok: bool
    session_id: str
    status: str
    summary: str
    active_findings: tuple[dict[str, str], ...]
    verified_findings: tuple[dict[str, str], ...]
    recently_touched_files: tuple[str, ...]
    recent_tools: tuple[str, ...]
    ratchet: RatchetModel
    next_tools: tuple[str, ...]


def test_resume_task_is_registered_and_documented() -> None:
    assert "resume_task" in registered_mcp_tool_names()
    assert "### `resume_task`" in DOCS.read_text()


@pytest.mark.anyio
async def test_resume_task_listed_with_resume_description() -> None:
    async with Client(mcp) as client:
        tools = await client.list_tools()

    tool = {item.name: item for item in tools}["resume_task"]
    description = tool.description or ""

    assert "RESUME work after losing context" in description
    assert "reads no analyzed source" in description


@pytest.mark.anyio
async def test_resume_task_returns_bounded_brief_with_expected_fields(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _seed_repo_with_progress(repo)

    async with Client(mcp) as client:
        result = await client.call_tool(
            "resume_task",
            {
                "repo": str(repo),
                "session_id": "session-a",
                "project_id": "project-a",
            },
        )

    payload_json = _text_content(result.content)
    payload = ResumeTaskPayload.model_validate_json(payload_json)

    assert payload.ok is True
    assert payload.session_id == "session-a"
    # The in-flight finding is verified via the ledger -> recommend resolving it.
    assert payload.status == "verified_unresolved"
    assert payload.active_findings[0]["id"] == "fix-me"
    assert set(payload.active_findings[0]) == {
        "id",
        "rule_id",
        "file_path",
        "severity",
        "status",
    }
    assert payload.next_tools[0] == "mark_finding:fix-me"
    assert payload.verified_findings[0]["finding_id"] == "fix-me"
    assert "src/a.py" in payload.recently_touched_files
    assert payload.recent_tools == ("get_finding_context",)
    # No source content leaks into the bounded brief.
    assert SENTINEL_TEXT not in payload_json
    assert "source_content" not in payload_json
    assert len(payload_json) < 5000


@pytest.mark.anyio
async def test_resume_task_empty_repo_is_graceful(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    async with Client(mcp) as client:
        result = await client.call_tool("resume_task", {"repo": str(repo)})

    payload = ResumeTaskPayload.model_validate_json(_text_content(result.content))

    assert payload.ok is True
    assert payload.status == "nothing_in_progress"
    assert payload.active_findings == ()
    assert payload.next_tools == (
        "start_task",
        "get_next_improvement",
        "scan_code_health",
    )


def _seed_repo_with_progress(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    storage = RepositoryStorage(initialize_storage(repo))
    with storage.write_transaction() as connection:
        _ = connection.execute(
            """
            insert or ignore into scan_runs (
                id, started_at, completed_at, index_version, rule_version,
                files_scanned, findings_created, findings_resolved, status
            ) values ('scan', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z',
                1, 'test', 0, 0, 0, 'complete')
            """,
        )
        cursor = connection.execute(
            """
            insert into files (
                path, language, hash, size_bytes, line_count, is_generated, is_test
            ) values ('src/a.py', 'python', 'fix-me', 1, 10, 0, 0)
            """,
        )
        file_id = cursor.lastrowid
        _ = connection.execute(
            """
            insert into findings (
                id, stable_key, rule_id, file_id, severity, confidence, status,
                title, message, evidence_json, suggested_action,
                first_seen_scan_id, last_seen_scan_id
            ) values ('fix-me', 'k', 'python.todo_cluster', ?, 'warning', 0.8,
                'open', 'fix-me', '', '{}', '', 'scan', 'scan')
            """,
            (file_id,),
        )
    findings = FindingRepository(storage)
    _ = findings.update_status(
        "fix-me",
        FindingStatus.IN_PROGRESS,
        note="resumed",
    )
    _ = findings.record_verification(
        "fix-me",
        command="uv run pytest tests/unit/test_a.py",
        exit_code=0,
        output_summary="1 passed",
    )
    _ = SessionEventRepository(storage).record_event(
        SessionEventWrite(
            project_id="project-a",
            session_id="session-a",
            event_type="tool_called",
            tool_name="get_finding_context",
            payload={"query": SENTINEL_TEXT},
            created_at="2026-06-13T00:00:00+00:00",
        ),
    )


def _text_content(content: list[ContentBlock]) -> str:
    assert len(content) == 1
    first = content[0]
    assert isinstance(first, TextContent)
    text = first.text
    parsed = cast("object", json.loads(text))
    assert isinstance(parsed, dict)
    return text
