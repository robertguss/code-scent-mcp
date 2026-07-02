from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict, cast

from codescent.mcp.finding_payloads import ok_envelope
from codescent.services.architecture import build_architecture

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from codescent.services.architecture import Architecture


class ModuleViewPayload(TypedDict):
    name: str
    members: tuple[str, ...]
    size: int
    source: str
    confidence: float


class HotspotPayload(TypedDict):
    path: str
    line_count: int


class GetArchitecturePayload(TypedDict):
    ok: bool
    read_only: bool
    file_count: int
    languages: dict[str, int]
    packages: tuple[str, ...]
    entry_points: tuple[str, ...]
    layers: tuple[str, ...]
    hotspots: tuple[HotspotPayload, ...]
    modules: tuple[ModuleViewPayload, ...]
    cluster_source: str
    next_tools: tuple[str, ...]


def register_architecture_tools(mcp: FastMCP) -> None:
    _ = mcp.tool(
        description=(
            "Orient on an unfamiliar repository in ONE bounded call instead of "
            "many repo-map + read cycles: languages, packages, entry points, "
            "layers, the largest files (hotspots), and the de-facto modules "
            "(cbm's clusters when a local cbm process is present, else a native "
            "label-propagation pass over the import graph, marked heuristic). "
            "e.g. get_architecture(repo='.'). Read-only for source; bounded "
            "output."
        ),
    )(get_architecture)


def get_architecture(repo: str = ".") -> GetArchitecturePayload:
    return _architecture_payload(build_architecture(repo))


def _architecture_payload(architecture: Architecture) -> GetArchitecturePayload:
    envelope = ok_envelope(
        next_tools=("get_repo_map", "scan_code_health"),
        read_only=True,
        file_count=architecture.file_count,
        languages=architecture.languages,
        packages=architecture.packages,
        entry_points=architecture.entry_points,
        layers=architecture.layers,
        hotspots=tuple(
            {"path": hotspot.path, "line_count": hotspot.line_count}
            for hotspot in architecture.hotspots
        ),
        modules=tuple(
            {
                "name": module.name,
                "members": module.members,
                "size": module.size,
                "source": module.source,
                "confidence": module.confidence,
            }
            for module in architecture.modules
        ),
        cluster_source=architecture.cluster_source,
    )
    return cast("GetArchitecturePayload", cast("object", envelope))
