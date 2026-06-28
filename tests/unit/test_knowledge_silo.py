import subprocess
from pathlib import Path

from codescent.engine.packs import KNOWLEDGE_SILO_RULE_PACK, build_pack_registry
from codescent.engine.rules.knowledge_silo import (
    HIGH_CONFIDENCE,
    LOW_CONFIDENCE,
    PYTHON_KNOWLEDGE_SILO_RULE_ID,
    TYPESCRIPT_KNOWLEDGE_SILO_RULE_ID,
    build_knowledge_silo_findings,
)
from codescent.services.git import FileAuthorChurn, git_author_churn


def test_git_author_churn_single_vs_multi_author(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)

    for value in range(5):
        _write(repo / "silo.py", f"VALUE = {value}\n")
        _commit(repo, f"silo {value}", "silo.py", author="Alice")

    for index, author in enumerate(("Alice", "Bob", "Carol", "Dave")):
        _write(repo / "shared.py", f"VALUE = {index}\n")
        _commit(repo, f"shared {index}", "shared.py", author=author)

    churn = git_author_churn(repo)

    assert churn["silo.py"] == FileAuthorChurn(
        churn=5,
        top_author_share=1.0,
        author_count=1,
    )
    assert churn["shared.py"] == FileAuthorChurn(
        churn=4,
        top_author_share=0.25,
        author_count=4,
    )


def test_git_author_churn_self_disables_without_git(tmp_path: Path) -> None:
    assert git_author_churn(tmp_path) == {}


def test_git_author_churn_self_disables_without_history(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    assert git_author_churn(repo) == {}


def test_build_knowledge_silo_findings_classification() -> None:
    findings = build_knowledge_silo_findings(
        {
            "pkg/single.py": FileAuthorChurn(
                churn=6, top_author_share=1.0, author_count=1
            ),
            "pkg/dominant.py": FileAuthorChurn(
                churn=6, top_author_share=0.83, author_count=3
            ),
            "pkg/shared.py": FileAuthorChurn(
                churn=6, top_author_share=0.5, author_count=2
            ),
            "pkg/young.py": FileAuthorChurn(
                churn=2, top_author_share=1.0, author_count=1
            ),
            "app/widget.ts": FileAuthorChurn(
                churn=8, top_author_share=1.0, author_count=1
            ),
            "README.md": FileAuthorChurn(
                churn=10, top_author_share=1.0, author_count=1
            ),
        },
    )

    by_path = {finding.file_path: finding for finding in findings}

    # Well-distributed, young, and non-py/ts files are never flagged.
    assert set(by_path) == {"app/widget.ts", "pkg/dominant.py", "pkg/single.py"}
    assert by_path["pkg/single.py"].rule_id == PYTHON_KNOWLEDGE_SILO_RULE_ID
    assert by_path["pkg/single.py"].confidence == HIGH_CONFIDENCE
    assert by_path["pkg/dominant.py"].confidence == LOW_CONFIDENCE
    assert by_path["app/widget.ts"].rule_id == TYPESCRIPT_KNOWLEDGE_SILO_RULE_ID
    # Git-derived findings are heuristic with explicit git provenance.
    assert by_path["pkg/single.py"].confidence_tier == "heuristic"
    assert by_path["pkg/single.py"].provenance["resolution"] == "git"


def test_build_knowledge_silo_findings_empty_on_no_history() -> None:
    assert build_knowledge_silo_findings({}) == ()


def test_knowledge_silo_pack_is_registered() -> None:
    registry = build_pack_registry()
    assert any(pack.name == KNOWLEDGE_SILO_RULE_PACK for pack in registry.rule_packs)


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
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
