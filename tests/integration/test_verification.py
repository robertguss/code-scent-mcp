from pathlib import Path

import pytest

from codescent.services.verification import VerificationService


def test_select_tests_maps_changed_source_to_related_tests(tmp_path: Path) -> None:
    repo = _repo_with_source_and_test(tmp_path)

    selected = VerificationService(repo).select_tests(paths=("src/app/x.py",))

    assert selected.changed_files == ("src/app/x.py",)
    assert selected.test_files == ("tests/test_x.py",)
    assert selected.command == "pytest tests/test_x.py"
    assert selected.executes_in_v1 is False
    assert not (repo / ".pytest_cache").exists()


def test_select_tests_without_related_tests_uses_plain_pytest(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    source = repo / "src" / "app" / "orphan.py"
    source.parent.mkdir(parents=True)
    _ = source.write_text(
        "def run_orphan() -> str:\n    return 'ok'\n",
    )

    selected = VerificationService(repo).select_tests(paths=("src/app/orphan.py",))

    assert selected.changed_files == ("src/app/orphan.py",)
    assert selected.test_files == ()
    assert selected.command == "pytest"
    assert selected.executes_in_v1 is False


def test_select_tests_uses_git_changed_paths_when_paths_are_omitted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = _repo_with_source_and_test(tmp_path)

    def fake_git_changed_paths(repo_root: Path) -> frozenset[str]:
        assert repo_root == repo.resolve()
        return frozenset({"tests/test_x.py"})

    monkeypatch.setattr(
        "codescent.services.verification.git_changed_paths",
        fake_git_changed_paths,
    )

    selected = VerificationService(repo).select_tests()

    assert selected.changed_files == ("tests/test_x.py",)
    assert selected.test_files == ("tests/test_x.py",)
    assert selected.command == "pytest tests/test_x.py"
    assert selected.executes_in_v1 is False


def _repo_with_source_and_test(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    source = repo / "src" / "app" / "x.py"
    unrelated = repo / "tests" / "test_y.py"
    test = repo / "tests" / "test_x.py"
    source.parent.mkdir(parents=True)
    test.parent.mkdir()
    _ = source.write_text(
        "def run_x() -> str:\n    return 'x'\n",
    )
    _ = test.write_text(
        """from app.x import run_x


def test_run_x() -> None:
    assert run_x() == 'x'
""",
    )
    _ = unrelated.write_text(
        """def test_unrelated() -> None:
    assert True
""",
    )
    return repo
