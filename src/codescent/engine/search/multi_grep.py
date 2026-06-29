"""Multi-pattern literal matcher (plan unit U10 / bead P2.3).

One pass finds every line matching ANY of many literal patterns, so impact
analysis can trace many identifiers in a single sweep instead of N searches.

Tier dispatch: when the optional ``pyahocorasick`` accelerator is installed, an
Aho-Corasick automaton scans each line once for all patterns at once; otherwise
a native single-scan fallback yields the IDENTICAL match set. ``pyahocorasick``
is OPTIONAL and imported lazily, so the base install runs on the native tier
with no extra dependency.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, cast

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence


class _Automaton(Protocol):
    """The slice of the pyahocorasick ``Automaton`` API this matcher uses."""

    def add_word(self, key: str, value: int) -> bool: ...
    def make_automaton(self) -> None: ...
    def iter(self, haystack: str, /) -> Iterable[tuple[int, int]]: ...


def multi_grep(
    patterns: Sequence[str],
    lines: Sequence[str],
) -> dict[str, tuple[int, ...]]:
    """Map each literal pattern to the 0-based line indexes where it occurs.

    Smart-case per pattern (matching the native ``match_text`` floor): a pattern
    containing any uppercase letter is matched case-sensitively, an all-lowercase
    pattern case-insensitively. Empty and duplicate patterns are dropped.

    Args:
        patterns: Literal substrings to trace (deduped; empty strings ignored).
        lines: The file content to scan, one entry per line.

    Returns:
        A mapping of each retained pattern to its sorted matching line indexes.
    """
    retained = tuple(dict.fromkeys(pattern for pattern in patterns if pattern))
    if not retained:
        return {}
    sensitive = tuple(pattern for pattern in retained if _has_upper(pattern))
    insensitive = tuple(pattern for pattern in retained if not _has_upper(pattern))
    hits: dict[str, set[int]] = {pattern: set() for pattern in retained}
    # ponytail: the automaton is rebuilt per call (per file); building it once
    # and reusing across files is the upgrade path if profiling ever shows the
    # construction cost matters next to scanning.
    factory = _automaton_factory()
    if factory is None:
        _scan_native(sensitive, insensitive, lines, hits)
    else:
        _scan_automaton(factory, sensitive, lines, hits, lower=False)
        _scan_automaton(factory, insensitive, lines, hits, lower=True)
    return {pattern: tuple(sorted(found)) for pattern, found in hits.items()}


def _has_upper(text: str) -> bool:
    return any(character.isupper() for character in text)


def _automaton_factory() -> Callable[[], _Automaton] | None:
    """Return pyahocorasick's ``Automaton`` constructor, or None when absent.

    The optional ``pyahocorasick`` accelerator is imported lazily so the base
    install never requires it; an ``ImportError`` selects the native tier. The
    compiled module ships no stubs, so its ``Automaton`` constructor is cast to
    the typed ``_Automaton`` contract this matcher relies on.
    """
    try:
        import ahocorasick  # noqa: PLC0415
    except ImportError:
        return None
    return cast("Callable[[], _Automaton]", ahocorasick.Automaton)


def _scan_automaton(
    factory: Callable[[], _Automaton],
    group: Sequence[str],
    lines: Sequence[str],
    hits: dict[str, set[int]],
    *,
    lower: bool,
) -> None:
    if not group:
        return
    automaton = factory()
    for index, pattern in enumerate(group):
        _ = automaton.add_word(pattern, index)
    automaton.make_automaton()
    for line_no, line in enumerate(lines):
        haystack = line.lower() if lower else line
        for _end, index in automaton.iter(haystack):
            hits[group[index]].add(line_no)


def _scan_native(
    sensitive: Sequence[str],
    insensitive: Sequence[str],
    lines: Sequence[str],
    hits: dict[str, set[int]],
) -> None:
    for line_no, line in enumerate(lines):
        lowered = line.lower()
        for pattern in sensitive:
            if pattern in line:
                hits[pattern].add(line_no)
        for pattern in insensitive:
            if pattern in lowered:
                hits[pattern].add(line_no)
