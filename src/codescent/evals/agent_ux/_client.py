"""In-memory MCP client plumbing shared by the agent-experience dimensions.

Every dimension drives the real FastMCP surface through the in-process
``fastmcp.Client(mcp)`` transport -- no subprocess, no socket, no network --
and reads the single ``TextContent`` JSON payload each tool returns. This
module centralizes the ``call_tool_json`` / ``list_tools_manifest`` helpers
(otherwise duplicated as a private ``_json`` across ~18 test files) and the
deterministic smelly-repo builder the dimensions score against, mirroring the
contract-test ``_repo_with_smell`` recipe.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from mcp.types import TextContent

from codescent.core.models import MaintainabilityThresholds, ProjectConfig
from codescent.evals.agent_ux.models import ToolInfo
from codescent.services.config import ConfigService

if TYPE_CHECKING:
    from pathlib import Path

    from fastmcp import Client
    from fastmcp.client.transports import FastMCPTransport
    from mcp.types import ContentBlock

STRICT_CONFIG = ProjectConfig(thresholds=MaintainabilityThresholds.strict())

_CONFIG_SOURCE = """STATUS = "pending-review"
OTHER_STATUS = "pending-review"
THIRD_STATUS = "pending-review"


def load_config() -> str:
    # TODO: split config
    # FIXME: preserve compatibility
    # HACK: keep old queue name
    return STATUS
"""

_CONFIG_TEST = """from pkg.config import load_config


def test_load_config() -> None:
    assert load_config() == "pending-review"
"""


def _payload(content: list[ContentBlock]) -> dict[str, object]:
    """Parse the single ``TextContent`` JSON block a tool returns."""
    if len(content) != 1:
        msg = f"expected exactly one content block, got {len(content)}"
        raise ValueError(msg)
    first = content[0]
    if not isinstance(first, TextContent):
        msg = f"expected TextContent, got {type(first).__name__}"
        raise TypeError(msg)
    parsed = cast("object", json.loads(first.text))
    if not isinstance(parsed, dict):
        msg = "tool payload is not a JSON object"
        raise TypeError(msg)
    return cast("dict[str, object]", parsed)


async def call_tool_json(
    client: Client[FastMCPTransport],
    name: str,
    args: dict[str, object],
) -> dict[str, object]:
    """Call ``name`` on ``client`` and return its parsed JSON payload.

    Uses ``raise_on_error=False`` so an error envelope is returned as data
    rather than raised -- the error-recovery and envelope dimensions inspect
    error payloads directly.

    Args:
        client: An open in-memory ``fastmcp.Client`` session.
        name: The MCP tool name to call.
        args: The tool arguments.

    Returns:
        The tool's JSON payload as a dict (success or error envelope).
    """
    result = await client.call_tool(name, args, raise_on_error=False)
    return _payload(result.content)


async def todo_finding_id(
    client: Client[FastMCPTransport],
    repo: Path,
) -> str:
    """Return the fixture's ``python.todo_cluster`` finding id via the surface.

    Shared by the error-recovery, envelope, and loop-connectivity dimensions so
    each reuses the same live finding rather than re-deriving it.
    """
    scan = await call_tool_json(client, "scan_code_health", {"repo": str(repo)})
    ids = scan.get("finding_ids")
    if not isinstance(ids, list):
        msg = "scan payload has no finding_ids list"
        raise TypeError(msg)
    for item in cast("list[object]", ids):
        if isinstance(item, str) and item.startswith("python.todo_cluster"):
            return item
    msg = "no python.todo_cluster finding in the fixture"
    raise ValueError(msg)


async def list_tools_manifest(
    client: Client[FastMCPTransport],
) -> list[ToolInfo]:
    """Return the live ``tools/list`` manifest as :class:`ToolInfo` entries."""
    tools = await client.list_tools()
    return [
        ToolInfo(
            name=tool.name,
            description=tool.description or "",
            input_schema_json=json.dumps(
                tool.inputSchema or {}, sort_keys=True, default=str
            ),
        )
        for tool in tools
    ]


def build_smelly_repo(dst: Path) -> Path:
    """Write a deterministic repo with a known finding cluster under ``dst``.

    Mirrors the contract-test ``_repo_with_smell`` recipe: a config module with
    a TODO/FIXME/HACK cluster and repeated string literals, a matching test, and
    a strict project config. Yields a ``python.todo_cluster`` finding the
    error-recovery, loop-connectivity, and constraint-drop dimensions rely on.
    The caller still runs ``scan_code_health`` to build the index.

    Args:
        dst: Directory to create the ``repo`` under (typically a temp dir).

    Returns:
        The path to the created repository root.
    """
    repo = dst / "repo"
    source = repo / "src" / "pkg" / "config.py"
    test = repo / "tests" / "test_config.py"
    source.parent.mkdir(parents=True)
    test.parent.mkdir()
    _ = source.write_text(_CONFIG_SOURCE)
    _ = test.write_text(_CONFIG_TEST)
    ConfigService(repo).save(STRICT_CONFIG)
    return repo
