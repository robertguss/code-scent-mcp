from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final, Literal

from rapidfuzz import fuzz

if TYPE_CHECKING:
    from collections.abc import Mapping

FUZZY_MATCH_THRESHOLD: Final = 60.0
# Personal-first ranking bonuses: what THIS developer actually touches floats up.
CHANGED_FILE_BONUS: Final = 25.0
GIT_MODIFIED_BONUS: Final = 20.0
FRECENCY_BONUS_MULTIPLIER: Final = 30.0
FRECENCY_CAP: Final = 5.0
RECENT_QUERY_BONUS: Final = 15.0
# Code-quality rank deltas: deliberately small tie-breakers/flags, kept
# well below the personal-first bonuses so quality NEVER dominates text
# relevance -- it only nudges and flags. Dead/duplicate code is down-weighted;
# risky hotspot/complex code gets a modest surfacing nudge plus a risk flag.
HOTSPOT_BOOST: Final = 3.0
COMPLEX_BOOST: Final = 2.0
DEAD_CODE_PENALTY: Final = 5.0
DUPLICATE_PENALTY: Final = 3.0
_QUALITY_DELTAS: Final[dict[QualityFlag, float]] = {
    "hotspot": HOTSPOT_BOOST,
    "complex": COMPLEX_BOOST,
    "dead_code": -DEAD_CODE_PENALTY,
    "duplicate": -DUPLICATE_PENALTY,
}


def _empty_frecency() -> dict[str, float]:
    return {}


def _empty_quality() -> dict[str, PathQuality]:
    return {}


QualityFlag = Literal["hotspot", "dead_code", "complex", "duplicate"]


@dataclass(frozen=True, slots=True)
class PathQuality:
    """Derived code-quality for one path, read from persisted findings.

    ``flags`` is the bounded set of quality reasons (``hotspot``/``dead_code``/
    ``duplicate``/``complex``); ``duplicate_twin`` names the other location of a
    structural duplicate when known. Empty flags means neutral (no annotation).
    """

    flags: tuple[QualityFlag, ...] = ()
    duplicate_twin: str | None = None


@dataclass(frozen=True, slots=True)
class PathRank:
    score: float
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RankingSignals:
    """Personal-first ranking signals shared by every retrieval path.

    ``changed`` is the union git/index change set already surfaced as
    ``changed_file``; ``git_modified`` is the narrower git working-tree dirty
    set; ``frecency`` is the decayed access score per path; ``recent_queries``
    is the set of paths a recent query surfaced (query-history); ``quality`` is
    the derived code-quality per path. Each maps to an explainable reason
    string in :func:`apply_signals`.
    """

    changed: frozenset[str] = frozenset()
    git_modified: frozenset[str] = frozenset()
    frecency: Mapping[str, float] = field(default_factory=_empty_frecency)
    recent_queries: frozenset[str] = frozenset()
    quality: Mapping[str, PathQuality] = field(default_factory=_empty_quality)


def apply_signals(
    path: str,
    score: float,
    reasons: tuple[str, ...],
    signals: RankingSignals,
) -> tuple[float, tuple[str, ...]]:
    """Fold the personal-first signals into a base ``(score, reasons)`` pair.

    Each contributing signal appends a named reason so callers can explain why a
    path floated up. Untouched paths return the base pair unchanged (neutral).
    """
    if path in signals.changed:
        score += CHANGED_FILE_BONUS
        reasons = (*reasons, "changed_file")
    if path in signals.git_modified:
        score += GIT_MODIFIED_BONUS
        reasons = (*reasons, "git_modified")
    frecency_score = signals.frecency.get(path, 0.0)
    if frecency_score > 0:
        score += min(frecency_score, FRECENCY_CAP) * FRECENCY_BONUS_MULTIPLIER
        reasons = (*reasons, "frecency")
    if path in signals.recent_queries:
        score += RECENT_QUERY_BONUS
        reasons = (*reasons, "recent_query")
    quality = signals.quality.get(path)
    if quality is not None:
        for flag in quality.flags:
            score += _QUALITY_DELTAS.get(flag, 0.0)
            reasons = (*reasons, flag)
    return score, reasons


def rank_path(path: str, query: str) -> PathRank | None:
    haystack = _match_text(path, query)
    needle = _match_text(query, query)

    if needle in haystack:
        return PathRank(score=100.0, reasons=("exact_path",))

    fuzzy_score = float(fuzz.partial_ratio(needle, haystack))
    if fuzzy_score < FUZZY_MATCH_THRESHOLD:
        return None
    return PathRank(score=fuzzy_score, reasons=("fuzzy_path",))


def _match_text(value: str, query: str) -> str:
    if any(character.isupper() for character in query):
        return value
    return value.lower()
