"""End-to-end: one `refactor_preflight` call on a fixture with known callers,
git co-change coupling, and nearby tests.

A coupled package is built and committed so the four signals are real:
``core.py`` and ``caller.py`` change together (co-change), ``caller.py`` imports
``core`` (impact), and ``tests/test_core.py`` exercises it (verification set).
The tool is invoked through the in-memory MCP client for a target *symbol*, and
each section of the single response is logged expected-vs-found (run with ``-s``
to watch it live) and asserted present and bounded.
"""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING, cast

import pytest
from fastmcp import Client
from mcp.types import ContentBlock, TextContent

from codescent.core.paths import resolve_repo_root
from codescent.mcp.server import mcp
from codescent.services.code_health import CodeHealthService
from codescent.services.git import git_co_change_counts
from codescent.services.refactor_preflight import SECTION_ITEM_CAP
from codescent.services.risk import RiskService
from codescent.services.verification import VerificationService

if TYPE_CHECKING:
    from pathlib import Path

CORE = "src/pkg/core.py"
CALLER = "src/pkg/caller.py"
TEST = "tests/test_core.py"


def _log(step: str, *, expected: object, found: object) -> None:
    print(f"[preflight-e2e] {step}: expected={expected!r} found={found!r}")  # noqa: T201


@pytest.mark.anyio
async def test_refactor_preflight_e2e_bundles_all_four_sections(tmp_path: Path) -> None:
    repo = _build_coupled_repo(tmp_path)
    _ = CodeHealthService(repo).scan()
    repo_root = resolve_repo_root(repo)

    # --- Independently-computed expectations from each component service. -----
    expected_co_change = dict(git_co_change_counts(repo_root, CORE))
    expected_selection = VerificationService(repo).select_tests(paths=(CORE,))
    expected_health = RiskService(repo).get_changed_file_health(CORE)

    # --- One bundled call for a target SYMBOL. -------------------------------
    async with Client(mcp) as client:
        result = await client.call_tool(
            "refactor_preflight",
            {"repo": str(repo), "target": "compute", "target_type": "symbol"},
        )
    payload = _payload(result.content)

    _log("ok", expected=True, found=payload["ok"])
    assert payload["ok"] is True

    # Impact section: symbol resolved to its file; core.py is in the blast radius.
    impact = cast("dict[str, object]", payload["impact"])
    _log("impact.target_type", expected="symbol", found=impact["target_type"])
    affected = cast("list[str]", impact["affected_files"])
    _log("impact.affected_files contains core", expected=CORE, found=affected)
    assert payload["file_path"] == CORE
    assert CORE in affected
    assert len(affected) <= SECTION_ITEM_CAP

    # Co-change section matches git_co_change_counts exactly.
    co_change = {
        cast("str", entry["path"]): cast("int", entry["commits"])
        for entry in cast("list[dict[str, object]]", payload["co_change"])
    }
    _log("co_change", expected=expected_co_change, found=co_change)
    assert co_change == expected_co_change
    assert CALLER in co_change
    assert len(co_change) <= SECTION_ITEM_CAP

    # Verification set section matches select_tests exactly.
    selection = cast("dict[str, object]", payload["test_selection"])
    _log(
        "test_selection.test_files",
        expected=expected_selection.test_files,
        found=selection["test_files"],
    )
    assert (
        tuple(cast("list[str]", selection["test_files"]))
        == expected_selection.test_files
    )
    assert TEST in cast("list[str]", selection["test_files"])

    # Changed-file health section matches get_changed_file_health.
    health = cast("dict[str, object]", payload["changed_file_health"])
    _log("changed_file_health.path", expected=CORE, found=health["path"])
    assert health["path"] == expected_health.path
    assert health["risk_level"] == expected_health.risk_level
    assert len(cast("list[str]", health["finding_ids"])) <= SECTION_ITEM_CAP

    _log("warnings", expected="bounded list", found=payload["warnings"])
    assert isinstance(payload["warnings"], list)
    # The full bundle never dumps analyzed source.
    assert "def compute" not in json.dumps(payload)


def _build_coupled_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    _write(repo / "src" / "pkg" / "__init__.py", "")
    _write(repo / CORE, "def compute(value):\n    return value + 1\n")
    _write(
        repo / CALLER,
        "from pkg.core import compute\n\n\ndef run(v):\n    return compute(v)\n",
    )
    _write(
        repo / TEST,
        "from pkg.core import compute\n\n\ndef test_x():\n    assert compute(1)\n",
    )
    _git(repo, "init")
    _git(repo, "config", "user.email", "qa@example.invalid")
    _git(repo, "config", "user.name", "QA")
    _commit(repo, "core+caller", "src/pkg/__init__.py", CORE, CALLER)
    _write(repo / CORE, "def compute(value):\n    return value + 2\n")
    _write(
        repo / CALLER,
        "from pkg.core import compute\n\n\ndef run(v):\n    return compute(v) + 1\n",
    )
    _commit(repo, "core+caller again", CORE, CALLER)
    _commit(repo, "core+test", CORE, TEST)
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


def _payload(content: list[ContentBlock]) -> dict[str, object]:
    assert len(content) == 1
    first = content[0]
    assert isinstance(first, TextContent)
    parsed = cast("dict[str, object]", json.loads(first.text))
    assert isinstance(parsed, dict)
    return parsed
