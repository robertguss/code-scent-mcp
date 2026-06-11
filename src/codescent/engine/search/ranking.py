from dataclasses import dataclass
from typing import Final

from rapidfuzz import fuzz

FUZZY_MATCH_THRESHOLD: Final = 60.0


@dataclass(frozen=True, slots=True)
class PathRank:
    score: float
    reasons: tuple[str, ...]


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
