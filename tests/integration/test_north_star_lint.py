"""Tests for the navigator north-star lint (roadmap Phase 0.1 / bead P0.1)."""

from __future__ import annotations

from pathlib import Path

from scripts.check_north_star import (
    ANTI_DRIFT_HEADER,
    NORTH_STAR_HEADER,
    check_north_star,
    main,
)

REPO_AGENTS_MD = Path("AGENTS.md")


def test_repo_agents_md_has_north_star() -> None:
    assert check_north_star(REPO_AGENTS_MD) is True
    assert main([str(REPO_AGENTS_MD.resolve().parent)]) == 0


def test_repo_agents_md_contains_section_and_checklist() -> None:
    text = REPO_AGENTS_MD.read_text(encoding="utf-8")
    assert NORTH_STAR_HEADER in text
    assert ANTI_DRIFT_HEADER in text
    # The four guardrails must all be present.
    for guardrail in (
        "Facts stay deterministic",
        "LLM layer is opt-in",
        "Stay bounded",
        "Engines stay optional",
    ):
        assert guardrail in text, f"missing guardrail: {guardrail}"


def test_lint_fails_when_section_absent(tmp_path: Path) -> None:
    stripped = tmp_path / "AGENTS.md"
    _ = stripped.write_text("# PROJECT\n\nNo north star here.\n", encoding="utf-8")
    assert check_north_star(stripped) is False
    assert main([str(tmp_path)]) == 1


def test_lint_fails_when_file_missing(tmp_path: Path) -> None:
    assert check_north_star(tmp_path / "AGENTS.md") is False
    assert main([str(tmp_path)]) == 1
