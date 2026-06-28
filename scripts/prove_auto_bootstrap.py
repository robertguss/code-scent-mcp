from __future__ import annotations

import hashlib
import json
import socket
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codescent.core.models import ProjectConfig
from codescent.engine.inventory import build_file_inventory
from codescent.mcp.repo_tools import start_task
from codescent.services.config import ConfigService

if TYPE_CHECKING:
    from codescent.smoke.lx_data_lake_contract import JsonValue

STATE_DIR = ".codescent"
DATABASE = "index.sqlite"
SOURCE_PY = 'def do_thing() -> str:\n    return "done"\n'
TEST_PY = (
    "from app.x import do_thing\n\n\n"
    'def test_do_thing() -> None:\n    assert do_thing() == "done"\n'
)


def prove_auto_bootstrap(out: Path) -> dict[str, JsonValue]:
    attempts: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        first_use = _scenario_first_use(workdir / "first-use", attempts)
        opt_out = _scenario_opt_out(workdir / "opt-out", attempts)
    network_attempts = len(attempts)
    payload: dict[str, JsonValue] = {
        "ok": bool(first_use["ok"] and opt_out["ok"] and network_attempts == 0),
        "network_attempts": network_attempts,
        "first_use": first_use,
        "opt_out": opt_out,
    }
    _write_json(out, payload)
    return payload


def _scenario_first_use(repo: Path, attempts: list[str]) -> dict[str, JsonValue]:
    git_available = _make_repo(repo)
    state_existed = (repo / STATE_DIR).exists()
    before = _source_hashes(repo)

    payload = _start_task_blocked(repo, attempts)

    after = _source_hashes(repo)
    note = _note(payload)
    bootstrapped = note.get("bootstrapped") is True
    state_created = (repo / STATE_DIR / DATABASE).exists()
    source_unchanged = before == after
    git_clean = _git_status_clean(repo) if git_available else True
    useful_answer = bool(payload.get("relevant_files"))
    ok = (
        not state_existed
        and bootstrapped
        and state_created
        and source_unchanged
        and git_clean
        and useful_answer
    )
    return {
        "ok": ok,
        "bootstrapped": bootstrapped,
        "reason": note.get("reason"),
        "ran": _jsonable(note.get("ran")),
        "state_created": state_created,
        "useful_answer": useful_answer,
        "source_hashes_unchanged": source_unchanged,
        "changed_paths": _changed_paths(before, after),
        "git_available": git_available,
        "git_status_clean": git_clean,
    }


def _scenario_opt_out(repo: Path, attempts: list[str]) -> dict[str, JsonValue]:
    _ = _make_repo(repo)
    ConfigService(repo).save(ProjectConfig(auto_bootstrap=False))
    before = _source_hashes(repo)

    payload = _start_task_blocked(repo, attempts)

    after = _source_hashes(repo)
    note = _note(payload)
    disabled = note.get("bootstrapped") is False and note.get("reason") == "disabled"
    has_guidance = bool(note.get("guidance"))
    source_unchanged = before == after
    index_not_refreshed = payload.get("index_fresh") is False
    ok = disabled and has_guidance and source_unchanged and index_not_refreshed
    return {
        "ok": ok,
        "bootstrapped": note.get("bootstrapped"),
        "reason": note.get("reason"),
        "guidance": _jsonable(note.get("guidance")),
        "source_hashes_unchanged": source_unchanged,
        "changed_paths": _changed_paths(before, after),
        "index_fresh": payload.get("index_fresh"),
    }


def _start_task_blocked(repo: Path, attempts: list[str]) -> dict[str, JsonValue]:
    original_socket = socket.socket
    socket.socket = _blocked_socket(attempts)
    try:
        return dict(start_task("do_thing", repo=repo.as_posix()))
    finally:
        socket.socket = original_socket


def _blocked_socket(attempts: list[str]) -> type[socket.socket]:
    class BlockedSocket(socket.socket):
        def __new__(
            cls,
            *args: JsonValue,
            **kwargs: JsonValue,
        ) -> socket.socket:
            _ = cls, args, kwargs
            attempts.append("socket")
            message = "network disabled"
            raise AssertionError(message)

    return BlockedSocket


def _note(payload: dict[str, JsonValue]) -> dict[str, JsonValue]:
    note = payload.get("bootstrap")
    return note if isinstance(note, dict) else {}


def _make_repo(repo: Path) -> bool:
    (repo / "src" / "app").mkdir(parents=True)
    (repo / "tests").mkdir()
    _ = (repo / "src" / "app" / "x.py").write_text(SOURCE_PY)
    _ = (repo / "tests" / "test_x.py").write_text(TEST_PY)
    _ = (repo / ".gitignore").write_text(".codescent/\n")
    return _git_init_commit(repo)


def _git_init_commit(repo: Path) -> bool:
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
    try:
        for command in commands:
            _ = subprocess.run(  # noqa: S603
                command,
                cwd=repo,
                check=True,
                capture_output=True,
            )
    except (OSError, subprocess.CalledProcessError):
        return False
    return True


def _git_status_clean(repo: Path) -> bool:
    result = subprocess.run(
        ("git", "status", "--porcelain"),  # noqa: S607
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() == ""


def _source_hashes(repo: Path) -> dict[str, str]:
    return {
        item.path: hashlib.sha256((repo / item.path).read_bytes()).hexdigest()
        for item in build_file_inventory(repo)
    }


def _changed_paths(before: dict[str, str], after: dict[str, str]) -> list[str]:
    return sorted(
        path for path in set(before) | set(after) if before.get(path) != after.get(path)
    )


def _jsonable(value: JsonValue) -> JsonValue:
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    return value


def _write_json(out: Path, payload: dict[str, JsonValue]) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    _ = out.write_text(json.dumps(payload, indent=2, sort_keys=True))


def main(out: Annotated[Path, typer.Option()]) -> None:
    payload = prove_auto_bootstrap(out)
    typer.echo(json.dumps({"ok": payload["ok"]}))


if __name__ == "__main__":
    typer.run(main)
