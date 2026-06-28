"""U24 .1 -- characterization tests pinning content-anchored finding identity.

A finding's ``stable_key`` must survive benign edits (inserting lines above it,
reformatting) so its lifecycle, ratchet baseline, and verification ledger stay
attached. Absolute source positions therefore must NOT enter the stable_key,
while the finding's substance must -- a rename or different violation is a new
identity by design.
"""

from __future__ import annotations

from codescent.engine.rules.model import EvidenceValue, FindingSpec, build_finding


def _spec(
    rule_id: str,
    *,
    symbol: str | None,
    evidence: dict[str, EvidenceValue],
    file_path: str = "src/pkg/mod.py",
) -> FindingSpec:
    return FindingSpec(
        rule_id=rule_id,
        title="t",
        message="m",
        file_path=file_path,
        symbol=symbol,
        severity="info",
        confidence=0.6,
        evidence=evidence,
        suggested_action="a",
    )


def test_dead_code_identity_ignores_line_positions() -> None:
    # Inserting lines above a dead symbol shifts start_line/end_line only.
    before = build_finding(
        _spec(
            "python.dead_code_candidate",
            symbol="pkg.mod.orphan",
            evidence={"start_line": 1, "end_line": 2, "kind": "function"},
        ),
    )
    after = build_finding(
        _spec(
            "python.dead_code_candidate",
            symbol="pkg.mod.orphan",
            evidence={"start_line": 40, "end_line": 41, "kind": "function"},
        ),
    )
    assert before.stable_key == after.stable_key


def test_architecture_identity_ignores_import_line() -> None:
    before = build_finding(
        _spec(
            "architecture.layer_violation",
            symbol=None,
            evidence={"layer": "services", "imported": "app.cli", "line": 1},
        ),
    )
    after = build_finding(
        _spec(
            "architecture.layer_violation",
            symbol=None,
            evidence={"layer": "services", "imported": "app.cli", "line": 12},
        ),
    )
    assert before.stable_key == after.stable_key


def test_structural_duplicate_identity_anchored_on_content_fingerprint() -> None:
    # `locations` carries "path:start-end:name" line ranges that shift on edits;
    # identity must rest on the content `fingerprint` instead.
    before = build_finding(
        _spec(
            "python.structural_duplicate",
            symbol="pkg.mod.dup",
            evidence={
                "count": 2,
                "fingerprint": "abc123",
                "locations": "src/a.py:1-5:f; src/b.py:1-5:g",
            },
        ),
    )
    after = build_finding(
        _spec(
            "python.structural_duplicate",
            symbol="pkg.mod.dup",
            evidence={
                "count": 2,
                "fingerprint": "abc123",
                "locations": "src/a.py:30-34:f; src/b.py:80-84:g",
            },
        ),
    )
    assert before.stable_key == after.stable_key


def test_reformat_whitespace_preserves_identity() -> None:
    # A large_function's measured size is excluded from identity, so reformatting
    # (which changes line_count) does not re-key it.
    before = build_finding(
        _spec(
            "python.large_function",
            symbol="pkg.mod.process",
            evidence={"line_count": 60, "threshold": 25},
        ),
    )
    after = build_finding(
        _spec(
            "python.large_function",
            symbol="pkg.mod.process",
            evidence={"line_count": 64, "threshold": 25},
        ),
    )
    assert before.stable_key == after.stable_key


def test_rename_changes_identity_by_design() -> None:
    original = build_finding(
        _spec(
            "python.dead_code_candidate",
            symbol="pkg.mod.orphan",
            evidence={"start_line": 1, "end_line": 2, "kind": "function"},
        ),
    )
    renamed = build_finding(
        _spec(
            "python.dead_code_candidate",
            symbol="pkg.mod.renamed",
            evidence={"start_line": 1, "end_line": 2, "kind": "function"},
        ),
    )
    assert original.stable_key != renamed.stable_key


def test_different_substance_changes_identity() -> None:
    # The offending literal is folded into identity: a different literal is a
    # different finding.
    one = build_finding(
        _spec(
            "python.duplicate_literal",
            symbol=None,
            evidence={"literal": "pending-review", "count": 3},
        ),
    )
    two = build_finding(
        _spec(
            "python.duplicate_literal",
            symbol=None,
            evidence={"literal": "in-progress", "count": 3},
        ),
    )
    assert one.stable_key != two.stable_key
