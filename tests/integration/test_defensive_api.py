"""The MCP search/context boundary accepts sloppy LLM inputs additively.

Defensive parsing is strictly MORE accepting: it must never change behavior for
an input that is already valid.
"""

from __future__ import annotations

from codescent.core.defensive import coerce_int, or_empty, resolve_query
from codescent.mcp.search_tools import search_content, search_files

_REPO = "tests/fixtures/python-basic"
_MATCH = "def"
_NO_MATCH = "zzz_never_match_qqq"


def test_pattern_alias_resolves_to_query() -> None:
    payload = search_content(pattern=_MATCH, repo=_REPO)

    assert payload["ok"] is True
    assert payload["query"] == _MATCH
    assert payload["results"]


def test_float_limit_is_coerced_to_int() -> None:
    payload = search_content(_MATCH, repo=_REPO, limit=5.0)  # pyright: ignore[reportArgumentType]

    assert payload["ok"] is True
    assert payload["limit"] == 5
    assert isinstance(payload["limit"], int)


def test_numeric_string_limit_is_coerced_to_int() -> None:
    payload = search_content(_MATCH, repo=_REPO, limit="3")  # pyright: ignore[reportArgumentType]

    assert payload["ok"] is True
    assert payload["limit"] == 3
    assert isinstance(payload["limit"], int)


def test_garbage_limit_degrades_to_default_without_crashing() -> None:
    payload = search_content(_MATCH, repo=_REPO, limit="not-a-number")  # pyright: ignore[reportArgumentType]

    assert payload["ok"] is True
    assert isinstance(payload["limit"], int)
    assert payload["results"]


def test_no_match_query_returns_bounded_empty_not_error() -> None:
    payload = search_content(_NO_MATCH, repo=_REPO)

    assert payload["ok"] is True
    assert payload["results"] == ()
    assert payload["count"] is None
    assert payload["next_cursor"] is None


def test_search_files_pattern_alias_resolves_to_query() -> None:
    payload = search_files(pattern=_MATCH, repo=_REPO)

    assert payload["ok"] is True
    assert payload["query"] == _MATCH


def test_valid_call_is_unchanged_by_the_alias_param() -> None:
    # Warm ranking state first so the frecency signal is saturated: each search
    # records a frecency access, and time-decayed frecency keeps nudging the
    # order until repeated touches push the contested paths past the boost cap
    # (and into the recent-query window). A few warm-up reads saturate them so
    # the two reads below are idempotent regardless of the decayed store state.
    for _ in range(5):
        _ = search_content(_MATCH, repo=_REPO, limit=5)

    canonical = search_content(_MATCH, repo=_REPO, limit=5)
    with_alias = search_content(_MATCH, repo=_REPO, limit=5, pattern="ignored")

    # The canonical query wins; an already-correct call behaves identically.
    assert canonical == with_alias
    assert canonical["query"] == _MATCH
    assert canonical["limit"] == 5


def test_coerce_int_helper() -> None:
    assert coerce_int(5, default=20) == 5
    assert coerce_int(5.0, default=20) == 5
    assert coerce_int("7", default=20) == 7
    assert coerce_int("garbage", default=20) == 20
    assert coerce_int(None, default=20) == 20
    # A bool is not a count; it degrades to the default rather than 0/1.
    assert coerce_int(value=True, default=20) == 20
    # A non-finite numeric string overflows int(float(...)); it must degrade to
    # the default, never raise OverflowError.
    assert coerce_int("inf", default=20) == 20
    assert coerce_int("1e999", default=20) == 20


def test_overflowing_size_constraint_degrades_not_crashes() -> None:
    # A 400-digit size: amount overflows float() to inf; int(inf) in the size
    # parser must not escape and crash the always-on native search floor. The
    # malformed token is dropped and the search still returns a bounded result.
    payload = search_content(_MATCH, repo=_REPO, constraints="size:<" + "9" * 400)

    assert payload["ok"] is True
    assert payload["results"]


def test_resolve_query_prefers_canonical_then_aliases() -> None:
    assert resolve_query("real", "alias") == "real"
    assert resolve_query("", "alias") == "alias"
    assert resolve_query(None, None) == ""


def test_or_empty_degrades_only_input_shape_errors() -> None:
    def boom() -> tuple[int, ...]:
        raise TypeError

    assert or_empty(lambda: (1, 2), ()) == (1, 2)
    assert or_empty(boom, ()) == ()
