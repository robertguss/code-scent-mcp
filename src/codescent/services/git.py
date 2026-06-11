import subprocess
from dataclasses import dataclass
from pathlib import Path
from shutil import which


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
            timeout=5,
        )
    except subprocess.CalledProcessError:
        return GitState(available=False, status="not_git")
    except subprocess.TimeoutExpired:
        return GitState(available=False, status="git_timeout")

    if result.stdout.strip():
        return GitState(available=True, status="dirty")
    return GitState(available=True, status="clean")
