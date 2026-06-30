"""Single source of truth for fff engine access.

Both the grep-injection hook (``hook_retrieval``) and the optional-backend
client (``fff_backend.FffPackageClient``) drive the same ``fff.FileFinder``.
Keeping construction and the indexed-language constraint here means there is one
place that configures fff — one scan-timeout, one code-only glob — even though
the two consumers read fff at different altitudes (the hook reads the rich
``GrepMatch`` directly; the client flattens to ``ContentHit``).

The ``fff`` import stays lazy (inside :func:`build_finder`) so importing this
module never pays fff's native-load cost; callers pay it only when they search.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from codescent.engine.inventory import LANGUAGE_BY_SUFFIX

if TYPE_CHECKING:
    from pathlib import Path

    import fff

# Restrict scans to the languages CodeScent indexes so fff mirrors content
# search (code only) and never floats a README/config hit above a real
# definition. fff glob constraint syntax: ``*.{ext,ext}``.
CODE_CONSTRAINT = "*.{{{}}}".format(
    ",".join(sorted(suffix.lstrip(".") for suffix in LANGUAGE_BY_SUFFIX)),
)
# Bound the initial scan so a huge repo cannot stall a never-block caller; an
# incomplete scan still greps what it has (best-effort).
SCAN_TIMEOUT_MS = 1200


def build_finder(repo_root: Path | str) -> fff.FileFinder:
    """Construct a scanned ``fff.FileFinder`` rooted at ``repo_root``.

    The finder is ready to grep on return (its initial scan has completed or hit
    the timeout). ``fff`` is imported lazily so module import stays cheap.
    """
    import fff  # noqa: PLC0415 - lazy native import; keep import cost off the hot path

    finder = fff.FileFinder(str(repo_root))
    _ = finder.wait_for_scan_blocking(timeout_ms=SCAN_TIMEOUT_MS)
    return finder
