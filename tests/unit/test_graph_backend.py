from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING, final

import pytest

from codescent.services.cbm_backend import (
    CbmCliClient,
    CbmClientError,
    CbmGraphBackend,
    detect_cbm,
    select_graph_backend,
)
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
    from pathlib import Path

# The bare name cbm collapses across languages (it reported an Elixir `defp get`
# with 211 cross-language callers); tiering must keep it out of findings.
COLLISION_CALLEE = "get"


def _no_which(_name: str) -> str | None:
    return None


def _write_repo(root: Path) -> None:
    pkg = root / "src" / "pkg"
    pkg.mkdir(parents=True)
    service = textwrap.dedent(
        """\
        def run() -> int:
            return helper()


        def helper() -> int:
            return 1
        """,
    )
    caller = textwrap.dedent(
        """\
        from pkg.service import run


        def main() -> int:
            return run()
        """,
    )
    _ = (pkg / "service.py").write_text(service)
    _ = (pkg / "caller.py").write_text(caller)


@final
class _FakeCbmClient:
    def __init__(
        self,
        *,
        healthy: bool = True,
        raise_on: tuple[str, ...] = (),
    ) -> None:
        self._healthy = healthy
        self._raise_on = set(raise_on)

    def healthy(self) -> bool:
        if "healthy" in self._raise_on:
            message = "boom"
            raise CbmClientError(message)
        return self._healthy

    def symbols(self) -> tuple[SymbolNode, ...]:
        if "symbols" in self._raise_on:
            message = "boom"
            raise CbmClientError(message)
        return (
            SymbolNode(
                "pkg.service.run",
                "run",
                "function",
                "src/pkg/service.py",
                1,
                2,
                1.0,
                "python",
            ),
            SymbolNode(
                "legacy.get",
                "get",
                "function",
                "src/legacy/store.exs",
                4,
                6,
                1.0,
                "elixir",
            ),
        )

    def complexity(self) -> tuple[ComplexityProps, ...]:
        return (
            ComplexityProps("pkg.service.run", "src/pkg/service.py", "python", 2, 5),
        )

    def call_edges(self) -> tuple[CallEdge, ...]:
        if "call_edges" in self._raise_on:
            message = "boom"
            raise CbmClientError(message)
        return (
            CallEdge("src/pkg/service.py", "helper", 2, 0.95, "python"),
            CallEdge("src/legacy/store.exs", COLLISION_CALLEE, 9, 1.0, "elixir"),
        )

    def clusters(self) -> tuple[Cluster, ...]:
        return (
            Cluster("pkg", "dir:pkg", ("pkg.service.run",), ("python",)),
            Cluster(
                "collision",
                "cross-lang",
                ("legacy.get", "pkg.service.run"),
                ("elixir", "python"),
            ),
        )


def _cbm_backend(tmp_path: Path, client: _FakeCbmClient) -> CbmGraphBackend:
    return CbmGraphBackend(client=client, native=NativeGraphBackend(repo_root=tmp_path))


def test_native_backend_conforms_to_protocol(tmp_path: Path) -> None:
    _write_repo(tmp_path)
    backend = NativeGraphBackend(repo_root=tmp_path)

    assert isinstance(backend, GraphBackend)
    assert backend.name() == "native"
    assert backend.available() is True

    symbols = backend.symbols()
    assert symbols
    assert all(isinstance(symbol, SymbolNode) for symbol in symbols)
    assert {"run", "helper", "main"} <= {symbol.name for symbol in symbols}

    complexity = backend.complexity()
    assert all(isinstance(props, ComplexityProps) for props in complexity)
    assert all(props.line_span >= 1 for props in complexity)

    edges = backend.call_edges()
    assert all(isinstance(edge, CallEdge) for edge in edges)

    clusters = backend.clusters()
    assert clusters
    assert all(isinstance(cluster, Cluster) for cluster in clusters)


def test_native_backend_is_deterministic(tmp_path: Path) -> None:
    _write_repo(tmp_path)
    backend = NativeGraphBackend(repo_root=tmp_path)
    assert backend.symbols() == backend.symbols()
    assert backend.call_edges() == backend.call_edges()
    assert backend.clusters() == backend.clusters()


def test_cbm_call_edges_drop_tree_sitter_tier(tmp_path: Path) -> None:
    backend = _cbm_backend(tmp_path, _FakeCbmClient())
    edges = backend.call_edges()
    assert edges
    assert all(is_hybrid_lsp(edge.language) for edge in edges)
    assert all(edge.callee_name != COLLISION_CALLEE for edge in edges)


def test_cbm_clusters_drop_cross_language_collisions(tmp_path: Path) -> None:
    backend = _cbm_backend(tmp_path, _FakeCbmClient())
    clusters = backend.clusters()
    assert clusters
    assert all(c.cluster_id != "collision" for c in clusters)
    assert all(is_hybrid_lsp(lang) for c in clusters for lang in c.languages)


