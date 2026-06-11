#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "typer>=0.12",
#     "pydantic>=2.0",
# ]
# ///

# ─── How to run ───
# 1. Install uv (if not installed):
#      curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run directly (no venv, no pip install needed):
#      uv run scripts/inspect_symbols.py tests/fixtures/python-basic --json
# 3. Or make executable and run:
#      chmod +x scripts/inspect_symbols.py && ./scripts/inspect_symbols.py <repo>
# ──────────────────

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import typer

from codescent.services.symbols import SymbolService


def main(
    repo: Annotated[str, typer.Argument()],
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    result = SymbolService(repo).extract()
    payload = {
        "files": [parsed.to_payload() for parsed in result.files],
    }
    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    typer.echo(f"Parsed {len(result.files)} Python files")


if __name__ == "__main__":
    typer.run(main)
