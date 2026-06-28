import logging
from pathlib import Path

import pytest

from codescent.engine.rules.dead_code import build_name_use_index, scan_dead_code

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "python-entrypoint"

_REACHABLE_SYMBOLS = (
    "exported_handler",  # __all__ export
    "decorated_command",  # @app.command() decorator
    "public_entry",  # call-form registration
)
_DEAD_SYMBOL = "acme_entry.handlers._genuinely_dead"


def test_scan_flags_only_genuinely_dead_private_function(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    logger = logging.getLogger("codescent.tests.deadcode_entrypoint")

    index = build_name_use_index(_FIXTURE)
    findings = scan_dead_code(_FIXTURE)
    flagged = [finding.symbol for finding in findings if finding.symbol is not None]

    # Verbose, per-symbol logging of the expected-vs-found decision so the e2e
    # run shows why each reachable symbol is excluded and which one is dead.
    for symbol in _REACHABLE_SYMBOLS:
        reason = index.entry_points.reason_for(symbol)
        logger.info("reachable symbol %r excluded from dead-code: %s", symbol, reason)
        assert reason is not None, f"{symbol} must be a recognized entry point"
        assert symbol not in {s.split(".")[-1] for s in flagged}

    logger.info("dead-code findings: expected=[%s] found=%s", _DEAD_SYMBOL, flagged)
    assert flagged == [_DEAD_SYMBOL]

    finding = findings[0]
    assert finding.rule_id == "python.dead_code_candidate"
    assert finding.symbol == _DEAD_SYMBOL


def test_registered_symbol_carries_reachable_reason() -> None:
    index = build_name_use_index(_FIXTURE)

    # The registered/exported symbols are reachable "via <registration>" even
    # though they have zero internal callers.
    assert index.entry_points.reason_for("how_to_use") is not None
    for symbol in _REACHABLE_SYMBOLS:
        assert index.entry_points.is_entry_point(symbol)


def test_scan_is_deterministic() -> None:
    first = scan_dead_code(_FIXTURE)
    second = scan_dead_code(_FIXTURE)

    assert [f.id for f in first] == [f.id for f in second]
    assert [f.symbol for f in first] == [f.symbol for f in second]
