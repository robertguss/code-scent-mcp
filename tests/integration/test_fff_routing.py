"""Retrieval routing through the optional fff engine (plan unit U8 / bead P2.1).

fff is NOT installed in this environment, so the live runtime path stays native
(rapidfuzz). These tests inject a fake ``FffClient`` to exercise the fff route as
a seam: when a present-and-healthy client exposes a capability, search routes
through it and re-applies CodeScent's collapse / bounding / freshness so the
output envelope is identical to native; when the client is absent, unhealthy,
partial, or raises, search falls back to the native floor per capability.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast, final

from codescent.services.fff_backend import ContentHit
from codescent.services.search import SearchService

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from codescent.services.fff_backend import FffClient

_MARKER_SOURCE = """def handle(payload: str) -> str:
    result = needle_marker(payload)
    return result
"""


def _write(repo: Path, relative: str, text: str) -> None:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(text)


def _marker_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    _write(repo, "src/mod.py", _MARKER_SOURCE)
    return repo


@final
class _FakeFff:
    """Fully-capable in-process fff stand-in returning caller-supplied data."""

    def __init__(
        self,
        *,
        paths: tuple[str, ...] = (),
        hits: tuple[ContentHit, ...] = (),
        healthy: bool = True,
    ) -> None:
        self._paths = paths
        self._hits = hits
        self._healthy = healthy

    def healthy(self) -> bool:
        return self._healthy

    def fuzzy_paths(self, query: str) -> tuple[str, ...]:
        _ = query
        return self._paths

    def grep_content(self, pattern: str) -> tuple[ContentHit, ...]:
        _ = pattern
        return self._hits

    def multi_grep(self, patterns: Sequence[str]) -> tuple[ContentHit, ...]:
        _ = patterns
        return self._hits

    def frecency(self) -> Mapping[str, float]:
        return {}


@final
class _NoGrepFff:
    """Present-but-partial engine: exposes path search but no content grep."""

    def healthy(self) -> bool:
        return True

    def fuzzy_paths(self, query: str) -> tuple[str, ...]:
        _ = query
        return ("src/from_fff.py",)

    def frecency(self) -> Mapping[str, float]:
        return {}


@final
class _RaisingFff:
    """A healthy engine whose retrieval calls blow up mid-flight."""

    def healthy(self) -> bool:
        return True

    def fuzzy_paths(self, query: str) -> tuple[str, ...]:
        _ = query
        message = "fff path search exploded"
        raise RuntimeError(message)

    def grep_content(self, pattern: str) -> tuple[ContentHit, ...]:
        _ = pattern
        message = "fff grep exploded"
        raise RuntimeError(message)

    def multi_grep(self, patterns: Sequence[str]) -> tuple[ContentHit, ...]:
        _ = patterns
        message = "fff multi grep exploded"
        raise RuntimeError(message)

    def frecency(self) -> Mapping[str, float]:
        return {}


def _service(repo: Path, fake: object) -> SearchService:
    return SearchService(repo, fff_client=cast("FffClient", fake))


def test_search_content_routes_through_fff_with_identical_envelope(
    tmp_path: Path,
) -> None:
    repo = _marker_repo(tmp_path)
    native_repo = tmp_path / "native"
    _write(native_repo, "src/mod.py", _MARKER_SOURCE)

    native = SearchService(native_repo).search_content("needle_marker", limit=20)
    fake = _FakeFff(hits=(ContentHit("src/mod.py", 2, "needle_marker"),))
    routed = _service(repo, fake).search_content("needle_marker", limit=20)

    # fff supplied the candidate, but collapse/bounding shaping is native-identical.
    assert len(routed) == 1
    assert routed[0]["path"] == "src/mod.py"
    assert routed[0]["snippet"] == "def handle(payload: str) -> str:"
    assert "collapsed_to_symbol" in routed[0]["reasons"]
    symbol = routed[0]["symbol"]
    assert symbol is not None
    assert symbol["name"] == "handle"
    # Envelope shape (key set) is identical to the native path.
    assert set(routed[0]) == set(native[0])


def test_search_files_routes_through_fuzzy_paths(tmp_path: Path) -> None:
    repo = _marker_repo(tmp_path)
    fake = _FakeFff(paths=("src/from_fff.py", "src/other_fff.py"))

    routed = _service(repo, fake).search_files("anything", limit=20)
    paths = tuple(result["path"] for result in routed)

    # The candidates come from fuzzy_paths (they do not exist natively) and the
    # engine's relevance order is preserved by the descending fff score.
    assert paths == ("src/from_fff.py", "src/other_fff.py")
    assert all("fff_path" in result["reasons"] for result in routed)


def test_absent_fff_runs_native_unchanged(tmp_path: Path) -> None:
    repo = _marker_repo(tmp_path)

    # Default service: select_search_backend detects no fff -> native floor.
    results = SearchService(repo).search_content("needle_marker", limit=20)

    assert len(results) == 1
    assert results[0]["path"] == "src/mod.py"
    assert results[0]["snippet"] == "def handle(payload: str) -> str:"
    assert results[0]["symbol"] is not None


def test_missing_capability_degrades_that_op_only(tmp_path: Path) -> None:
    repo = _marker_repo(tmp_path)
    service = _service(repo, _NoGrepFff())

    # grep_content is absent -> content search degrades to the native scan.
    content = service.search_content("needle_marker", limit=20)
    assert len(content) == 1
    assert content[0]["path"] == "src/mod.py"
    assert content[0]["snippet"] == "def handle(payload: str) -> str:"

    # fuzzy_paths IS present -> path search still routes through fff.
    files = service.search_files("anything", limit=20)
    assert tuple(result["path"] for result in files) == ("src/from_fff.py",)


def test_fff_path_results_respect_the_bound(tmp_path: Path) -> None:
    repo = _marker_repo(tmp_path)
    many = tuple(f"src/file_{index:02d}.py" for index in range(50))
    fake = _FakeFff(paths=many)

    routed = _service(repo, fake).search_files("x", limit=3)

    assert len(routed) == 3
    assert tuple(result["path"] for result in routed) == many[:3]


def test_fff_content_results_respect_the_bound(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    for index in range(8):
        _write(
            repo,
            f"src/mod_{index:02d}.py",
            f"def handle_{index:02d}() -> int:\n    return needle_marker()\n",
        )
    hits = tuple(
        ContentHit(f"src/mod_{index:02d}.py", 2, "needle_marker") for index in range(8)
    )
    fake = _FakeFff(hits=hits)

    routed = _service(repo, fake).search_content("needle_marker", limit=3)

    assert len(routed) == 3
    assert all("collapsed_to_symbol" in result["reasons"] for result in routed)


def test_raising_client_falls_back_to_native(tmp_path: Path) -> None:
    repo = _marker_repo(tmp_path)
    service = _service(repo, _RaisingFff())

    # grep_content raises -> caught, native scan answers instead (no error out).
    content = service.search_content("needle_marker", limit=20)
    assert len(content) == 1
    assert content[0]["snippet"] == "def handle(payload: str) -> str:"

    # fuzzy_paths raises -> native path search answers instead.
    files = service.search_files("mod", limit=20)
    assert any(result["path"] == "src/mod.py" for result in files)


def test_unhealthy_client_falls_back_to_native(tmp_path: Path) -> None:
    repo = _marker_repo(tmp_path)
    # An unhealthy client is dropped by select_search_backend before any routing;
    # its bogus hit must never surface.
    fake = _FakeFff(healthy=False, hits=(ContentHit("src/nope.py", 1, "x"),))

    results = _service(repo, fake).search_content("needle_marker", limit=20)

    assert len(results) == 1
    assert results[0]["path"] == "src/mod.py"
