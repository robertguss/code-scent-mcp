from __future__ import annotations

from typing import TYPE_CHECKING

from codescent.core.models import MaintainabilityThresholds, ProjectConfig
from codescent.engine.packs import build_pack_registry
from codescent.engine.rules.model import FindingSpec, build_finding
from codescent.services.code_health import (
    CodeHealthService,
    run_rule_packs,
    scan_rule_packs_cached,
)
from codescent.services.config import ConfigService
from codescent.services.repo_index import RepoIndexService
from codescent.services.scan_cache import (
    ScanCache,
    changed_paths,
    pack_input_hashes,
)
from codescent.storage import initialize_storage

if TYPE_CHECKING:
    from pathlib import Path


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    a = repo / "src" / "pkg" / "a.py"
    a.parent.mkdir(parents=True)
    _ = a.write_text(
        """STATUS = "pending-review"
OTHER = "pending-review"
THIRD = "pending-review"


def load_config() -> dict[str, str]:
    # TODO: split config
    # FIXME: preserve compatibility
    # HACK: keep old queue name
    return {"status": STATUS}
""",
    )
    b = repo / "src" / "pkg" / "b.py"
    _ = b.write_text(
        """LABEL = "draft-state"
ALT = "draft-state"
MORE = "draft-state"


def render() -> str:
    # TODO: paginate
    # FIXME: escape html
    # HACK: inline styles
    return LABEL
""",
    )
    ConfigService(repo).save(
        ProjectConfig(thresholds=MaintainabilityThresholds.strict()),
    )
    return repo


def test_changed_paths_detects_single_change() -> None:
    assert changed_paths({"a": "1", "b": "2"}, {"a": "1", "b": "3"}) == ("b",)
    assert changed_paths({"a": "1"}, {"a": "1", "c": "9"}) == ("c",)
    assert changed_paths({"a": "1", "b": "2"}, {"a": "1", "b": "2"}) == ()


def test_cache_roundtrip_preserves_tier_and_provenance(tmp_path: Path) -> None:
    finding = build_finding(
        FindingSpec(
            rule_id="python.dead_code_candidate",
            title="Dead code",
            message="foo is never called.",
            file_path="src/pkg/a.py",
            symbol="pkg.a.foo",
            severity="warning",
            confidence=0.8,
            evidence={"symbol": "foo", "line": 3},
            suggested_action="Remove foo.",
        ),
    )
    assert finding.confidence_tier == "verified"

    cache = ScanCache(tmp_path)
    cache.store(
        fingerprint="fp",
        file_hashes={"src/pkg/a.py": "h"},
        findings=(finding,),
    )
    loaded = cache.load()

    assert loaded is not None
    assert loaded.fingerprint == "fp"
    # Full dataclass equality covers every field, including evidence types.
    assert loaded.findings == (finding,)
    assert loaded.findings[0].confidence_tier == finding.confidence_tier
    assert loaded.findings[0].provenance == finding.provenance


def test_warm_hit_then_single_file_reprocess(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    index_result = RepoIndexService(repo).index_repo()
    state = initialize_storage(repo)
    registry = build_pack_registry(ConfigService(repo).load())

    cold = scan_rule_packs_cached(
        state, registry, index_result, workers=1, use_cache=True
    )
    assert cold.cache_hit is False
    assert cold.findings
    assert set(cold.reprocessed_files) == set(index_result.file_hashes)

    warm = scan_rule_packs_cached(
        state, registry, index_result, workers=1, use_cache=True
    )
    assert warm.cache_hit is True
    assert warm.reprocessed_files == ()
    assert warm.findings == cold.findings

    target = repo / "src" / "pkg" / "a.py"
    _ = target.write_text(target.read_text() + "\nEXTRA = 'pending-review'\n")
    index2 = RepoIndexService(repo).index_repo()

    changed = scan_rule_packs_cached(state, registry, index2, workers=1, use_cache=True)
    assert changed.cache_hit is False
    assert set(changed.reprocessed_files) == {"src/pkg/a.py"}

    fresh = scan_rule_packs_cached(state, registry, index2, workers=1, use_cache=False)
    assert changed.findings == fresh.findings


def test_parallel_equals_serial(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    _ = RepoIndexService(repo).index_repo()
    state = initialize_storage(repo)
    registry = build_pack_registry(ConfigService(repo).load())

    serial = run_rule_packs(registry, state.repo_root, workers=1)
    parallel = run_rule_packs(registry, state.repo_root, workers=4)

    assert serial
    assert parallel == serial


def test_scan_warm_equals_cold_including_suppression(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    svc = CodeHealthService(repo)

    # Prime the index + cache. After this, the incremental index reports no
    # changed files, so the delta-based changed-source rule is stable and the
    # only variable left between the next two scans is cache hit vs recompute.
    _ = svc.scan()
    warm = svc.scan()  # cache hit: rule findings reused

    ScanCache(repo / ".codescent").path.unlink()
    cold = svc.scan()  # cache miss: rule findings recomputed

    assert warm.findings == cold.findings
    assert warm.suppressed_stable_keys == cold.suppressed_stable_keys
    assert warm.rule_ids == cold.rule_ids
    assert warm.finding_ids == cold.finding_ids


def test_pack_input_hashes_track_go_and_generic_content(tmp_path: Path) -> None:
    # Regression: the language inventory hashes only .py/.ts/.js, so the cache
    # fingerprint must hash Go and generic-fallback files itself or a stale scan
    # is served when one of them changes while git status does not flip.
    repo = tmp_path / "repo"
    repo.mkdir()
    go_file = repo / "main.go"
    _ = go_file.write_text("package main\n\nfunc A() {}\n")
    data_file = repo / "data.rb"
    _ = data_file.write_text("VALUE = 1\n")
    config = ProjectConfig()

    before = pack_input_hashes(repo, config)
    assert "main.go" in before
    assert "data.rb" in before

    _ = go_file.write_text("package main\n\nfunc B() {}\n")
    assert pack_input_hashes(repo, config) != before

    after_go = pack_input_hashes(repo, config)
    _ = data_file.write_text("VALUE = 2\n")
    assert pack_input_hashes(repo, config) != after_go


def test_pack_input_hashes_respect_disabled_packs(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / "main.go").write_text("package main\n")
    _ = (repo / "data.rb").write_text("VALUE = 1\n")
    config = ProjectConfig(language_packs=("python",), generic_fallback=False)

    assert pack_input_hashes(repo, config) == {}
