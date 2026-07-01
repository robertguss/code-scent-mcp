"""Per-rule **eval precision** harness + CI gate (plan unit U10).

This computes *eval precision* — ``TP / (TP + FP)`` for each rule against a
labeled corpus of known-smelly and known-clean fixtures under
``evals/precision_corpus/``. It is deliberately distinct from U13's runtime
*acceptance precision* (accept-vs-dismiss verdicts): this number measures, on a
fixed labeled corpus, how often a rule that fires is firing on something it is
supposed to flag.

Definitions (per rule ``R``):

* **TP** — ``R`` produced a finding on an item labeled *smelly* for ``R``.
* **FP** — ``R`` produced a finding on an item labeled *clean* for ``R``.
* **eval precision** — ``TP / (TP + FP)`` (``1.0`` when ``R`` made no positive
  prediction on either set, i.e. nothing to be imprecise about).

The scan reuses the production engine (``CodeHealthService``) and the same
strict thresholds the deterministic eval pins, so the harness exercises the real
rules rather than a parallel re-implementation. It is deterministic, bounded
(tiny corpus) and performs no network or git access beyond the local scan.
"""

from __future__ import annotations

import logging
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

# Allow `python evals/precision_harness.py` style direct execution to find the
# package without an editable install (mirrors evals/run_deterministic.py).
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codescent.core.models import MaintainabilityThresholds, ProjectConfig
from codescent.evals.deterministic import EVAL_EXCLUDED_RULE_IDS
from codescent.services.code_health import CodeHealthService
from codescent.services.config import ConfigService

logger = logging.getLogger("codescent.evals.precision")

_HARNESS_DIR = Path(__file__).resolve().parent
DEFAULT_CORPUS_ROOT = _HARNESS_DIR / "precision_corpus"
DEFAULT_LABELS_PATH = DEFAULT_CORPUS_ROOT / "labels.json"
DEFAULT_BASELINES_PATH = _HARNESS_DIR / "precision_baselines.json"

# Deterministic float comparison slack for the regression gate. Precision is a
# ratio of small integers here, so anything beyond rounding noise is a real
# regression.
REGRESSION_TOLERANCE = 1e-9


class RuleLabels(BaseModel):
    """Smelly/clean fixture paths (relative to the corpus root) for one rule."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    smelly: tuple[str, ...] = ()
    clean: tuple[str, ...] = ()


class CorpusLabels(BaseModel):
    """The labeled corpus: a smelly/clean fixture set per ``rule_id``."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    description: str = ""
    corpus_root: str
    rules: dict[str, RuleLabels]


