"""End-to-end bus-factor signal over a real git history.

A git fixture is built in a tmp dir (building test data, not analysing the
parent repo): one single-author high-churn file becomes a knowledge silo, a
well-distributed file does not, and a repo with no history yields nothing. The
signal is exercised through the pack registry's ``scan_rule_packs`` -- the same
path that feeds the scan envelope's ``rule_id`` set -- so the assertion proves
registration + wiring without coupling to storage/indexing.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

from codescent.engine.packs import build_pack_registry
from codescent.engine.rules.knowledge_silo import (
    PYTHON_KNOWLEDGE_SILO_RULE_ID,
    SILO_DOMINANCE_THRESHOLD,
)

if TYPE_CHECKING:
    from pathlib import Path

    from codescent.engine.rules.model import CodeHealthFinding


def _silo_findings(repo: Path) -> tuple[CodeHealthFinding, ...]:
    findings = build_pack_registry().scan_rule_packs(repo)
    return tuple(
        finding
        for finding in findings
        if finding.rule_id == PYTHON_KNOWLEDGE_SILO_RULE_ID
    )


def _build_history(tmp_path: Path) -> Path:
    repo = _init_repo(tmp_path)
    # silo.py: one author, well above MIN_SILO_CHURN.
    for value in range(6):
        _write(repo / "silo.py", f"VALUE = {value}\n")
        _commit(repo, f"silo {value}", "silo.py", author="Alice")
    # shared.py: high churn but evenly spread across three authors.
    for index, author in enumerate(("Alice", "Bob", "Carol", "Alice", "Bob", "Carol")):
        _write(repo / "shared.py", f"VALUE = {index}\n")
        _commit(repo, f"shared {index}", "shared.py", author=author)
    return repo


def test_single_author_high_churn_file_is_flagged(tmp_path: Path) -> None:
    repo = _build_history(tmp_path)

    findings = _silo_findings(repo)
    flagged = {finding.file_path: finding for finding in findings}

    # Deterministic logging of the discriminating values vs the threshold.
    for finding in findings:
        share = finding.evidence["top_author_share"]
        churn = finding.evidence["churn"]
        diagnostic = " ".join(
            [
                f"silo candidate {finding.file_path}:",
                f"share={share}",
                f"vs threshold={SILO_DOMINANCE_THRESHOLD}",
                f"churn={churn}",
            ],
        )
        print(diagnostic)  # noqa: T201 - intentional e2e diagnostic

    assert set(flagged) == {"silo.py"}
    assert flagged["silo.py"].confidence == 0.9
    assert flagged["silo.py"].evidence["author_count"] == 1


def test_well_distributed_file_is_not_flagged(tmp_path: Path) -> None:
    repo = _build_history(tmp_path)
    flagged = {finding.file_path for finding in _silo_findings(repo)}
    assert "shared.py" not in flagged


def test_no_history_yields_no_finding(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    assert _silo_findings(repo) == ()


def test_signal_is_deterministic(tmp_path: Path) -> None:
    first = _silo_findings(_build_history(tmp_path / "a"))
    second = _silo_findings(_build_history(tmp_path / "b"))
    assert tuple(f.id for f in first) == tuple(f.id for f in second)
    assert first != ()


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    _git(repo, "init")
    _git(repo, "config", "user.email", "qa@example.invalid")
    _git(repo, "config", "user.name", "QA")
    return repo


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(content)


def _commit(repo: Path, message: str, *paths: str, author: str) -> None:
    _git(repo, "add", *paths)
    slug = author.lower()
    _git(repo, "commit", "-m", message, f"--author={author} <{slug}@example.invalid>")


def _git(repo: Path, *args: str) -> None:
    _ = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
