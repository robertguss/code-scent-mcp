import hashlib
import socket
import subprocess
from pathlib import Path

import pytest
from scripts.prove_auto_bootstrap import prove_auto_bootstrap

from codescent.core.models import ProjectConfig
from codescent.engine.inventory import build_file_inventory
from codescent.mcp.repo_tools import start_task
from codescent.services.bootstrap import ensure_bootstrapped
from codescent.services.code_health import CodeHealthService
from codescent.services.config import ConfigService

SOURCE_PY = 'def do_thing() -> str:\n    return "done"\n'
TEST_PY = (
    "from app.x import do_thing\n\n\n"
    'def test_do_thing() -> None:\n    assert do_thing() == "done"\n'
)


def test_fresh_repo_bootstraps_and_leaves_source_clean(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    _git_init_commit(repo)
    assert not (repo / ".codescent").exists()

    result = ensure_bootstrapped(repo)

    assert result.bootstrapped is True
    assert result.reason == "created"
    assert result.ran == ("init", "index", "scan")
    assert (repo / ".codescent" / "index.sqlite").exists()
    # analyzed source untouched; .codescent is gitignored, so the tree is clean.
    assert _git_status_porcelain(repo) == ""


def test_already_fresh_is_a_noop(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    _ = CodeHealthService(repo).scan()

    result = ensure_bootstrapped(repo)

    assert result.bootstrapped is False
    assert result.reason == "fresh"
    assert result.ran == ()
    assert result.freshness.index_fresh is True


def test_stale_index_triggers_reindex(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    _ = CodeHealthService(repo).scan()
    added = repo / "src" / "app" / "y.py"
    _ = added.write_text("def added() -> int:\n    return 1\n")

    result = ensure_bootstrapped(repo)

    assert result.bootstrapped is True
    assert result.reason == "refreshed"
    assert result.ran == ("index", "scan")
    assert result.freshness.auto_refreshed is True


def test_bootstrap_makes_no_network_requests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _make_repo(tmp_path)
    attempts: list[str] = []

    def blocked_socket(*args: object, **kwargs: object) -> socket.socket:
        _ = args, kwargs
        attempts.append("socket")
        message = "network disabled"
        raise AssertionError(message)

    monkeypatch.setattr(socket, "socket", blocked_socket)

    result = ensure_bootstrapped(repo)

    assert result.bootstrapped is True
    assert attempts == []


def test_opt_out_disabled_emits_guidance_and_writes_no_index(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    ConfigService(repo).save(ProjectConfig(auto_bootstrap=False))
    # save() writes only .codescent/config.toml; the index must not exist yet.
    assert not (repo / ".codescent" / "index.sqlite").exists()

    result = ensure_bootstrapped(repo)

    assert result.bootstrapped is False
    assert result.reason == "disabled"
    assert result.guidance  # clear "run scan_code_health" guidance
    assert result.freshness.bootstrap_disabled is True
    # opt-out must not auto-create CodeScent index state.
    assert not (repo / ".codescent" / "index.sqlite").exists()


def test_config_round_trips_auto_bootstrap(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    assert ConfigService(repo).load().auto_bootstrap is True

    ConfigService(repo).save(ProjectConfig(auto_bootstrap=False))

    assert ConfigService(repo).load().auto_bootstrap is False
    config_text = (repo / ".codescent" / "config.toml").read_text()
    assert "auto_bootstrap = false" in config_text


def test_start_task_e2e_carries_bootstrap_note(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    before = _source_hashes(repo)

    payload = start_task("do_thing", repo=str(repo))

    note = payload["bootstrap"]
    assert note["bootstrapped"] is True
    assert note["reason"] == "created"
    assert "scan" in note["ran"]
    assert payload["relevant_files"]  # useful bounded answer
    assert _source_hashes(repo) == before  # analyzed source untouched


def test_prove_auto_bootstrap_script_passes(tmp_path: Path) -> None:
    payload = prove_auto_bootstrap(tmp_path / "proof.json")

    first_use = payload["first_use"]
    opt_out = payload["opt_out"]
    assert isinstance(first_use, dict)
    assert isinstance(opt_out, dict)
    assert payload["ok"] is True
    assert payload["network_attempts"] == 0
    assert first_use["ok"] is True
    assert first_use["bootstrapped"] is True
    assert opt_out["ok"] is True
    assert opt_out["bootstrapped"] is False


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "src" / "app").mkdir(parents=True)
    (repo / "tests").mkdir()
    _ = (repo / "src" / "app" / "x.py").write_text(SOURCE_PY)
    _ = (repo / "tests" / "test_x.py").write_text(TEST_PY)
    return repo


def _git_init_commit(repo: Path) -> None:
    _ = (repo / ".gitignore").write_text(".codescent/\n")
    commands = (
        ("git", "init", "-q"),
        ("git", "add", "-A"),
        (
            "git",
            "-c",
            "user.email=ci@codescent",
            "-c",
            "user.name=ci",
            "commit",
            "-qm",
            "init",
        ),
    )
    for command in commands:
        _ = subprocess.run(command, cwd=repo, check=True, capture_output=True)


def _git_status_porcelain(repo: Path) -> str:
    result = subprocess.run(
        ("git", "status", "--porcelain"),
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _source_hashes(repo: Path) -> dict[str, str]:
    return {
        item.path: hashlib.sha256((repo / item.path).read_bytes()).hexdigest()
        for item in build_file_inventory(repo)
    }
