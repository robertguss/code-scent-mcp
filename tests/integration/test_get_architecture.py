"""get_architecture returns ONE bounded orientation overview."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, cast, final

import pytest
from fastmcp import Client
from mcp.types import ContentBlock, TextContent

from codescent.mcp.architecture_tools import (
    GetArchitecturePayload,
    get_architecture,
)
from codescent.mcp.schema import build_schema
from codescent.mcp.server import mcp
from codescent.services.architecture import (
    HOTSPOT_CAP,
    MODULE_CAP,
    build_architecture,
)
from codescent.services.graph_backend import (
    CallEdge,
    Cluster,
    ComplexityProps,
    SymbolNode,
)

if TYPE_CHECKING:
    from codescent.services.cbm_backend import CbmClient

FIXTURE = Path("tests/fixtures/python-basic")


def _no_cbm(*_args: object, **_kwargs: object) -> None:
    return None


def _force_native(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("codescent.services.cbm_backend.detect_cbm", _no_cbm)


@final
class _StubCbmClient:
    """A local cbm stub that exposes two python-only clusters."""

    def healthy(self) -> bool:
        return True

    def symbols(self) -> tuple[SymbolNode, ...]:
        return ()

    def complexity(self) -> tuple[ComplexityProps, ...]:
        return ()

    def call_edges(self) -> tuple[CallEdge, ...]:
        return ()

    def clusters(self) -> tuple[Cluster, ...]:
        return (
            Cluster("auth", "auth-module", ("a.py", "b.py"), ("python",)),
            Cluster("io", "io-module", ("c.py",), ("python",)),
        )


def test_get_architecture_returns_bounded_overview(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _force_native(monkeypatch)

    arch = build_architecture(FIXTURE)

    # Every orientation facet is present and bounded.
    assert arch.languages == {"python": arch.languages["python"]}
    assert arch.languages["python"] >= 1
    assert "acme_tasks" in arch.packages
    assert "src/acme_tasks/cli.py" in arch.entry_points
    assert "src/acme_tasks" in arch.layers
    assert arch.hotspots
    assert arch.hotspots[0].path == "src/acme_tasks/oversized.py"
    assert len(arch.hotspots) <= HOTSPOT_CAP
    assert arch.modules
    assert len(arch.modules) <= MODULE_CAP


def test_cbm_present_surfaces_cbm_clusters() -> None:
    arch = build_architecture(FIXTURE, client=cast("CbmClient", _StubCbmClient()))

    assert arch.cluster_source == "cbm"
    names = {module.name for module in arch.modules}
    assert {"auth-module", "io-module"} <= names
    assert all(module.source == "cbm" for module in arch.modules)
    # Ranked by membership: the two-member cluster leads.
    assert arch.modules[0].name == "auth-module"


def test_cbm_absent_runs_heuristic_clustering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _force_native(monkeypatch)

    arch = build_architecture(FIXTURE)

    assert arch.cluster_source == "heuristic"
    assert arch.modules
    # The native fallback marks every module as heuristic with a confidence.
    assert all(module.source == "heuristic" for module in arch.modules)
    assert all(0.0 < module.confidence <= 1.0 for module in arch.modules)
    # cli imports workflow, so the de-facto module is import-linked, not isolated.
    linked = next(
        module for module in arch.modules if "src/acme_tasks/cli.py" in module.members
    )
    assert "src/acme_tasks/workflow.py" in linked.members


def test_overview_respects_its_bound_on_a_larger_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _force_native(monkeypatch)
    _write_wide_repo(tmp_path)

    arch = build_architecture(tmp_path)

    # More directories and files than the caps, yet the overview stays bounded.
    assert len(arch.modules) <= MODULE_CAP
    assert len(arch.hotspots) <= HOTSPOT_CAP
    assert all(len(module.members) <= 25 for module in arch.modules)


def test_get_architecture_in_schema_and_callable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _force_native(monkeypatch)

    schema = build_schema()
    by_name = {tool["name"]: tool for tool in schema["tools"]}
    assert "get_architecture" in by_name
    entry = by_name["get_architecture"]
    assert "repo" in entry["params"]
    assert {"modules", "hotspots", "cluster_source"} <= set(entry["response_keys"])

    payload = get_architecture(str(FIXTURE))
    assert payload["ok"] is True
    assert payload["read_only"] is True
    assert payload["cluster_source"] == "heuristic"


@pytest.mark.anyio
async def test_get_architecture_callable_over_stdio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _force_native(monkeypatch)

    async with Client(mcp) as client:
        tools = await client.list_tools()
        assert "get_architecture" in {tool.name for tool in tools}
        result = await client.call_tool("get_architecture", {"repo": str(FIXTURE)})

    payload = cast(
        "GetArchitecturePayload",
        json.loads(_text_content(result.content)),
    )
    assert payload["ok"] is True
    assert payload["languages"]["python"] >= 1
    assert len(payload["modules"]) <= MODULE_CAP


def _write_wide_repo(root: Path) -> None:
    for index in range(MODULE_CAP * 3):
        package = root / "src" / "proj" / f"mod_{index:02d}"
        package.mkdir(parents=True, exist_ok=True)
        body = "\n".join(f"value_{line} = {line}" for line in range(index + 5))
        _ = (package / "unit.py").write_text(f"{body}\n")


def _text_content(content: list[ContentBlock]) -> str:
    assert len(content) == 1
    first = content[0]
    assert isinstance(first, TextContent)
    return first.text
