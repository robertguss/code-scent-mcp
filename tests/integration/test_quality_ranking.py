"""Quality-aware retrieval ranking + inline annotations (plan unit U13 / P3.2).

The moat: the navigator does not just find code, it tells you the code's health
inline. Retrieval results are annotated with derived quality signals (hotspot,
dead code, structural duplication, complexity) and reranked -- dead/duplicate
code is down-weighted, risky hotspot/complex code is flagged. The signals are
READ from the persisted Inspector findings; they never trigger a scan and never
mutate a finding, so ``scan_code_health`` stays byte-identical (KTD-8).
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

from codescent.core.models import MaintainabilityThresholds, ProjectConfig
from codescent.services.code_health import CodeHealthService
from codescent.services.config import ConfigService
from codescent.services.quality_signals import QualityAnnotation, quality_signals_for
from codescent.services.search import SearchService

if TYPE_CHECKING:
    from pathlib import Path

    from codescent.services.search_support import SearchResultPayload

# A large function (> strict large_function_lines=25) so it carries a size
# finding; referenced via the module-level call so it is not also dead code.
_HOTSPOT_SOURCE = """def hotspot_metric(rows):
    total = 0
    count = 0
    smallest = None
    largest = None
    history = []
    for row in rows:
        total = total + row
        count = count + 1
        if smallest is None:
            smallest = row
        if largest is None:
            largest = row
        if row < smallest:
            smallest = row
        if row > largest:
            largest = row
        midpoint = total / count
        spread = (largest or 0) - (smallest or 0)
        adjusted = midpoint + spread
        scaled = adjusted * 2
        trimmed = scaled - 1
        report = trimmed + count
        history.append(report)
        rolling = sum(history)
        normalized = rolling / count
    average = total / count if count else 0
    summary = (average, smallest, largest, normalized)
    return summary


_READY = hotspot_metric([1, 2, 3])
"""

_DEAD_SOURCE = """def authenticate_unused(user):
    return user is None
"""

_CLEAN_SOURCE = """def authenticate(user):
    return user is not None


_OK = authenticate(None)
"""

_DUPLICATE_BODY = """def {name}(items):
    total = 0
    doubled = []
    for item in items:
        total = total + item
        doubled.append(item * 2)
    average = total / len(items)
    return average, doubled


{assigned} = {name}([1, 2, 3])
"""

_COMPLEX_SOURCE = """def deeply_nested(values):
    for outer in values:
        if outer:
            for inner in outer:
                if inner:
                    while inner:
                        inner = inner - 1
    return values


