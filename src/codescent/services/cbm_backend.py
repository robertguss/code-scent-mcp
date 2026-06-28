"""Optional cbm-backed structural graph backend.

cbm (codebase-memory-mcp) is a fast LOCAL structural index. When a cbm process
is reachable on this machine, this adapter pulls symbols / complexity / call
edges / clusters from it; otherwise it falls back to the native backend and
behaves exactly as CodeScent does today.

Hard constraint: cbm's CALL GRAPH is only trusted for Hybrid-LSP languages.
For the tree-sitter tail cbm collapses same-named symbols across languages, so
the adapter drops cbm call edges and cross-language clusters for those languages
before they can reach CodeScent findings.

Local IPC only — this module never opens a network connection.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, cast, runtime_checkable

from pydantic import TypeAdapter, ValidationError

from codescent.core.paths import resolve_repo_root
from codescent.services.graph_backend import (
    CallEdge,
    Cluster,
    ComplexityProps,
    GraphBackend,
    NativeGraphBackend,
    SymbolNode,
    is_hybrid_lsp,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

LOGGER = logging.getLogger("codescent.cbm_backend")
CBM_COMMAND_ENV = "CODESCENT_CBM_CMD"
CBM_CANDIDATES = ("cbm", "codebase-memory-mcp")
DEFAULT_TIMEOUT_SECONDS = 5.0


class CbmClientError(RuntimeError):
    """A local cbm process was unreachable or returned unusable data."""


@runtime_checkable
class CbmClient(Protocol):
    """Minimal contract the adapter needs from a local cbm process."""

    def healthy(self) -> bool: ...
    def symbols(self) -> tuple[SymbolNode, ...]: ...
    def complexity(self) -> tuple[ComplexityProps, ...]: ...
    def call_edges(self) -> tuple[CallEdge, ...]: ...
    def clusters(self) -> tuple[Cluster, ...]: ...


_SYMBOLS_ADAPTER = TypeAdapter(list[SymbolNode])
_COMPLEXITY_ADAPTER = TypeAdapter(list[ComplexityProps])
_CALL_EDGES_ADAPTER = TypeAdapter(list[CallEdge])
_CLUSTERS_ADAPTER = TypeAdapter(list[Cluster])


def _validate[T](adapter: TypeAdapter[list[T]], payload: object) -> tuple[T, ...]:
    try:
        return tuple(adapter.validate_python(payload))
    except ValidationError as exc:
        message = "cbm payload failed validation"
        raise CbmClientError(message) from exc


@dataclass(frozen=True, slots=True)
class CbmCliClient:
    """Talk to a local cbm CLI over a documented JSON contract (no network).

    Each subcommand is expected to emit a JSON array of records matching the
    graph_backend dataclasses (or, for ``health``, an object with an ``ok``
    flag). A ``runner`` may be injected for testing so no subprocess spawns.
    """

    command: str
    repo_root: Path
    runner: Callable[[str], object] | None = None
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS

    def healthy(self) -> bool:
        try:
            payload = self._invoke("health")
        except CbmClientError:
            return False
        if isinstance(payload, dict):
            health = cast("dict[str, object]", payload)
            return bool(health.get("ok", True))
        return False

    def symbols(self) -> tuple[SymbolNode, ...]:
        return _validate(_SYMBOLS_ADAPTER, self._invoke("symbols"))

    def complexity(self) -> tuple[ComplexityProps, ...]:
        return _validate(_COMPLEXITY_ADAPTER, self._invoke("complexity"))

    def call_edges(self) -> tuple[CallEdge, ...]:
        return _validate(_CALL_EDGES_ADAPTER, self._invoke("call_edges"))

    def clusters(self) -> tuple[Cluster, ...]:
        return _validate(_CLUSTERS_ADAPTER, self._invoke("clusters"))

    def _invoke(self, subcommand: str) -> object:
        if self.runner is not None:
            return self.runner(subcommand)
        return self._run_subprocess(subcommand)

    def _run_subprocess(self, subcommand: str) -> object:
        argv = [
            self.command,
            subcommand,
            "--repo",
            str(self.repo_root),
            "--format",
            "json",
        ]
        try:
            completed = subprocess.run(  # noqa: S603  # local cbm CLI, fixed argv
                argv,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=True,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            message = f"cbm invocation failed: {subcommand}"
            raise CbmClientError(message) from exc
        try:
            return cast("object", json.loads(completed.stdout))
        except json.JSONDecodeError as exc:
            message = f"cbm returned invalid json: {subcommand}"
            raise CbmClientError(message) from exc


@dataclass(frozen=True, slots=True)
class CbmGraphBackend:
    """cbm-backed `GraphBackend` with language tiering and native fallback."""

    client: CbmClient
    native: NativeGraphBackend

    def name(self) -> str:
        return "cbm"

    def available(self) -> bool:
        try:
            return self.client.healthy()
        except CbmClientError:
            return False

    def symbols(self) -> tuple[SymbolNode, ...]:
        # Symbols carry no cross-symbol resolution, so every tier is safe.
        data, _ = self._pull(self.client.symbols, self.native.symbols, "symbols")
        return data

    def complexity(self) -> tuple[ComplexityProps, ...]:
        data, _ = self._pull(
            self.client.complexity,
            self.native.complexity,
            "complexity",
        )
        return data

    def call_edges(self) -> tuple[CallEdge, ...]:
        data, from_cbm = self._pull(
            self.client.call_edges,
            self.native.call_edges,
            "call_edges",
        )
        if not from_cbm:
            return data
        tiered = tuple(edge for edge in data if is_hybrid_lsp(edge.language))
        if len(tiered) != len(data):
            LOGGER.info(
                "dropped %d tree-sitter-tier cbm call edge(s)",
                len(data) - len(tiered),
            )
        return tiered

    def clusters(self) -> tuple[Cluster, ...]:
        data, from_cbm = self._pull(
            self.client.clusters,
            self.native.clusters,
            "clusters",
        )
        if not from_cbm:
            return data
        tiered = tuple(
            cluster
            for cluster in data
            if all(is_hybrid_lsp(language) for language in cluster.languages)
        )
        if len(tiered) != len(data):
            LOGGER.info(
                "dropped %d cross-language cbm cluster(s)",
                len(data) - len(tiered),
            )
        return tiered

    def _pull[T](
        self,
        cbm_call: Callable[[], tuple[T, ...]],
        native_call: Callable[[], tuple[T, ...]],
        label: str,
    ) -> tuple[tuple[T, ...], bool]:
        if not self.available():
            LOGGER.info("cbm unavailable; native fallback for %s", label)
            return native_call(), False
        try:
            data = cbm_call()
        except CbmClientError:
            LOGGER.warning("cbm %s failed; native fallback", label)
            return native_call(), False
        LOGGER.debug("cbm supplied %d %s record(s)", len(data), label)
        return data, True


def detect_cbm(
    repo_root: Path | str,
    *,
    runner: Callable[[str], object] | None = None,
) -> CbmClient | None:
    """Detect a LOCAL cbm process; return None cleanly when cbm is absent."""
    command = os.environ.get(CBM_COMMAND_ENV)
    if command is None:
        for candidate in CBM_CANDIDATES:
            found = shutil.which(candidate)
            if found is not None:
                command = found
                break
    if command is None:
        LOGGER.debug("cbm not detected; using native graph backend")
        return None
    LOGGER.info("cbm command detected at %s", command)
    return CbmCliClient(
        command=command,
        repo_root=resolve_repo_root(repo_root),
        runner=runner,
    )


def select_graph_backend(
    repo_root: Path | str,
    *,
    client: CbmClient | None = None,
    runner: Callable[[str], object] | None = None,
) -> GraphBackend:
    """Pick the structural backend: cbm when present and healthy, else native."""
    native = NativeGraphBackend(repo_root=repo_root)
    resolved = client if client is not None else detect_cbm(repo_root, runner=runner)
    if resolved is None:
        return native
    backend = CbmGraphBackend(client=resolved, native=native)
    if not backend.available():
        LOGGER.info("cbm detected but unhealthy; using native graph backend")
        return native
    LOGGER.info("using cbm graph backend")
    return backend
