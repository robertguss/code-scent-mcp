from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

from codescent.engine.search import rank_content
from codescent.engine.search.ranking import FUZZY_MATCH_THRESHOLD
from codescent.services.search_support import ranking_signals_for

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_rank_content_exact_substring_scores_full() -> None:
    assert rank_content("def build_hook_payload(event):", "payload") == 100.0


def test_rank_content_case_insensitive_when_query_lowercase() -> None:
    assert rank_content("The PAYLOAD builder", "payload") == 100.0


def test_rank_content_case_sensitive_when_query_has_uppercase() -> None:
    assert rank_content("the payload builder", "PAYLOAD") is None


def test_rank_content_fuzzy_typo_above_threshold() -> None:
    score = rank_content("configure the widget", "configuer")
    assert score is not None
    assert score >= FUZZY_MATCH_THRESHOLD


def test_rank_content_unrelated_returns_none() -> None:
    assert rank_content("completely different sentence", "xylophone") is None


def test_ranking_signals_collapses_to_single_git_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ranking hot path must fire ONE ``git status``, not three (bead 4y8o).

    Two ``git_changed_paths`` calls plus a ``detect_git_state`` used to shell out
    three times per query for data one porcelain pass carries.
    """
    (tmp_path / ".git").mkdir()
    status_calls = 0

    def fake_run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal status_calls
        if "status" in cmd:
            status_calls += 1
        return subprocess.CompletedProcess(cmd, 0, stdout=" M b.py\n", stderr="")

    def fake_which(_name: str) -> str:
        return "/usr/bin/git"

    monkeypatch.setattr("codescent.services.git.subprocess.run", fake_run)
    monkeypatch.setattr("codescent.services.git.which", fake_which)

    signals = ranking_signals_for(tmp_path)

    assert status_calls == 1
    assert "b.py" in signals.git_modified
