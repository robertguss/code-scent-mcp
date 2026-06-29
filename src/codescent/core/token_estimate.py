"""Local, deterministic token estimator (KTD-4).

CodeScent counts tokens through a single pluggable helper so the
token-efficiency benchmark (U2) and the answer-pack budget (U6) share one
estimator. It is a word + punctuation heuristic in the chars/4 accuracy class:
approximate but consistent. The benchmark's metric is the *relative* token
delta between the CodeScent path and the naive path, which is robust to
estimator drift.

The estimator is deliberately local and dependency-free: it performs no network
and pulls in no model encoder (e.g. tiktoken), preserving the repo's no-network
invariant. Everything routes through :func:`estimate_tokens`, so a real
tokenizer can replace it later without touching callers.

ponytail: heuristic estimator; swap for a real tokenizer if absolute counts
ever matter.
"""

from __future__ import annotations

import re
from math import ceil

_TOKEN_RE = re.compile(r"\w+|[^\w\s]+")
_CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    """Estimate the token count of ``text`` with a local heuristic.

    Splits the text into word and punctuation runs and charges each run roughly
    one token per four characters (BPE-like), so long identifiers and digit or
    punctuation runs cost more than a single token. The result is deterministic
    and never decreases when characters are appended, so a longer string always
    estimates at least as many tokens as any of its prefixes.

    Args:
        text: The text to estimate.

    Returns:
        A non-negative token-count estimate (``0`` only for whitespace-only or
        empty input).
    """
    runs: list[str] = _TOKEN_RE.findall(text)
    return sum(max(1, ceil(len(run) / _CHARS_PER_TOKEN)) for run in runs)
