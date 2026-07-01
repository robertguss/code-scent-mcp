"""Constraints DSL data model + parser.

A space-separated mini-language scopes path + content search BEFORE ranking and
before the result bound, so the agent trades many narrowing tool calls for one
token. Each whitespace token is one constraint; combined tokens AND together:

    git:modified   keep files git reports as changed (modified / added / untracked)
    git:untracked  keep only untracked files
    *.py           extension / glob -- fnmatch over the repo-relative path
    src/           path prefix -- kept when the path starts with it
    !tests/        exclusion -- drop paths matching the inner glob or prefix
    size:<10kb     file-size bound -- operators < <= > >=, units b / kb / mb
    mtime:<7d      modified within (<) or older than (>) N -- units s m h d w

Unknown or malformed tokens are ignored, never raised, mirroring the
degrade-don't-crash spirit of ``core/defensive.py``. An empty constraint string
parses to an empty set whose filter (see ``constraints_filter``) is a no-op, so
default search is unchanged.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final, Literal

if TYPE_CHECKING:
    from collections.abc import Callable

GitKind = Literal["modified", "untracked"]
SizeOp = Literal["<", "<=", ">", ">="]
TimeOp = Literal["<", ">"]

_GLOB_CHARS: Final = frozenset("*?[")
_SIZE_UNITS: Final[dict[str, int]] = {
    "b": 1,
    "k": 1024,
    "kb": 1024,
    "m": 1024 * 1024,
    "mb": 1024 * 1024,
}
_TIME_UNITS: Final[dict[str, float]] = {
    "s": 1.0,
    "m": 60.0,
    "h": 3600.0,
    "d": 86400.0,
    "w": 604800.0,
}


@dataclass(frozen=True, slots=True)
class ConstraintKind:
    """One documented constraint token plus a one-line description."""

    token: str
    description: str


# Single source of truth for the kinds ``get_schema`` advertises.
CONSTRAINT_KINDS: Final[tuple[ConstraintKind, ...]] = (
    ConstraintKind(
        "git:modified",
        "keep files git reports as changed (modified / added / untracked)",
    ),
    ConstraintKind("git:untracked", "keep only untracked files"),
    ConstraintKind("*.py", "extension or glob; fnmatch over the repo-relative path"),
    ConstraintKind("src/", "path prefix; kept when the path starts with it"),
    ConstraintKind("!tests/", "exclusion; drop paths matching the inner glob/prefix"),
    ConstraintKind("size:<10kb", "file-size bound; operators < <= > >=, units b/kb/mb"),
    ConstraintKind(
        "mtime:<7d", "modified within (<) or older than (>) N; units s/m/h/d/w"
    ),
)


@dataclass(frozen=True, slots=True)
class ExcludePattern:
    """A negated pattern: a path matching it is dropped."""

    pattern: str
    is_glob: bool


@dataclass(frozen=True, slots=True)
class SizeConstraint:
    op: SizeOp
    threshold_bytes: int


@dataclass(frozen=True, slots=True)
class TimeConstraint:
    op: TimeOp
    seconds: float


@dataclass(frozen=True, slots=True)
class GitPaths:
    """Injected git status sets so callers/tests avoid nondeterministic git I/O."""

    modified: frozenset[str] = frozenset()
    untracked: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class ConstraintSet:
    """A parsed, typed constraint string. All groups AND together when filtering."""

    globs: tuple[str, ...] = ()
    prefixes: tuple[str, ...] = ()
    excludes: tuple[ExcludePattern, ...] = ()
    git_kinds: frozenset[GitKind] = frozenset()
    sizes: tuple[SizeConstraint, ...] = ()
    times: tuple[TimeConstraint, ...] = ()
    # Raw tokens that were dropped as unknown/malformed. Surfaced as
    # ``constraint_warnings`` so a silently-ignored token is no longer trusted as
    # a filter (F2). Not part of ``is_empty`` — it is diagnostics, not a filter.
    ignored: tuple[str, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not (
            self.globs
            or self.prefixes
            or self.excludes
            or self.git_kinds
            or self.sizes
            or self.times
        )

    @property
    def needs_stat(self) -> bool:
        return bool(self.sizes or self.times)


@dataclass(slots=True)
class _Builder:
    globs: list[str] = field(default_factory=list)
    prefixes: list[str] = field(default_factory=list)
    excludes: list[ExcludePattern] = field(default_factory=list)
    git_kinds: set[GitKind] = field(default_factory=set)
    sizes: list[SizeConstraint] = field(default_factory=list)
    times: list[TimeConstraint] = field(default_factory=list)
    ignored: list[str] = field(default_factory=list)

    def build(self) -> ConstraintSet:
        return ConstraintSet(
            globs=tuple(self.globs),
            prefixes=tuple(self.prefixes),
            excludes=tuple(self.excludes),
            git_kinds=frozenset(self.git_kinds),
            sizes=tuple(self.sizes),
            times=tuple(self.times),
            ignored=tuple(self.ignored),
        )


def parse_constraints(text: str) -> ConstraintSet:
    """Parse a space-separated constraint string into a typed constraint set.

    Args:
        text: The raw ``constraints`` value (possibly empty or malformed).

    Returns:
        The parsed :class:`ConstraintSet`; unknown/malformed tokens are dropped.
    """
    builder = _Builder()
    for token in text.split():
        _classify(builder, token)
    return builder.build()


def constraint_warnings(text: str) -> tuple[str, ...]:
    """Human-readable warning per dropped token in ``text``.

    Runs the real :func:`parse_constraints` (no re-implementation, so it can
    never drift from the actual filter) and formats every token it dropped.
    Because ``parse_constraints`` never short-circuits, this warns even when
    every token is malformed and the resulting filter is empty (the F2 repro).
    """
    return tuple(_ignored_message(token) for token in parse_constraints(text).ignored)


def _ignored_message(token: str) -> str:
    if token.startswith("size:"):
        return (
            f"ignored {token!r} — expected e.g. size:<10kb "
            "(operators < <= > >=, units b/kb/mb)"
        )
    if token.startswith("mtime:"):
        return (
            f"ignored {token!r} — expected e.g. mtime:<7d "
            "(operators < >, units s/m/h/d/w)"
        )
    if token.startswith("git:"):
        return f"ignored {token!r} — expected git:modified or git:untracked"
    if token.startswith("!"):
        return f"ignored {token!r} — exclusion needs a pattern after '!'"
    return f"ignored {token!r} — unknown constraint scheme"


def is_glob(token: str) -> bool:
    """Return whether ``token`` contains a glob metacharacter (``* ? [``)."""
    return any(character in _GLOB_CHARS for character in token)


def _classify(builder: _Builder, token: str) -> None:
    handler = _scheme_handler(token)
    if handler is not None:
        handler(builder, token)
    elif is_glob(token):
        builder.globs.append(token)
    elif token and ":" not in token:
        # A bare token is a path prefix; a ``scheme:`` token with an unknown
        # scheme is ignored rather than mistaken for a prefix.
        builder.prefixes.append(token)
    elif token:
        # A ``scheme:`` token whose scheme we do not recognise — record it so the
        # drop is surfaced instead of silently trusted.
        builder.ignored.append(token)


def _handle_exclude(builder: _Builder, token: str) -> None:
    inner = token.removeprefix("!")
    if inner:
        builder.excludes.append(ExcludePattern(pattern=inner, is_glob=is_glob(inner)))
    else:
        builder.ignored.append(token)


def _handle_git(builder: _Builder, token: str) -> None:
    value = token.removeprefix("git:")
    if value in {"modified", "changed"}:
        builder.git_kinds.add("modified")
    elif value == "untracked":
        builder.git_kinds.add("untracked")
    else:
        builder.ignored.append(token)


def _handle_size(builder: _Builder, token: str) -> None:
    parsed = _parse_size(token.removeprefix("size:"))
    if parsed is not None:
        builder.sizes.append(parsed)
    else:
        builder.ignored.append(token)


def _handle_time(builder: _Builder, token: str) -> None:
    parsed = _parse_time(token.removeprefix("mtime:"))
    if parsed is not None:
        builder.times.append(parsed)
    else:
        builder.ignored.append(token)


_SCHEMES: Final[tuple[tuple[str, Callable[[_Builder, str], None]], ...]] = (
    ("!", _handle_exclude),
    ("git:", _handle_git),
    ("size:", _handle_size),
    ("mtime:", _handle_time),
)


def _scheme_handler(token: str) -> Callable[[_Builder, str], None] | None:
    for prefix, handler in _SCHEMES:
        if token.startswith(prefix):
            return handler
    return None


def _parse_size(value: str) -> SizeConstraint | None:
    op, rest = _split_size_op(value)
    if op is None:
        return None
    amount = _parse_amount(rest, _SIZE_UNITS, default_unit="b")
    if amount is None:
        return None
    return SizeConstraint(op=op, threshold_bytes=int(amount))


def _parse_time(value: str) -> TimeConstraint | None:
    if not value or value[0] not in "<>":
        return None
    seconds = _parse_amount(value[1:], _TIME_UNITS, default_unit="d")
    if seconds is None:
        return None
    op: TimeOp = "<" if value[0] == "<" else ">"
    return TimeConstraint(op=op, seconds=seconds)


def _split_size_op(value: str) -> tuple[SizeOp | None, str]:
    ops: tuple[SizeOp, ...] = ("<=", ">=", "<", ">")
    for op in ops:
        if value.startswith(op):
            return op, value[len(op) :]
    return None, value


def _parse_amount(
    text: str,
    units: dict[str, float] | dict[str, int],
    *,
    default_unit: str,
) -> float | None:
    digits, unit = _split_number(text.strip().lower())
    if digits is None:
        return None
    multiplier = units.get(unit or default_unit)
    if multiplier is None:
        return None
    try:
        amount = float(digits) * multiplier
    except ValueError:
        return None
    if not math.isfinite(amount):
        # float('9'*400) overflows to inf without raising; int(inf) in
        # _parse_size would crash the always-on native floor, so drop it like
        # any malformed token (module docstring): degrade, never raise.
        return None
    return amount


def _split_number(text: str) -> tuple[str | None, str]:
    index = 0
    while index < len(text) and (text[index].isdigit() or text[index] == "."):
        index += 1
    if index == 0:
        return None, text
    return text[:index], text[index:]
