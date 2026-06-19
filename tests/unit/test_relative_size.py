from pathlib import Path

from codescent.core.models import MaintainabilityThresholds, ProjectConfig
from codescent.engine.rules.python import scan_python_health

STRICT_CONFIG = ProjectConfig(thresholds=MaintainabilityThresholds.strict())


def _class_block(name: str, span: int) -> str:
    # `class X:` plus (span - 1) body lines == `span` source lines.
    body = "\n".join(f"    attr_{index} = {index}" for index in range(span - 1))
    return f"class {name}:\n{body}\n"


def _repo_with_class_outlier(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    source = repo / "src" / "models.py"
    source.parent.mkdir(parents=True)
    # 16 small classes (3..18 lines) establish the repo distribution; one 40-line
    # class is a clear outlier but stays well under the absolute class threshold.
    blocks = [_class_block(f"Small{span}", span) for span in range(3, 19)]
    blocks.append(_class_block("BigOutlierModel", 40))
    _ = source.write_text("\n\n".join(blocks) + "\n")
    return repo


def test_relative_large_class_flags_repo_outlier_under_default_thresholds(
    tmp_path: Path,
) -> None:
    repo = _repo_with_class_outlier(tmp_path)

    findings = scan_python_health(repo)
    relative = [
        finding
        for finding in findings
        if finding.rule_id == "python.relative_large_class"
    ]

    assert len(relative) == 1
    outlier = relative[0]
    assert outlier.file_path == "src/models.py"
    assert outlier.evidence["line_count"] == 40
    assert outlier.evidence["absolute_threshold"] == 200
    assert outlier.severity == "info"
    # The outlier cutoff is derived from the repo's own distribution.
    assert 18 < float(outlier.evidence["outlier_cutoff"]) < 40


def test_relative_thresholds_disabled_in_strict_profile(tmp_path: Path) -> None:
    repo = _repo_with_class_outlier(tmp_path)

    findings = scan_python_health(repo, config=STRICT_CONFIG)

    assert not any(
        finding.rule_id.startswith("python.relative_") for finding in findings
    )


def test_relative_thresholds_need_a_minimum_sample(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = repo / "src" / "models.py"
    source.parent.mkdir(parents=True)
    # Only three classes — below the default min_sample_size, so no relative
    # findings even though one is comparatively large.
    blocks = [_class_block("A", 3), _class_block("B", 4), _class_block("Big", 40)]
    _ = source.write_text("\n\n".join(blocks) + "\n")

    findings = scan_python_health(repo)

    assert not any(
        finding.rule_id.startswith("python.relative_") for finding in findings
    )


def test_relative_finding_id_is_stable_across_distribution_shift(
    tmp_path: Path,
) -> None:
    repo = _repo_with_class_outlier(tmp_path)
    before = next(
        finding
        for finding in scan_python_health(repo)
        if finding.rule_id == "python.relative_large_class"
    )

    # Adding an unrelated tiny class shifts the distribution stats but must not
    # re-key the existing outlier finding.
    extra = repo / "src" / "extra.py"
    _ = extra.write_text(_class_block("TinyExtra", 3))
    after = next(
        finding
        for finding in scan_python_health(repo)
        if finding.rule_id == "python.relative_large_class"
        and finding.file_path == "src/models.py"
    )

    assert before.stable_key == after.stable_key
