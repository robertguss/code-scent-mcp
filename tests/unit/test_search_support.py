from __future__ import annotations

from codescent.engine.search import rank_content
from codescent.engine.search.ranking import FUZZY_MATCH_THRESHOLD


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
