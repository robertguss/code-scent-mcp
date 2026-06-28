"""Service-level tests for the refactor_preflight blast-radius bundle.

Covers the three things the composition must guarantee: each section equals what
its component service returns when called directly (composition fidelity), the
bundle stays bounded and deduped, and a missing input degrades to an empty
section with a reason rather than crashing.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

from codescent.core.paths import resolve_repo_root
from codescent.services.code_health import CodeHealthService
from codescent.services.git import git_co_change_counts
from codescent.services.refactor_planning import RefactorPlanningService
from codescent.services.refactor_preflight import (
    SECTION_ITEM_CAP,
    RefactorPreflightService,
)
from codescent.services.risk import RiskService
from codescent.services.verification import VerificationService

if TYPE_CHECKING:
    from pathlib import Path

CORE = "src/pkg/core.py"


def test_each_section_matches_its_component_called_directly(tmp_path: Path) -> None:
    repo = _build_coupled_repo(tmp_path)
    _ = CodeHealthService(repo).scan()
    repo_root = resolve_repo_root(repo)

    impact_direct = RefactorPlanningService(repo).get_impact(
        target=CORE,
        target_type="file",
    )
    co_change_direct = git_co_change_counts(repo_root, CORE)
    selection_direct = VerificationService(repo).select_tests(paths=(CORE,))
    health_direct = RiskService(repo).get_changed_file_health(CORE)

    bundle = RefactorPreflightService(repo).preflight(target=CORE, target_type="file")

    assert bundle.ok is True
    assert bundle.file_path == CORE
    # Composition fidelity: identical to the component outputs (no new analysis).
    assert bundle.impact == impact_direct
    assert tuple((e.path, e.commits) for e in bundle.co_change) == co_change_direct
    assert bundle.test_selection == selection_direct
    assert bundle.changed_file_health == health_direct


def test_bundle_is_bounded_and_deduped(tmp_path: Path) -> None:
    repo = _build_coupled_repo(tmp_path)
    _ = CodeHealthService(repo).scan()

    bundle = RefactorPreflightService(repo).preflight(target=CORE, target_type="file")

    co_change_paths = [entry.path for entry in bundle.co_change]
    # Every list section honors the most restrictive existing cap.
    assert len(bundle.co_change) <= SECTION_ITEM_CAP
    assert len(bundle.impact.affected_files) <= SECTION_ITEM_CAP
    assert len(bundle.impact.likely_tests) <= SECTION_ITEM_CAP
    assert len(bundle.test_selection.test_files) <= SECTION_ITEM_CAP
    assert len(bundle.changed_file_health.findings) <= SECTION_ITEM_CAP
    # Deduped within the section the bundle itself builds.
    assert len(co_change_paths) == len(set(co_change_paths))
    # The target never appears as its own co-change peer.
    assert CORE not in co_change_paths
    # No source content leaks into the bundle (none of the four sections carry it).
    assert "def compute" not in str(bundle)


def test_missing_git_history_degrades_gracefully(tmp_path: Path) -> None:
    # A scanned but NON-git repo: impact/tests/health still resolve, co-change is
    # empty with a reason instead of crashing.
    repo = tmp_path / "nogit"
    _write_sources(repo)
    _ = CodeHealthService(repo).scan()

    bundle = RefactorPreflightService(repo).preflight(target=CORE, target_type="file")

    assert bundle.ok is True
    assert bundle.co_change == ()
    assert any("co-change empty" in note for note in bundle.warnings)
    assert bundle.file_path == CORE
    assert bundle.changed_file_health.path == CORE


def test_unresolvable_target_degrades_without_crash(tmp_path: Path) -> None:
    repo = tmp_path / "nogit"
    _write_sources(repo)
    _ = CodeHealthService(repo).scan()

    bundle = RefactorPreflightService(repo).preflight(
        target="src/pkg/does_not_exist.py",
        target_type="file",
    )

    assert any("impact unavailable" in note for note in bundle.warnings)
    assert any("changed-file health unavailable" in note for note in bundle.warnings)
    assert bundle.impact.affected_files == ()
    assert bundle.changed_file_health.findings == ()
    # select_tests degrades on its own (no test files for an unknown path).
    assert bundle.test_selection.test_files == ()


def test_no_target_at_all_is_graceful(tmp_path: Path) -> None:
    repo = tmp_path / "nogit"
    _write_sources(repo)
    _ = CodeHealthService(repo).scan()

    bundle = RefactorPreflightService(repo).preflight()

    assert bundle.ok is False
    assert any("no resolvable" in note for note in bundle.warnings)
    assert bundle.co_change == ()


def _build_coupled_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    _write_sources(repo)
    _git(repo, "init")
    _git(repo, "config", "user.email", "qa@example.invalid")
    _git(repo, "config", "user.name", "QA")
    # core.py + caller.py change together twice -> co-change(core) = caller:2.
    _commit(repo, "core+caller", "src/pkg/__init__.py", CORE, "src/pkg/caller.py")
    _write(repo / CORE, "def compute(value):\n    return value + 2\n")
    _write(
        repo / "src" / "pkg" / "caller.py",
        "from pkg.core import compute\n\n\ndef run(v):\n    return compute(v) + 1\n",
    )
    _commit(repo, "core+caller again", CORE, "src/pkg/caller.py")
    # core.py + its test change together once -> co-change(core) also = test:1.
    _commit(repo, "core+test", CORE, "tests/test_core.py")
    return repo


def _write_sources(repo: Path) -> None:
    _write(repo / "src" / "pkg" / "__init__.py", "")
    _write(repo / CORE, "def compute(value):\n    return value + 1\n")
    _write(
        repo / "src" / "pkg" / "caller.py",
        "from pkg.core import compute\n\n\ndef run(v):\n    return compute(v)\n",
    )
    _write(
        repo / "tests" / "test_core.py",
        "from pkg.core import compute\n\n\ndef test_x():\n    assert compute(1)\n",
    )


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
