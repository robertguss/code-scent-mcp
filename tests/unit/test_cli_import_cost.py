"""U5: importing the CLI must not eagerly pull the heavy service graph.

``hook-augment`` runs through ``codescent.cli.main``; eager imports of the
reporting/admin service modules (``ci`` pulls the heaviest sub-graph, plus
``reports``/``precision``/``findings``) add startup latency in front of every
intercepted search. These services are lazy-imported inside their command
bodies, so a bare ``import codescent.cli.main`` must leave them out of
``sys.modules``. Checked in a fresh interpreter because the test process has
already imported them.
"""

from __future__ import annotations

import json
import subprocess
import sys

_FORBIDDEN = (
    "codescent.services.ci",
    "codescent.services.reports",
    "codescent.services.precision",
    "codescent.services.findings",
)


def test_cli_main_import_does_not_pull_heavy_services() -> None:
    code = (
        "import sys, json, codescent.cli.main; "
        f"print(json.dumps([m for m in {_FORBIDDEN!r} if m in sys.modules]))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
    )
    leaked = json.loads(completed.stdout.strip().splitlines()[-1])
    assert leaked == [], f"heavy modules eagerly imported by the CLI: {leaked}"