_NESTED = deeply_nested([])
"""


def _run_git(repo: Path, *args: str) -> None:
    _ = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _write_sources(repo: Path) -> None:
    src = repo / "src"
    src.mkdir(parents=True)
    _ = (src / "hot.py").write_text(_HOTSPOT_SOURCE)
    _ = (src / "dead.py").write_text(_DEAD_SOURCE)
    _ = (src / "clean.py").write_text(_CLEAN_SOURCE)
    _ = (src / "dup_a.py").write_text(
        _DUPLICATE_BODY.format(name="process_alpha", assigned="_A"),
    )
    _ = (src / "dup_b.py").write_text(
        _DUPLICATE_BODY.format(name="process_beta", assigned="_B"),
    )
    _ = (src / "nested.py").write_text(_COMPLEX_SOURCE)


def _commit_repo(repo: Path) -> None:
    _run_git(repo, "init")
    _run_git(repo, "config", "user.email", "codescent@example.test")
    _run_git(repo, "config", "user.name", "CodeScent Test")
    _run_git(repo, "add", "src")
    _run_git(repo, "commit", "-m", "initial")


def _seeded_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_sources(repo)
    _commit_repo(repo)
    ConfigService(repo).save(
        ProjectConfig(thresholds=MaintainabilityThresholds.strict()),
    )
    _ = CodeHealthService(repo).scan()
    return repo


def _result_for(
    results: tuple[SearchResultPayload, ...],
    suffix: str,
) -> SearchResultPayload:
    for result in results:
        if result["path"].endswith(suffix):
            return result
    message = f"no result for {suffix}"
    raise AssertionError(message)


def _quality(result: SearchResultPayload) -> QualityAnnotation:
    annotation = result.get("quality")
    assert annotation is not None
    return annotation


def test_hotspot_path_carries_hotspot_flag(tmp_path: Path) -> None:
    repo = _seeded_repo(tmp_path)

    results = SearchService(repo).search_content("hotspot_metric")

    hit = _result_for(results, "hot.py")
    assert "hotspot" in _quality(hit)["flags"]
    assert "hotspot" in hit["reasons"]


def test_dead_code_is_down_weighted_and_flagged(tmp_path: Path) -> None:
    repo = _seeded_repo(tmp_path)

    results = SearchService(repo).search_content("authenticate")

    dead = _result_for(results, "dead.py")
    clean = _result_for(results, "clean.py")
    assert "dead_code" in _quality(dead)["flags"]
    assert "dead_code" in dead["reasons"]
    # Dead code carries a penalty, so it ranks below equally-relevant live code.
    assert dead["score"] < clean["score"]
    assert clean.get("quality") is None


def test_structural_duplicate_names_its_twin(tmp_path: Path) -> None:
    repo = _seeded_repo(tmp_path)

    results = SearchService(repo).search_content("doubled")

    dup = _result_for(results, "dup_a.py")
    quality = _quality(dup)
    assert "duplicate" in quality["flags"]
    twin = quality["duplicate_twin"]
    assert twin is not None
    assert twin.endswith("dup_b.py")


def test_complexity_is_reflected_in_rank_and_flag(tmp_path: Path) -> None:
    repo = _seeded_repo(tmp_path)

    results = SearchService(repo).search_content("deeply_nested")

    hit = _result_for(results, "nested.py")
    assert "complex" in _quality(hit)["flags"]
    assert "complex" in hit["reasons"]
    # The complexity boost surfaces the risky symbol above the bare text floor.
    assert hit["score"] > 100.0


def test_annotation_stays_within_output_bound(tmp_path: Path) -> None:
    repo = _seeded_repo(tmp_path)

    results = SearchService(repo).search_content("doubled")

    quality = _quality(_result_for(results, "dup_a.py"))
    # Bounded: a few flags plus an optional twin path, never a findings dump.
    assert set(quality.keys()) == {"flags", "duplicate_twin"}
    assert len(quality["flags"]) <= 4
    assert all(isinstance(flag, str) for flag in quality["flags"])


def test_quality_rank_adjustment_is_explainable(tmp_path: Path) -> None:
    repo = _seeded_repo(tmp_path)
    service = SearchService(repo)

    dead = _result_for(service.search_content("authenticate"), "dead.py")
    hot = _result_for(service.search_content("hotspot_metric"), "hot.py")

    # Each quality adjustment leaves a named, human-readable reason behind.
    assert "dead_code" in dead["reasons"]
    assert "hotspot" in hot["reasons"]


def _finding_facts(repo: Path) -> list[tuple[str, str, str]]:
    """The deterministic identity of every finding scan_code_health produces.

    Excludes the per-run ``scan_id`` uuid (never deterministic by design) and
    lifecycle counts; the rule/file/stable-key triple IS the fact surface.
    """
    findings = CodeHealthService(repo).scan().findings
    return sorted(
        (finding.rule_id, finding.file_path, finding.stable_key) for finding in findings
    )


def test_scan_code_health_output_is_byte_identical(tmp_path: Path) -> None:
    # Warm the scan first so later scans are stable (no first-scan changed-source
    # churn); this isolates the quality path as the only variable between them.
    repo = _seeded_repo(tmp_path)

    before = _finding_facts(repo)
    # Exercise the full quality read + annotation + frecency-write path.
    _ = SearchService(repo).search_content("authenticate")
    _ = SearchService(repo).search_files("hot")
    after = _finding_facts(repo)

    # Facts stay deterministic: reading quality never mutates findings (KTD-8).
    assert before == after


def test_repo_without_findings_yields_neutral_results(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    src = repo / "src"
    src.mkdir(parents=True)
    _ = (src / "mod.py").write_text(_CLEAN_SOURCE)

    results = SearchService(repo).search_content("authenticate")

    assert results
    assert all(result.get("quality") is None for result in results)
    assert quality_signals_for(repo) == {}
