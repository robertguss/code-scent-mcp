"""Defensive parsing for the MCP boundary: accept sloppy LLM inputs.

The MCP search and context tools land the broadest range of caller inputs. These
helpers make the boundary MORE accepting -- resolving common parameter aliases,
coercing numeric-looking values to ints, and degrading a malformed input to a
bounded empty result instead of raising -- without ever changing behavior for an
input that is already valid. The alias table is surfaced by ``get_schema`` so a
caller can discover which sloppy spellings are accepted.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Callable

# Parameter aliases folded into their canonical name at the boundary. Kept here
# as the single source of truth so ``get_schema`` advertises exactly what the
# tools wire up; widen only when a tool actually accepts the new alias.
QUERY_ALIASES: Final[tuple[str, ...]] = ("pattern",)
PARAM_ALIASES: Final[dict[str, str]] = dict.fromkeys(QUERY_ALIASES, "query")


def resolve_query(query: str | None, *aliases: str | None) -> str:
    """Return the first non-empty query, accepting alias spellings.

    Args:
        query: The canonical ``query`` value (may be empty or ``None``).
        *aliases: Alias values (e.g. a ``pattern=`` kwarg) tried in order when
            ``query`` is empty.

    Returns:
        The first non-empty value, or ``""`` when none is provided.
    """
    for value in (query, *aliases):
        if value:
            return value
    return ""


def coerce_int(value: object, *, default: int) -> int:
    """Coerce a float, numeric string, or int to int; fall back to ``default``.

    Args:
        value: The raw value (``int``, ``float``, numeric ``str``, or other).
        default: The value returned when ``value`` cannot be parsed as a number.

    Returns:
        The integer form of ``value``, or ``default`` when it is not numeric.
    """
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value.strip()))
        except (ValueError, OverflowError):
            # OverflowError guards int(float("inf"))/int(float("1e999")): a
            # non-finite numeric string degrades to the default, never raises.
            return default
    return default


def or_empty[T](producer: Callable[[], T], empty: T) -> T:
    """Run a bounded producer, degrading a malformed-input failure to ``empty``.

    Args:
        producer: A zero-argument callable returning the bounded result.
        empty: The well-formed empty result returned when the producer rejects a
            malformed input.

    Returns:
        The producer's result, or ``empty`` when it raises on a bad input.
    """
    try:
        result = producer()
    except (ValueError, TypeError, OverflowError):
        # ponytail: catch only input-shape errors; real bugs (OSError, KeyError)
        # still surface. OverflowError covers non-finite numbers a malformed
        # size:/mtime: token can produce. Widen only for a new sloppy-input mode.
        return empty
    return result
