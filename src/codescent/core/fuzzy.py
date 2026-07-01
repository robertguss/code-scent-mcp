"""Small "did you mean" helper for error-recovery suggestions.

Reuses the deterministic ``rapidfuzz.fuzz.partial_ratio`` scorer already used in
the search-ranking path (``engine/search/ranking.py``) — no new dependency and
no network/LLM, so recovery hints stay within the North-Star fact-path floor.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from rapidfuzz import fuzz

if TYPE_CHECKING:
    from collections.abc import Iterable

# Mirrors ``engine/search/ranking.FUZZY_MATCH_THRESHOLD`` — below this a match is
# too weak to suggest as a likely typo.
FUZZY_MATCH_THRESHOLD: Final = 60.0


def nearest_matches(
    query: str,
    candidates: Iterable[str],
    *,
    limit: int = 5,
    threshold: float = FUZZY_MATCH_THRESHOLD,
) -> tuple[str, ...]:
    """Return up to ``limit`` candidates closest to ``query``, best first."""
    scored = sorted(
        ((fuzz.partial_ratio(query, candidate), candidate) for candidate in candidates),
        key=lambda pair: pair[0],
        reverse=True,
    )
    return tuple(candidate for score, candidate in scored[:limit] if score >= threshold)
