from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated

import typer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from codescent.evals import run_deterministic_eval


def main(
    repo: Annotated[Path, typer.Option()],
    expected: Annotated[Path, typer.Option()],
    out: Annotated[Path, typer.Option()],
) -> None:
    result = run_deterministic_eval(repo=repo, expected=expected, out=out)
    typer.echo(json.dumps({"passed": result.passed, "score": result.score}))
    if not result.passed:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    typer.run(main)
