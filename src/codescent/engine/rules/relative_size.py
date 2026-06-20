"""Relative ("large for this repository") maintainability findings.

These complement the absolute size thresholds: a file/function/class can be well
under the absolute floor yet be a clear outlier for *this* repository. We flag
those using a robust IQR outlier rule (cutoff = Q3 + k*IQR) computed over the
repo's own size distribution, so the rule fires only on genuine outliers rather
than a fixed fraction of the codebase. Output is a pure, deterministic function
of the repo's metric distribution.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import TYPE_CHECKING

from codescent.engine.rules.model import CodeHealthFinding, FindingSpec, build_finding

if TYPE_CHECKING:
    from collections.abc import Sequence

    from codescent.core.models import MaintainabilityThresholds


@dataclass(frozen=True, slots=True)
class SizeSample:
    file_path: str
    symbol: str | None
    value: int


def relative_outlier_findings(
    *,
    file_samples: Sequence[SizeSample],
    function_samples: Sequence[SizeSample],
    class_samples: Sequence[SizeSample],
    thresholds: MaintainabilityThresholds,
) -> tuple[CodeHealthFinding, ...]:
    if not thresholds.relative_thresholds_enabled:
        return ()
    return (
        *_outliers(
            file_samples,
            rule_id="python.relative_large_file",
            title="Large file for this repository",
            descriptor="module",
            absolute=thresholds.large_file_lines,
            thresholds=thresholds,
        ),
        *_outliers(
            function_samples,
            rule_id="python.relative_large_function",
            title="Large function for this repository",
            descriptor="function",
            absolute=thresholds.large_function_lines,
            thresholds=thresholds,
        ),
        *_outliers(
            class_samples,
            rule_id="python.relative_large_class",
            title="Large class for this repository",
            descriptor="class",
            absolute=thresholds.large_class_lines,
            thresholds=thresholds,
        ),
    )


def _outliers(  # noqa: PLR0913
    samples: Sequence[SizeSample],
    *,
    rule_id: str,
    title: str,
    descriptor: str,
    absolute: int,
    thresholds: MaintainabilityThresholds,
) -> tuple[CodeHealthFinding, ...]:
    if len(samples) < thresholds.relative_min_sample_size:
        return ()
    values = [sample.value for sample in samples]
    quartile_one, _quartile_two, quartile_three = statistics.quantiles(values, n=4)
    iqr = quartile_three - quartile_one
    if iqr <= 0:
        # No meaningful spread (e.g. many identically sized files): nothing is a
        # relative outlier.
        return ()
    median = statistics.median(values)
    cutoff = quartile_three + thresholds.relative_outlier_iqr_multiplier * iqr
    # Only the gap the absolute rule misses: an outlier for this repo that is
    # still under the absolute floor (the absolute rule already owns the rest).
    return tuple(
        _finding(
            sample,
            rule_id=rule_id,
            title=title,
            descriptor=descriptor,
            absolute=absolute,
            median=median,
            quartile_three=quartile_three,
            cutoff=cutoff,
            sample_size=len(samples),
        )
        for sample in samples
        if cutoff <= sample.value < absolute
    )


def _finding(  # noqa: PLR0913
    sample: SizeSample,
    *,
    rule_id: str,
    title: str,
    descriptor: str,
    absolute: int,
    median: float,
    quartile_three: float,
    cutoff: float,
    sample_size: int,
) -> CodeHealthFinding:
    target = sample.symbol or sample.file_path
    return build_finding(
        FindingSpec(
            rule_id=rule_id,
            title=title,
            message=(
                f"{target} spans {sample.value} lines — unusually large for this "
                f"repository (median {median:g}, outlier cutoff {cutoff:g})."
            ),
            file_path=sample.file_path,
            symbol=sample.symbol,
            severity="info",
            confidence=0.6,
            evidence={
                "line_count": sample.value,
                "repo_median": _round(median),
                "repo_q3": _round(quartile_three),
                "outlier_cutoff": _round(cutoff),
                "sample_size": sample_size,
                "absolute_threshold": absolute,
            },
            suggested_action=(
                f"Review whether this {descriptor} should be split; it is an "
                "outlier for this repository even though it is under the absolute "
                "threshold."
            ),
        ),
    )


def _round(value: float) -> float:
    return round(float(value), 1)