def test_cbm_symbols_pass_through_all_tiers(tmp_path: Path) -> None:
    backend = _cbm_backend(tmp_path, _FakeCbmClient())
    languages = {symbol.language for symbol in backend.symbols()}
    assert {"python", "elixir"} <= languages


def test_cbm_unhealthy_falls_back_to_native(tmp_path: Path) -> None:
    _write_repo(tmp_path)
    native = NativeGraphBackend(repo_root=tmp_path)
    backend = CbmGraphBackend(client=_FakeCbmClient(healthy=False), native=native)
    assert backend.available() is False
    assert backend.symbols() == native.symbols()
    assert backend.call_edges() == native.call_edges()
    assert backend.clusters() == native.clusters()


def test_cbm_health_error_falls_back_to_native(tmp_path: Path) -> None:
    _write_repo(tmp_path)
    native = NativeGraphBackend(repo_root=tmp_path)
    backend = CbmGraphBackend(
        client=_FakeCbmClient(raise_on=("healthy",)), native=native
    )
    assert backend.available() is False
    assert backend.call_edges() == native.call_edges()


def test_cbm_data_error_falls_back_to_native(tmp_path: Path) -> None:
    _write_repo(tmp_path)
    native = NativeGraphBackend(repo_root=tmp_path)
    backend = CbmGraphBackend(
        client=_FakeCbmClient(raise_on=("call_edges",)), native=native
    )
    edges = backend.call_edges()
    assert edges == native.call_edges()
    assert all(edge.callee_name != COLLISION_CALLEE for edge in edges)


def test_detect_cbm_absent_returns_none(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CODESCENT_CBM_CMD", raising=False)
    monkeypatch.setattr(
        "codescent.services.cbm_backend.shutil.which",
        _no_which,
    )
    assert detect_cbm(tmp_path) is None


def test_select_graph_backend_defaults_to_native_when_absent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CODESCENT_CBM_CMD", raising=False)
    monkeypatch.setattr(
        "codescent.services.cbm_backend.shutil.which",
        _no_which,
    )
    assert select_graph_backend(tmp_path).name() == "native"


def test_select_graph_backend_uses_cbm_when_present(tmp_path: Path) -> None:
    backend = select_graph_backend(tmp_path, client=_FakeCbmClient())
    assert backend.name() == "cbm"


def test_select_graph_backend_falls_back_when_unhealthy(tmp_path: Path) -> None:
    backend = select_graph_backend(tmp_path, client=_FakeCbmClient(healthy=False))
    assert backend.name() == "native"


def test_parity_cbm_present_vs_absent_never_inherits_collision(tmp_path: Path) -> None:
    _write_repo(tmp_path)
    native = NativeGraphBackend(repo_root=tmp_path)
    cbm = _cbm_backend(tmp_path, _FakeCbmClient())
    native_callees = {edge.callee_name for edge in native.call_edges()}
    cbm_callees = {edge.callee_name for edge in cbm.call_edges()}
    assert COLLISION_CALLEE not in native_callees
    assert COLLISION_CALLEE not in cbm_callees
    assert cbm.call_edges()  # python tier is still delivered from cbm


def test_cbm_cli_client_parses_json_and_tiers(tmp_path: Path) -> None:
    def runner(subcommand: str) -> object:
        payloads: dict[str, object] = {
            "health": {"ok": True},
            "symbols": [
                {
                    "qualified_name": "pkg.run",
                    "name": "run",
                    "kind": "function",
                    "path": "src/pkg/s.py",
                    "start_line": 1,
                    "end_line": 2,
                    "confidence": 1.0,
                    "language": "python",
                },
            ],
            "complexity": [],
            "call_edges": [
                {
                    "caller_path": "src/pkg/s.py",
                    "callee_name": "helper",
                    "start_line": 2,
                    "confidence": 0.9,
                    "language": "python",
                },
                {
                    "caller_path": "src/legacy/store.exs",
                    "callee_name": "get",
                    "start_line": 9,
                    "confidence": 1.0,
                    "language": "elixir",
                },
            ],
            "clusters": [],
        }
        return payloads.get(subcommand, [])

    client = CbmCliClient(command="cbm", repo_root=tmp_path, runner=runner)
    assert client.healthy() is True
    backend = CbmGraphBackend(
        client=client, native=NativeGraphBackend(repo_root=tmp_path)
    )
    assert [edge.callee_name for edge in backend.call_edges()] == ["helper"]


def test_cbm_cli_client_invalid_payload_raises(tmp_path: Path) -> None:
    def runner(_subcommand: str) -> object:
        return {"not": "a list"}

    client = CbmCliClient(command="cbm", repo_root=tmp_path, runner=runner)
    with pytest.raises(CbmClientError):
        _ = client.symbols()
