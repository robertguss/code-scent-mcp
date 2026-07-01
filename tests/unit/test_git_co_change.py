import subprocess
from pathlib import Path

from codescent.services.git import (
    _is_excluded_cochange_path,  # pyright: ignore[reportPrivateUsage]
    git_change_counts,
    git_co_change_counts,
    git_related_paths,
)


def test_git_co_change_counts_repeated_peer_changes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "qa@example.invalid")
    _git(repo, "config", "user.name", "QA")

    _write(repo / "a.py", "value = 1\n")
    _write(repo / "b.py", "value = 1\n")
    _commit(repo, "first coupling", "a.py", "b.py")

    _write(repo / "a.py", "value = 2\n")
    _write(repo / "b.py", "value = 2\n")
    _commit(repo, "second coupling", "a.py", "b.py")

    _write(repo / "c.py", "value = 1\n")
    _commit(repo, "irrelevant", "c.py")

    _write(repo / "a.py", "value = 3\n")
    _write(repo / ".codescent" / "state.json", "{}\n")
    _commit(repo, "runtime state", "a.py", ".codescent/state.json")

    co_changes = git_co_change_counts(repo, "a.py")
    paths = {path for path, _count in co_changes}

    assert co_changes[0] == ("b.py", 2)
    assert "a.py" not in paths
    assert "c.py" not in paths
    assert ".codescent/state.json" not in paths

    change_counts = git_change_counts(repo)

    assert change_counts == {"a.py": 3, "b.py": 2, "c.py": 1}


def test_git_co_change_counts_empty_for_non_git_dir(tmp_path: Path) -> None:
    assert git_co_change_counts(tmp_path, "a.py") == ()
    assert git_change_counts(tmp_path) == {}


def test_git_co_change_counts_empty_for_repo_without_history(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")

    assert git_co_change_counts(repo, "a.py") == ()
    assert git_change_counts(repo) == {}


def test_git_co_change_excludes_high_churn_artifacts(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "qa@example.invalid")
    _git(repo, "config", "user.name", "QA")

    for value in (1, 2):
        _write(repo / "a.py", f"value = {value}\n")
        _write(repo / "b.py", f"value = {value}\n")
        _write(repo / ".beads" / "issues.jsonl", f'{{"n": {value}}}\n')
        _write(repo / "uv.lock", f"# lock {value}\n")
        _commit(
            repo,
            f"coupling {value}",
            "a.py",
            "b.py",
            ".beads/issues.jsonl",
            "uv.lock",
        )

    co_changes = git_co_change_counts(repo, "a.py")
    paths = {path for path, _count in co_changes}

    assert co_changes[0] == ("b.py", 2)
    assert ".beads/issues.jsonl" not in paths
    assert "uv.lock" not in paths


def test_git_related_paths_excludes_high_churn_artifacts(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "qa@example.invalid")
    _git(repo, "config", "user.name", "QA")

    _write(repo / "a.py", "value = 1\n")
    _write(repo / "b.py", "value = 1\n")
    _write(repo / ".beads" / "issues.jsonl", '{"n": 1}\n')
    _commit(repo, "coupling", "a.py", "b.py", ".beads/issues.jsonl")

    related = git_related_paths(repo, "a.py")

    assert "b.py" in related
    assert ".beads/issues.jsonl" not in related


def test_is_excluded_cochange_path_covers_state_and_lockfiles() -> None:
    assert _is_excluded_cochange_path(".beads/issues.jsonl")
    assert _is_excluded_cochange_path(".codescent/state.json")
    assert _is_excluded_cochange_path("data/events.jsonl")
    assert _is_excluded_cochange_path("uv.lock")
    assert _is_excluded_cochange_path("frontend/package-lock.json")
    assert not _is_excluded_cochange_path("src/app.py")
    assert not _is_excluded_cochange_path("tests/test_app.py")


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(content)


def _commit(repo: Path, message: str, *paths: str) -> None:
    _git(repo, "add", *paths)
    _git(repo, "commit", "-m", message)


def _git(repo: Path, *args: str) -> None:
    _ = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
