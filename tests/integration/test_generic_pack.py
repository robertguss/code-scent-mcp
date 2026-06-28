from pathlib import Path

from codescent.core.models import MaintainabilityThresholds, ProjectConfig
from codescent.engine.packs import build_pack_registry

_FIXTURE = Path("tests/fixtures/generic-fallback")


def _log(message: str) -> None:
    print(f"[generic-eval] {message}")  # noqa: T201 - intentional e2e diagnostic


def _low_thresholds() -> MaintainabilityThresholds:
    # Low enough that the tiny fixtures trip every text heuristic.
    return MaintainabilityThresholds(
        large_file_lines=10,
        todo_cluster_size=3,
        duplicate_literal_min_count=3,
        duplicate_literal_min_length=4,
    )


def test_generic_pack_registered_last_and_toggle() -> None:
    on = build_pack_registry(ProjectConfig())
    names = tuple(pack.name for pack in on.rule_packs)
    _log(f"rule packs (fallback on) = {names}")
    assert names[-1] == "generic"
    assert names == (
        "architecture",
        "knowledge-silo",
        "python-maintainability",
        "ts-react-next",
        "go-maintainability",
        "generic",
    )
    # The fallback is a rule pack only -- no parser, so it never appears as a
    # language pack and never resolves a language.
    assert "generic" not in {pack.name for pack in on.language_packs}

    off = build_pack_registry(ProjectConfig(generic_fallback=False))
    assert "generic" not in {pack.name for pack in off.rule_packs}


def test_generic_rules_fire_on_unsupported_language_without_symbols() -> None:
    registry = build_pack_registry(ProjectConfig(thresholds=_low_thresholds()))
    findings = [
        f
        for f in registry.scan_rule_packs(_FIXTURE)
        if f.rule_id.startswith("generic.")
    ]
    by_rule = {f.rule_id: f for f in findings}
    _log(f"generic findings = {sorted((f.rule_id, f.file_path) for f in findings)}")

    assert set(by_rule) == {
        "generic.large_file",
        "generic.todo_cluster",
        "generic.duplicate_literal",
    }
    # Degrade honestly: text-only, no structural/semantic claims.
    assert all(f.symbol is None for f in findings)
    assert all(f.confidence_tier == "heuristic" for f in findings)
    assert all(f.provenance["language"] == "generic" for f in findings)
    assert all(f.provenance["resolution"] == "text" for f in findings)
    assert all(f.provenance["symbol_resolved"] is False for f in findings)
    # Every finding lands on the smelly Ruby file, never the clean text file.
    assert all(f.file_path == "lib/widget.rb" for f in findings)
    assert by_rule["generic.duplicate_literal"].evidence["literal"] == "pending-review"


def test_generic_findings_are_deterministic() -> None:
    registry = build_pack_registry(ProjectConfig(thresholds=_low_thresholds()))
    first = [
        f.id
        for f in registry.scan_rule_packs(_FIXTURE)
        if f.rule_id.startswith("generic.")
    ]
    second = [
        f.id
        for f in registry.scan_rule_packs(_FIXTURE)
        if f.rule_id.startswith("generic.")
    ]
    _log(f"determinism: {first} == {second}")
    assert first == second


def test_specific_packs_win_for_their_own_suffixes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    big = "\n".join(f"value_{i} = {i}" for i in range(20)) + "\n"
    (repo / "src").mkdir(parents=True)
    _ = (repo / "src" / "big.py").write_text(big)
    _ = (repo / "src" / "big.ts").write_text(big)
    _ = (repo / "main.go").write_text("package main\n\n" + big)
    _ = (repo / "legacy.rb").write_text(big)

    registry = build_pack_registry(ProjectConfig(thresholds=_low_thresholds()))
    findings = registry.scan_rule_packs(repo)
    generic_files = {f.file_path for f in findings if f.rule_id.startswith("generic.")}
    _log(f"generic touched files = {sorted(generic_files)}")

    # The fallback fires only on the unsupported-language file.
    assert generic_files == {"legacy.rb"}
    # Specific packs handled their own files (sanity: the Python pack ran).
    assert any(
        f.rule_id == "python.large_file" and f.file_path == "src/big.py"
        for f in findings
    )
    # No generic.* claim ever lands on a specific-pack suffix.
    assert not any(
        f.rule_id.startswith("generic.") and f.file_path.endswith((".py", ".ts", ".go"))
        for f in findings
    )


def test_disabling_fallback_yields_no_generic_findings(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / "legacy.rb").write_text(
        "\n".join(f"x = {i} # TODO done?" for i in range(20)) + "\n",
    )

    enabled = build_pack_registry(ProjectConfig(thresholds=_low_thresholds()))
    disabled = build_pack_registry(
        ProjectConfig(thresholds=_low_thresholds(), generic_fallback=False),
    )
    enabled_generic = [
        f for f in enabled.scan_rule_packs(repo) if f.rule_id.startswith("generic.")
    ]
    disabled_generic = [
        f for f in disabled.scan_rule_packs(repo) if f.rule_id.startswith("generic.")
    ]
    _log(f"enabled={len(enabled_generic)} disabled={len(disabled_generic)}")

    assert enabled_generic  # sanity: it would have fired
    assert disabled_generic == []
