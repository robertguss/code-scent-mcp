"""Multi-pattern literal matcher.

One pass finds every line matching ANY of many literal patterns, so impact
analysis can trace many identifiers in a single sweep instead of N searches.

Tier dispatch: when the optional ``pyahocorasick`` accelerator is installed, an
Aho-Corasick automaton scans each line once for all patterns at once; otherwise
a native single-scan fallback yields the IDENTICAL match set. ``pyahocorasick``
is OPTIONAL and imported lazily, so the base install runs on the native tier
with no extra dependency.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, cast, final

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence


class _Automaton(Protocol):
    """The slice of the pyahocorasick ``Automaton`` API this matcher uses."""

    def add_word(self, key: str, value: int) -> bool: ...
    def make_automaton(self) -> None: ...
    def iter(self, haystack: str, /) -> Iterable[tuple[int, int]]: ...


@final
class MultiMatcher:
    """A multi-pattern literal matcher compiled once, then reused across files.

    Smart-case per pattern (matching the native ``match_text`` floor): a pattern
    containing any uppercase letter is matched case-sensitively, an all-lowercase
    pattern case-insensitively. Empty and duplicate patterns are dropped.

    The Aho-Corasick automaton is built ONCE at construction (per query / pattern
    set) rather than per scanned file, so a caller sweeping many files pays the
    construction cost once and reuses the compiled automaton for every ``scan``.
    """

    __slots__ = ("_insensitive", "_matchers", "_retained", "_sensitive")

    def __init__(self, patterns: Sequence[str]) -> None:
        """Compile the automaton(s) for ``patterns`` once (deduped, empties dropped)."""
        self._retained = tuple(
            dict.fromkeys(pattern for pattern in patterns if pattern)
        )
        self._sensitive = tuple(p for p in self._retained if _has_upper(p))
        self._insensitive = tuple(p for p in self._retained if not _has_upper(p))
        factory = _automaton_factory()
        # Compile the sensitive/insensitive automatons up front (None on the
        # native tier or for an empty group); scan() never rebuilds them.
        self._matchers: tuple[_Automaton | None, _Automaton | None] | None = (
            None
            if factory is None
            else (
                _build_automaton(factory, self._sensitive),
                _build_automaton(factory, self._insensitive),
            )
        )

    def scan(self, lines: Sequence[str]) -> dict[str, tuple[int, ...]]:
        """Map each retained pattern to the 0-based line indexes where it occurs.

        Args:
            lines: One file's content to scan, one entry per line.

        Returns:
            A mapping of each retained pattern to its sorted matching line
            indexes (empty tuple for a pattern that does not occur).
        """
        if not self._retained:
            return {}
        hits: dict[str, set[int]] = {pattern: set() for pattern in self._retained}
        if self._matchers is None:
            _scan_native(self._sensitive, self._insensitive, lines, hits)
        else:
            sensitive_auto, insensitive_auto = self._matchers
            _scan_prebuilt(sensitive_auto, self._sensitive, lines, hits, lower=False)
            _scan_prebuilt(
                insensitive_auto, self._insensitive, lines, hits, lower=True
            )
        return {pattern: tuple(sorted(found)) for pattern, found in hits.items()}


def multi_grep(
    patterns: Sequence[str],
    lines: Sequence[str],
) -> dict[str, tuple[int, ...]]:
    """Scan a single file's ``lines`` for ``patterns`` (one-shot convenience).

    Equivalent to ``MultiMatcher(patterns).scan(lines)``. Callers sweeping many
    files should build one :class:`MultiMatcher` and reuse it so the automaton is
    compiled once per query rather than once per file.
    """
    return MultiMatcher(patterns).scan(lines)


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


def _build_automaton(
    factory: Callable[[], _Automaton],
    group: Sequence[str],
) -> _Automaton | None:
    """Compile an automaton for ``group`` once, or None when the group is empty."""
    if not group:
        return None
    automaton = factory()
    for index, pattern in enumerate(group):
        _ = automaton.add_word(pattern, index)
    automaton.make_automaton()
    return automaton


def _scan_prebuilt(
    automaton: _Automaton | None,
    group: Sequence[str],
    lines: Sequence[str],
    hits: dict[str, set[int]],
    *,
    lower: bool,
) -> None:
    if automaton is None:
        return
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
