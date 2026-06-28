"""Entry-point-aware dead-code fixture.

Every public/registered/exported symbol here is reachable from outside the
internal call graph even though nothing inside the package calls it. Only
``_genuinely_dead`` is truly unreferenced, so a correct scan flags exactly one
dead-code candidate. This is the checked-in proof for U8 (the "cbm in-degree=0"
trap that flagged a registered tool as dead).
"""

from __future__ import annotations

import typer

__all__ = ["exported_handler"]

app = typer.Typer()


def exported_handler() -> str:
    """Reachable via ``__all__`` export; never called internally."""
    return _shared("export")


@app.command()
def decorated_command() -> str:
    """Reachable via the ``@app.command()`` decorator; never called internally."""
    return _shared("command")


def public_entry() -> str:
    """Reachable via the call-form registration at the bottom of the module."""
    return _shared("entry")


def _shared(label: str) -> str:
    """Private helper kept alive by internal callers above."""
    return f"acme:{label}"


def _genuinely_dead() -> str:
    """Private, unreferenced, unregistered — the ONLY dead symbol in this repo."""
    return "this function is never reached"


_ = app.command(name="public-entry")(public_entry)
