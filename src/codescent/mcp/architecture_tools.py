from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

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


def register_architecture_tools(mcp: FastMCP) -> None:
    _ = mcp.tool(
        description=(
            "Use CodeScent to orient on an unfamiliar repository in ONE bounded "
            "call instead of many repo-map + read cycles. Returns languages, "
            "packages, entry points, layers, the largest files (hotspots), and "
            "the de-facto modules: cbm's clusters when a local cbm process is "
            "present, otherwise a native label-propagation pass over the import "
            "graph (marked heuristic). Read-only for analyzed source; bounded "
            "output."
        ),
    )(get_architecture)


def get_architecture(repo: str = ".") -> GetArchitecturePayload:
    return _architecture_payload(build_architecture(repo))


def _architecture_payload(architecture: Architecture) -> GetArchitecturePayload:
    return {
        "ok": True,
        "read_only": True,
        "file_count": architecture.file_count,
        "languages": architecture.languages,
        "packages": architecture.packages,
        "entry_points": architecture.entry_points,
        "layers": architecture.layers,
        "hotspots": tuple(
            {"path": hotspot.path, "line_count": hotspot.line_count}
            for hotspot in architecture.hotspots
        ),
        "modules": tuple(
            {
                "name": module.name,
                "members": module.members,
                "size": module.size,
                "source": module.source,
                "confidence": module.confidence,
            }
            for module in architecture.modules
        ),
        "cluster_source": architecture.cluster_source,
    }
