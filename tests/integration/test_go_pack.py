import json
from collections import defaultdict
from pathlib import Path
from typing import cast

from codescent.core.models import MaintainabilityThresholds, ProjectConfig
from codescent.engine.packs import build_pack_registry
from codescent.engine.parsers.go import parse_go_file
from codescent.engine.parsers.python import LOW_CONFIDENCE

_FIXTURE = Path("tests/fixtures/go-module")
_EXPECTED = cast(
    "dict[str, object]",
    json.loads(Path("evals/fixtures/go.expected.json").read_text()),
)


def _log(message: str) -> None:
    print(f"[go-eval] {message}")  # noqa: T201 - intentional e2e diagnostic


def _eval_config() -> ProjectConfig:
    limits = cast("dict[str, int]", _EXPECTED["thresholds"])
    return ProjectConfig(
        thresholds=MaintainabilityThresholds(
            large_file_lines=limits["large_file_lines"],
            large_function_lines=limits["large_function_lines"],
            duplicate_literal_min_count=limits["duplicate_literal_min_count"],
            duplicate_literal_min_length=limits["duplicate_literal_min_length"],
        ),
    )


def test_go_pack_registers_with_specific_suffix_and_default_config() -> None:
    registry = build_pack_registry(ProjectConfig())

    assert "go" in {pack.name for pack in registry.language_packs}
    assert "go-maintainability" in {pack.name for pack in registry.rule_packs}
    assert registry.parser_for_language("go") is not None
    go_pack = next(pack for pack in registry.language_packs if pack.name == "go")
    assert go_pack.suffixes == (".go",)


def test_go_pack_disabled_when_config_excludes_it() -> None:
    registry = build_pack_registry(
        ProjectConfig(
            language_packs=("python",), rule_packs=("python-maintainability",)
        ),
    )

    assert registry.parser_for_language("go") is None
    assert "go-maintainability" not in {pack.name for pack in registry.rule_packs}


def test_go_symbols_and_imports_match_expected_low_confidence() -> None:
    symbols_by_file: defaultdict[str, set[tuple[str, str]]] = defaultdict(set)
    for symbol in cast("list[dict[str, str]]", _EXPECTED["symbols"]):
        symbols_by_file[symbol["file"]].add((symbol["qualified_name"], symbol["kind"]))
    imports_by_file: defaultdict[str, set[str]] = defaultdict(set)
    for imported in cast("list[dict[str, str]]", _EXPECTED["imports"]):
        imports_by_file[imported["file"]].add(imported["module"])

    for file, expected in sorted(symbols_by_file.items()):
        parsed = parse_go_file(_FIXTURE / file, file)
        detected = {(s.qualified_name, s.kind) for s in parsed.symbols}
        _log(f"{file} symbols detected={sorted(detected)} expected={sorted(expected)}")
        assert detected == expected
        assert all(s.confidence == LOW_CONFIDENCE for s in parsed.symbols)

    for file, expected_modules in sorted(imports_by_file.items()):
        parsed = parse_go_file(_FIXTURE / file, file)
        found = {imported.module for imported in parsed.imports}
        detail = f"detected={sorted(found)} expected={sorted(expected_modules)}"
        _log(f"{file} imports {detail}")
        assert found == expected_modules
        assert all(imp.confidence == LOW_CONFIDENCE for imp in parsed.imports)


def test_go_findings_match_expected_and_are_deterministic() -> None:
    registry = build_pack_registry(_eval_config())

    first = registry.scan_rule_packs(_FIXTURE)
    second = registry.scan_rule_packs(_FIXTURE)

    first_go = [f for f in first if f.rule_id.startswith("go.")]
    second_go = [f for f in second if f.rule_id.startswith("go.")]
    assert [f.id for f in first_go] == [f.id for f in second_go]

    detected = {(f.file_path, f.rule_id, f.symbol) for f in first_go}
    expected = {
        (e["file"], e["rule_id"], e["symbol"])
        for e in cast("list[dict[str, object]]", _EXPECTED["findings"])
    }
    _log(f"findings detected={sorted(detected)} expected={sorted(expected)}")
    assert detected == expected
    assert {f.rule_id for f in first_go} == {
        "go.large_file",
        "go.large_function",
        "go.missing_nearby_test",
        "go.duplicate_literal",
    }
    assert all(f.provenance["language"] == "go" for f in first_go)
    assert all(f.confidence_tier == "heuristic" for f in first_go)
