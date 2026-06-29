from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated

import typer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codescent.evals.token_efficiency import build_token_efficiency_report

DEFAULT_REPO = Path("tests/fixtures/python-basic")
DEFAULT_OUT = Path("evals/token_baselines.json")


def main(
    repo: Annotated[Path, typer.Option()] = DEFAULT_REPO,
    out: Annotated[Path, typer.Option()] = DEFAULT_OUT,
) -> None:
    report = build_token_efficiency_report(repo)
    out.parent.mkdir(parents=True, exist_ok=True)
    _ = out.write_text(
        json.dumps(report.model_dump(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    typer.echo(report.summary.model_dump_json())


if __name__ == "__main__":
    typer.run(main)