class PrecisionBaselines(BaseModel):
    """Checked-in per-rule eval-precision floors enforced by the CI gate."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    comment: str = ""
    baselines: dict[str, float]


@dataclass(frozen=True, slots=True)
class RulePrecision:
    rule_id: str
    true_positives: int
    false_positives: int
    eval_precision: float
    smelly_total: int
    clean_total: int
    missed_smelly: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PrecisionReport:
    rules: tuple[RulePrecision, ...]
    unlabeled_rule_ids: tuple[str, ...]

    def precision_map(self) -> dict[str, float]:
        return {rule.rule_id: rule.eval_precision for rule in self.rules}


@dataclass(frozen=True, slots=True)
class Regression:
    rule_id: str
    baseline: float
    measured: float


def load_labels(path: Path = DEFAULT_LABELS_PATH) -> CorpusLabels:
    return CorpusLabels.model_validate_json(path.read_text())


def load_baselines(path: Path = DEFAULT_BASELINES_PATH) -> dict[str, float]:
    return dict(PrecisionBaselines.model_validate_json(path.read_text()).baselines)


def precision_from_labels(
    labels: CorpusLabels,
    actual_pairs: set[tuple[str, str]],
) -> PrecisionReport:
    """Compute the per-rule report from labels and a set of ``(rule, file)``.

    Pure function (no scanning) so the precision arithmetic and the regression
    gate are independently testable.
    """
    rules: list[RulePrecision] = []
    for rule_id in sorted(labels.rules):
        spec = labels.rules[rule_id]
        flagged = {file for rule, file in actual_pairs if rule == rule_id}
        smelly = set(spec.smelly)
        clean = set(spec.clean)
        tp_files = smelly & flagged
        fp_files = clean & flagged
        true_positives = len(tp_files)
        false_positives = len(fp_files)
        denominator = true_positives + false_positives
        precision = true_positives / denominator if denominator else 1.0
        rules.append(
            RulePrecision(
                rule_id=rule_id,
                true_positives=true_positives,
                false_positives=false_positives,
                eval_precision=precision,
                smelly_total=len(smelly),
                clean_total=len(clean),
                missed_smelly=tuple(sorted(smelly - flagged)),
            ),
        )
    labeled = set(labels.rules)
    unlabeled = tuple(
        sorted({rule for rule, _ in actual_pairs if rule not in labeled}),
    )
    return PrecisionReport(rules=tuple(rules), unlabeled_rule_ids=unlabeled)


def scan_corpus_pairs(corpus_root: Path) -> set[tuple[str, str]]:
    """Scan the corpus with strict thresholds; return ``(rule_id, file)`` pairs.

    ``.codescent`` runtime state is removed before and after so the scan is a
    deterministic cold run and the corpus stays source-only on disk.

    The default scan-time suppression is turned OFF here so this harness keeps
    measuring rule precision against the intentional-smell corpus (R4 override).
    """
    shutil.rmtree(corpus_root / ".codescent", ignore_errors=True)
    ConfigService(corpus_root).save(
        ProjectConfig(thresholds=MaintainabilityThresholds.strict()),
    )
    try:
        scan = CodeHealthService(corpus_root).scan(apply_default_suppression=False)
        return {
            (finding.rule_id, finding.file_path)
            for finding in scan.findings
            if finding.rule_id not in EVAL_EXCLUDED_RULE_IDS
        }
    finally:
        shutil.rmtree(corpus_root / ".codescent", ignore_errors=True)


def compute_precision(
    *,
    corpus_root: Path = DEFAULT_CORPUS_ROOT,
    labels_path: Path = DEFAULT_LABELS_PATH,
) -> PrecisionReport:
    labels = load_labels(labels_path)
    pairs = scan_corpus_pairs(corpus_root)
    return precision_from_labels(labels, pairs)


def check_regression(
    report: PrecisionReport,
    baselines: dict[str, float],
    *,
    tolerance: float = REGRESSION_TOLERANCE,
) -> tuple[Regression, ...]:
    """Return rules whose measured eval precision fell below their baseline.

    A baselined rule that is absent from the report (its corpus item vanished)
    is treated as a full regression so the gate cannot be silently bypassed by
    deleting a fixture.
    """
    measured = report.precision_map()
    regressions: list[Regression] = []
    for rule_id, baseline in sorted(baselines.items()):
        got = measured.get(rule_id)
        if got is None:
            regressions.append(
                Regression(rule_id=rule_id, baseline=baseline, measured=0.0)
            )
            continue
        if got < baseline - tolerance:
            regressions.append(
                Regression(rule_id=rule_id, baseline=baseline, measured=got)
            )
    return tuple(regressions)


def baselines_from_report(
    report: PrecisionReport, *, comment: str
) -> PrecisionBaselines:
    return PrecisionBaselines(
        comment=comment,
        baselines={rule.rule_id: rule.eval_precision for rule in report.rules},
    )


def log_report(report: PrecisionReport) -> None:
    """Emit a verbose, per-rule eval-precision report at INFO level."""
    logger.info(
        "per-rule eval precision (TP / (TP + FP)) over %d rules:", len(report.rules)
    )
    for rule in report.rules:
        logger.info(
            "  %-38s precision=%.3f  TP=%d FP=%d  (smelly=%d clean=%d)%s",
            rule.rule_id,
            rule.eval_precision,
            rule.true_positives,
            rule.false_positives,
            rule.smelly_total,
            rule.clean_total,
            f"  MISSED={list(rule.missed_smelly)}" if rule.missed_smelly else "",
        )
    if report.unlabeled_rule_ids:
        logger.info(
            "rules seen in scan but not covered by the corpus (gaps): %s",
            list(report.unlabeled_rule_ids),
        )
