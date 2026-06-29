"""Lint: AGENTS.md must carry the NAVIGATOR NORTH STAR section.

Guards the settled navigator identity (roadmap Phase 0.1) against drift. Run in
CI or via the pytest companion in ``tests/integration/test_north_star_lint.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import typer

NORTH_STAR_HEADER = "## NAVIGATOR NORTH STAR"
ANTI_DRIFT_HEADER = "### Anti-drift checklist"


def check_north_star(agents_md: Path) -> bool:
    """Return True when ``agents_md`` carries the north star + anti-drift section."""
    try:
        text = agents_md.read_text(encoding="utf-8")
    except OSError:
        return False
    return NORTH_STAR_HEADER in text and ANTI_DRIFT_HEADER in text


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    root = Path(args[0]) if args else Path(__file__).resolve().parents[1]
    agents_md = root / "AGENTS.md"
    if check_north_star(agents_md):
        typer.echo(f"OK: navigator north star present in {agents_md}")
        return 0
    typer.echo(
        f"MISSING: {NORTH_STAR_HEADER!r} / {ANTI_DRIFT_HEADER!r} not in {agents_md}",
        err=True,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
