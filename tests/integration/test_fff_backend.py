from __future__ import annotations

import shutil
from typing import TYPE_CHECKING, final

from codescent.services.fff_backend import (
    FFF_CAPABILITIES,
    ContentHit,
    FffCliClient,
    FffClient,
    FffPackageClient,
    detect_fff,
    probe_capabilities,
    select_search_backend,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    import pytest

FFF_ENV = "CODESCENT_FFF_CMD"


def _no_which(_name: str) -> str | None:
    return None


def _which_fff(name: str) -> str | None:
    return "/usr/bin/fff" if name == "fff" else None


@final
class _FakeFffClient:
    """A fully-capable in-process fff stand-in (local data only, no network)."""

    def __init__(self, *, healthy: bool = True) -> None:
        self._healthy = healthy

    def healthy(self) -> bool:
        return self._healthy

    def fuzzy_paths(self, query: str) -> tuple[str, ...]:
        return (f"src/{query}.py",)

    def grep_content(self, pattern: str) -> tuple[ContentHit, ...]:
        return (ContentHit("src/a.py", 1, pattern),)

    def multi_grep(self, patterns: Sequence[str]) -> tuple[ContentHit, ...]:
        return tuple(ContentHit("src/a.py", i, p) for i, p in enumerate(patterns))

    def frecency(self) -> Mapping[str, float]:
        return {"src/a.py": 3.0}


@final
class _PartialFffClient:
    """A present-but-partial fff engine: missing the multi_grep capability."""

    def healthy(self) -> bool:
        return True

    def fuzzy_paths(self, query: str) -> tuple[str, ...]:
        return (query,)

    def grep_content(self, pattern: str) -> tuple[ContentHit, ...]:
        return (ContentHit("src/a.py", 1, pattern),)

    def frecency(self) -> Mapping[str, float]:
        return {}


def test_detect_fff_present_via_binary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(FFF_ENV, raising=False)
    monkeypatch.setattr("codescent.services.fff_backend.shutil.which", _which_fff)

    client = detect_fff(tmp_path)

    assert client is not None
    assert isinstance(client, FffClient)
    assert select_search_backend(tmp_path) is not None


def test_detect_fff_present_via_package(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The importable wheel (no env override, no binary) drives the real
    # in-process engine, not the CLI stub.
    monkeypatch.delenv(FFF_ENV, raising=False)
    monkeypatch.setattr("codescent.services.fff_backend.shutil.which", _no_which)
    monkeypatch.setattr(
        "codescent.services.fff_backend._fff_package_available",
        lambda: True,
    )

    client = detect_fff(tmp_path)

    assert isinstance(client, FffPackageClient)
    assert probe_capabilities(client) == frozenset(FFF_CAPABILITIES)
    assert select_search_backend(tmp_path) is not None


def test_detect_fff_absent_returns_none(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Absent path: no env override, no binary on PATH, and the package probe
    # reports unavailable. The probe is mocked rather than relying on the wheel
    # being uninstalled, since fff-search is now a project dependency.
    monkeypatch.delenv(FFF_ENV, raising=False)
    monkeypatch.setattr("codescent.services.fff_backend.shutil.which", _no_which)
    monkeypatch.setattr(
        "codescent.services.fff_backend._fff_package_available",
        lambda: False,
    )

    assert detect_fff(tmp_path) is None
    assert select_search_backend(tmp_path) is None


def test_fff_command_env_override_is_consulted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(FFF_ENV, "fff")
    calls: list[tuple[object, ...]] = []

    def runner(subcommand: str, *args: object) -> object:
        calls.append((subcommand, *args))
        return ["src/x.py", "src/y.py"]

    client = detect_fff(tmp_path, runner=runner)

    assert isinstance(client, FffCliClient)
    assert client.command == "fff"
    assert client.fuzzy_paths("query") == ("src/x.py", "src/y.py")
    assert calls == [("fuzzy_paths", "query")]


def test_select_search_backend_returns_client_when_present(tmp_path: Path) -> None:
    fake = _FakeFffClient()
    assert select_search_backend(tmp_path, client=fake) is fake


def test_select_search_backend_falls_back_when_unhealthy(tmp_path: Path) -> None:
    backend = select_search_backend(tmp_path, client=_FakeFffClient(healthy=False))
    assert backend is None


def test_probe_capabilities_reports_full_surface() -> None:
    assert probe_capabilities(_FakeFffClient()) == frozenset(FFF_CAPABILITIES)


def test_probe_capabilities_degrades_when_capability_missing() -> None:
    caps = probe_capabilities(_PartialFffClient())
    assert "multi_grep" not in caps
    assert {"fuzzy_paths", "grep_content", "frecency"} <= caps


def test_probe_capabilities_handles_non_client() -> None:
    assert probe_capabilities(object()) == frozenset()


def test_module_imports_without_fff_package_installed() -> None:
    # Importing the module (done at file top) must not require fff-search; the
    # public detection surface stays available with the wheel absent.
    assert callable(detect_fff)
    assert callable(select_search_backend)


def _fixture_client(tmp_path: Path) -> tuple[FffPackageClient, Path]:
    repo = tmp_path / "python-basic"
    _ = shutil.copytree(
        "tests/fixtures/python-basic",
        repo,
        ignore=shutil.ignore_patterns(".codescent"),
    )
    return FffPackageClient(repo), repo


def test_package_client_grep_content_returns_hits(tmp_path: Path) -> None:
    client, _ = _fixture_client(tmp_path)

    hits = client.grep_content("load_config")

    assert hits
    assert all(isinstance(hit, ContentHit) for hit in hits)
    assert any(hit.path == "src/acme_tasks/config.py" and hit.line >= 1 for hit in hits)


def test_package_client_multi_grep_covers_patterns(tmp_path: Path) -> None:
    client, _ = _fixture_client(tmp_path)

    hits = client.multi_grep(["load_config", "return"])

    assert hits
    assert any("load_config" in hit.text for hit in hits)


def test_package_client_grep_empty_on_no_match(tmp_path: Path) -> None:
    client, _ = _fixture_client(tmp_path)

    assert client.grep_content("zzz_no_such_symbol_zzz") == ()


def test_package_client_fuzzy_paths_matches_filename(tmp_path: Path) -> None:
    client, _ = _fixture_client(tmp_path)

    paths = client.fuzzy_paths("config")

    assert any("config" in path for path in paths)


def test_package_client_healthy_and_frecency_shape(tmp_path: Path) -> None:
    client, _ = _fixture_client(tmp_path)

    assert client.healthy() is True
    assert isinstance(client.frecency(), dict)


def test_package_client_is_read_only(tmp_path: Path) -> None:
    client, repo = _fixture_client(tmp_path)
    before = {path.name for path in repo.rglob("*")}

    _ = client.grep_content("load_config")

    assert {path.name for path in repo.rglob("*")} == before


def test_package_client_unhealthy_path_degrades(tmp_path: Path) -> None:
    # A missing path cannot scan; the client reports unhealthy and every
    # capability returns empty rather than raising.
    client = FffPackageClient(tmp_path / "does_not_exist")

    assert client.healthy() is False
    assert client.grep_content("anything") == ()
    assert client.multi_grep(["anything"]) == ()
    assert client.fuzzy_paths("anything") == ()
