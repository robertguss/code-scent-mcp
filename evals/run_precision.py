"""CLI for the per-rule eval-precision harness + CI gate (plan unit U10).

Examples:
    # Verbose per-rule eval-precision report over the seeded corpus
    uv run python evals/run_precision.py --verbose

    # CI gate: fail (exit 1) if any rule regressed below its recorded baseline
    uv run python evals/run_precision.py --check

    # Re-record baselines after an intended, reviewed precision change
    uv run python evals/run_precision.py --update-baseline
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Annotated

import typer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evals.precision_harness import (
    DEFAULT_BASELINES_PATH,
    DEFAULT_CORPUS_ROOT,
    DEFAULT_LABELS_PATH,
    baselines_from_report,
    check_regression,
    compute_precision,
    load_baselines,
    log_report,
)

BASELINE_COMMENT = (
    "Per-rule eval precision (TP/(TP+FP)) floors for the U10 CI gate. "
    "Regenerate with: uv run python evals/run_precision.py --update-baseline"
)


def main(  # noqa: PLR0913 - typer CLI: each flag/path is its own option
    *,
    corpus: Annotated[Path, typer.Option()] = DEFAULT_CORPUS_ROOT,
    labels: Annotated[Path, typer.Option()] = DEFAULT_LABELS_PATH,
    baselines: Annotated[Path, typer.Option()] = DEFAULT_BASELINES_PATH,
    check: Annotated[
        bool, typer.Option(help="Fail when a rule regresses below baseline.")
    ] = False,
    update_baseline: Annotated[
        bool,
        typer.Option(help="Rewrite the baselines file from the current scan."),
    ] = False,
    verbose: Annotated[
        bool, typer.Option(help="Log the full per-rule report.")
    ] = False,
) -> None:
    logging.basicConfig(
        level=logging.INFO if (verbose or check) else logging.WARNING,
        format="%(message)s",
    )
    report = compute_precision(corpus_root=corpus, labels_path=labels)
    log_report(report)

    if update_baseline:
        recorded = baselines_from_report(report, comment=BASELINE_COMMENT)
        _ = baselines.write_text(recorded.model_dump_json(indent=2) + "\n")
        typer.echo(
            json.dumps(
                {
                    "updated_baselines": baselines.as_posix(),
                    "rules": len(recorded.baselines),
                }
            )
        )
        return

    if check:
        recorded = load_baselines(baselines)
        regressions = check_regression(report, recorded)
        typer.echo(
            json.dumps(
                {
                    "passed": not regressions,
                    "rules": len(report.rules),
                    "regressions": [
                        {
                            "rule_id": r.rule_id,
                            "baseline": r.baseline,
                            "measured": r.measured,
                        }
                        for r in regressions
                    ],
                },
            ),
        )
        if regressions:
            raise typer.Exit(code=1)
        return

    typer.echo(json.dumps(report.precision_map(), indent=2))


if __name__ == "__main__":
    typer.run(main)
