import subprocess
from pathlib import Path
from shutil import which

import pytest

from codescent.services.verify_refactor import VerifyRefactorService

_BEFORE = "def load_config(path):\n    return path\n"


def _git(repo: Path, *args: str) -> None:
    git_path = which("git")
    assert git_path is not None
    _ = subprocess.run(
        [git_path, "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    _ = (repo / "src" / "config.py").write_text(_BEFORE)
    _git(repo, "init")
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "base")
    return repo


@pytest.mark.skipif(which("git") is None, reason="git is required for verify_refactor")
def test_verify_refactor_preserves_unchanged_file(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    result = VerifyRefactorService(repo).verify_refactor(path="src/config.py")

    assert result.preserved is True
    assert result.base_ref == "HEAD"
    assert result.violations == ()


@pytest.mark.skipif(which("git") is None, reason="git is required for verify_refactor")
def test_verify_refactor_flags_a_signature_change_versus_head(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    # Edit the working tree only; HEAD still has the original signature.
    _ = (repo / "src" / "config.py").write_text(
        "def load_config(path, strict):\n    return path\n",
    )

    result = VerifyRefactorService(repo).verify_refactor(path="src/config.py")

    assert result.preserved is False
    assert result.changed_symbols == ("load_config",)


def test_verify_refactor_reports_unsupported_language(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / "app.ts").write_text("export const x = 1;\n")

    result = VerifyRefactorService(repo).verify_refactor(path="app.ts")

    assert result.language == "unsupported"
    assert result.preserved is False
