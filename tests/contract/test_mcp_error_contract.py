"""Contract tests for the uniform tool error boundary (U1) and the recoverable
recovery data at the four converted raise sites (U2)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, cast

import pytest
from fastmcp import Client, FastMCP
from mcp.types import ContentBlock, TextContent

from codescent.core.errors import CodeScentError, ErrorCode, ErrorSeverity
from codescent.core.models import (
    FindingStatus,
    MaintainabilityThresholds,
    ProjectConfig,
)
from codescent.mcp.error_boundary import ToolErrorBoundary
from codescent.mcp.server import mcp
from codescent.services.config import ConfigService

if TYPE_CHECKING:
    from pathlib import Path

STRICT_CONFIG = ProjectConfig(thresholds=MaintainabilityThresholds.strict())


# --- boundary shape (U1) -------------------------------------------------


@pytest.mark.anyio
async def test_bad_repo_returns_structured_error_not_a_string() -> None:
    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_repo_status",
            {"repo": "/no/such/dir/codescent-xyz"},
            raise_on_error=False,
        )

    payload = _json(result.content)
    assert result.is_error is True
    assert payload["ok"] is False
    assert payload["code"] == "invalid_repo_root"
    assert payload["recoverable"] is True
    assert isinstance(payload["data"], dict)
    # Keeps its existing keys so nothing branching on the old shape breaks.
    assert set(payload) >= {"code", "message", "severity", "details"}
    assert "Traceback" not in json.dumps(payload)


@pytest.mark.anyio
async def test_retrieve_result_error_gains_uniform_keys(tmp_path: Path) -> None:
    async with Client(mcp) as client:
        result = await client.call_tool(
            "retrieve_result",
            {"repo": str(tmp_path), "result_id": "ctx_0000000000000000"},
            raise_on_error=False,
        )

    payload = _json(result.content)
    # Existing StoredResultErrorPayload keys are preserved ...
    assert payload["kind"] == "result_store_error"
    assert payload["code"] == "missing_result"
    assert payload["result_id"] == "ctx_0000000000000000"
    assert payload["retryable"] is False
    # ... and the uniform envelope keys are added.
    assert payload["ok"] is False
    assert payload["recoverable"] is False  # mirrors retryable
    assert payload["data"]["result_id"] == "ctx_0000000000000000"


@pytest.mark.anyio
async def test_internal_error_is_not_recoverable() -> None:
    probe = FastMCP(name="probe")
    probe.add_middleware(ToolErrorBoundary())

    @probe.tool(description="raises a bare internal error")
    def boom(x: int) -> dict[str, int]:
        message = f"kaboom {x}"
        raise ValueError(message)

    async with Client(probe) as client:
        result = await client.call_tool("boom", {"x": 1}, raise_on_error=False)

    payload = _json(result.content)
    assert result.is_error is True
    assert payload["code"] == "internal"
    assert payload["recoverable"] is False
    # An internal fault must never leak its raw text as a "fix your input" hint.
    assert "kaboom" not in json.dumps(payload)


@pytest.mark.anyio
async def test_codescent_error_through_boundary_is_recoverable() -> None:
    probe = FastMCP(name="probe")
    probe.add_middleware(ToolErrorBoundary())

    @probe.tool(description="raises a domain error")
    def domain(x: int) -> dict[str, int]:
        raise CodeScentError(
            code=ErrorCode.NOT_FOUND,
            message="no such thing",
            severity=ErrorSeverity.ERROR,
            recovery={"available_options": ["a", "b"]},
        )

    async with Client(probe) as client:
        result = await client.call_tool("domain", {"x": 1}, raise_on_error=False)

    payload = _json(result.content)
    assert result.is_error is True
    assert payload["ok"] is False
    assert payload["code"] == "not_found"
    assert payload["recoverable"] is True
    assert payload["data"]["available_options"] == ["a", "b"]


# --- recovery data at the raise sites (U2) -------------------------------


@pytest.mark.anyio
async def test_unknown_finding_returns_bounded_available_ids(tmp_path: Path) -> None:
    repo = _repo_with_findings(tmp_path)
    async with Client(mcp) as client:
        _ = await client.call_tool("scan_code_health", {"repo": str(repo)})
        result = await client.call_tool(
            "get_finding",
            {"repo": str(repo), "finding_id": "does-not-exist"},
            raise_on_error=False,
        )

    payload = _json(result.content)
    assert payload["ok"] is False
    assert payload["code"] == "not_found"
    options = payload["data"]["available_options"]
    assert isinstance(options, list)
    assert len(options) > 0
    assert payload["data"]["fix_hint"]


@pytest.mark.anyio
async def test_finding_id_sample_is_bounded(tmp_path: Path) -> None:
    repo = _repo_with_many_findings(tmp_path, file_count=30)
    async with Client(mcp) as client:
        _ = await client.call_tool("scan_code_health", {"repo": str(repo)})
        result = await client.call_tool(
            "get_finding",
            {"repo": str(repo), "finding_id": "nope"},
            raise_on_error=False,
        )

    payload = _json(result.content)
    options = payload["data"]["available_options"]
    total = payload["data"]["total_findings"]
    assert total > len(options)  # sample, not a dump
    assert len(options) <= 10


@pytest.mark.anyio
async def test_invalid_status_lists_valid_values(tmp_path: Path) -> None:
    repo = _repo_with_findings(tmp_path)
    async with Client(mcp) as client:
        scan = _json(
            (
                await client.call_tool(
                    "scan_code_health",
                    {"repo": str(repo)},
                )
            ).content
        )
        finding_id = cast("list[str]", scan["finding_ids"])[0]
        result = await client.call_tool(
            "mark_finding",
            {"repo": str(repo), "finding_id": finding_id, "status": "banana"},
            raise_on_error=False,
        )

    payload = _json(result.content)
    assert payload["ok"] is False
    assert payload["code"] == "invalid_value"
    assert payload["data"]["valid_values"] == [s.value for s in FindingStatus]


@pytest.mark.anyio
async def test_unknown_symbol_suggests_nearest(tmp_path: Path) -> None:
    repo = _repo_with_findings(tmp_path)
    # A one-character typo of the real symbol proves rapidfuzz is wired: the
    # exact string does not exist, yet the real symbol is the top suggestion.
    real = "pkg.config.load_config"
    typo = "pkg.config.load_confib"
    async with Client(mcp) as client:
        _ = await client.call_tool("scan_code_health", {"repo": str(repo)})
        result = await client.call_tool(
            "get_symbol_context",
            {"repo": str(repo), "qualified_name": typo},
            raise_on_error=False,
        )

    payload = _json(result.content)
    assert payload["ok"] is False
    assert payload["code"] == "not_found"
    suggestions = payload["data"]["suggestions"]
    assert suggestions
    assert suggestions[0] == real


@pytest.mark.anyio
async def test_unknown_path_suggests_nearest(tmp_path: Path) -> None:
    repo = _repo_with_findings(tmp_path)
    async with Client(mcp) as client:
        _ = await client.call_tool("scan_code_health", {"repo": str(repo)})
        result = await client.call_tool(
            "get_file_context",
            {"repo": str(repo), "path": "src/pkg/confgi.py"},
            raise_on_error=False,
        )

    payload = _json(result.content)
    assert payload["ok"] is False
    assert payload["code"] == "not_found"
    assert "src/pkg/config.py" in payload["data"]["suggestions"]


# --- helpers -------------------------------------------------------------


def _repo_with_findings(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    source = repo / "src" / "pkg" / "config.py"
    source.parent.mkdir(parents=True)
    _ = source.write_text(
        'STATUS = "pending-review"\n'
        'OTHER_STATUS = "pending-review"\n'
        'THIRD_STATUS = "pending-review"\n\n\n'
        "def load_config() -> str:\n"
        "    # TODO: split config\n"
        "    # FIXME: preserve compatibility\n"
        "    # HACK: keep old queue name\n"
        "    return STATUS\n",
    )
    ConfigService(repo).save(STRICT_CONFIG)
    return repo


def _repo_with_many_findings(tmp_path: Path, file_count: int) -> Path:
    repo = tmp_path / "repo"
    package = repo / "src" / "pkg"
    package.mkdir(parents=True)
    body = "\n".join(f"    value_{line} = {line}" for line in range(80))
    for index in range(file_count):
        module = package / f"module_{index}.py"
        _ = module.write_text(f"def build_{index}() -> int:\n{body}\n    return 0\n")
    ConfigService(repo).save(STRICT_CONFIG)
    return repo


def _json(content: list[ContentBlock]) -> dict[str, Any]:
    assert len(content) == 1
    first = content[0]
    assert isinstance(first, TextContent)
    parsed = cast("object", json.loads(first.text))
    assert isinstance(parsed, dict)
    return cast("dict[str, Any]", parsed)
