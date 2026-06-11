import subprocess
from dataclasses import dataclass
from pathlib import Path
from shutil import which
from typing import Final

GIT_STATUS_TIMEOUT_SECONDS: Final = 5
PORCELAIN_STATUS_PREFIX_WIDTH: Final = 3
MIN_PORCELAIN_STATUS_LINE_LENGTH: Final = PORCELAIN_STATUS_PREFIX_WIDTH + 1


@dataclass(frozen=True, slots=True)
class GitState:
    available: bool
    status: str


def detect_git_state(repo_root: Path) -> GitState:
    if not (repo_root / ".git").exists():
        return GitState(available=False, status="not_git")

    git_path = which("git")
    if git_path is None:
        return GitState(available=False, status="git_missing")

    try:
        result = subprocess.run(
            [
                git_path,
                "-C",
                str(repo_root),
                "status",
                "--porcelain",
                "--",
                ".",
                ":(exclude).codescent",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=GIT_STATUS_TIMEOUT_SECONDS,
        )
    except subprocess.CalledProcessError:
        return GitState(available=False, status="not_git")
    except subprocess.TimeoutExpired:
        return GitState(available=False, status="git_timeout")

    if result.stdout.strip():
        return GitState(available=True, status="dirty")
    return GitState(available=True, status="clean")


def git_changed_paths(repo_root: Path) -> frozenset[str]:
    if not (repo_root / ".git").exists():
        return frozenset()

    git_path = which("git")
    if git_path is None:
        return frozenset()

    try:
        result = subprocess.run(
            [
                git_path,
                "-C",
                str(repo_root),
                "status",
                "--porcelain",
                "--untracked-files=all",
                "--",
                ".",
                ":(exclude).codescent",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=GIT_STATUS_TIMEOUT_SECONDS,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return frozenset()

    return frozenset(_parse_git_status_paths(result.stdout))


def _parse_git_status_paths(stdout: str) -> tuple[str, ...]:
    paths: list[str] = []
    for line in stdout.splitlines():
        if len(line) < MIN_PORCELAIN_STATUS_LINE_LENGTH or line.startswith("!!"):
            continue
        path = line[PORCELAIN_STATUS_PREFIX_WIDTH:]
        if " -> " in path:
            path = path.rsplit(" -> ", maxsplit=1)[1]
        paths.append(path.strip('"'))
    return tuple(paths)
