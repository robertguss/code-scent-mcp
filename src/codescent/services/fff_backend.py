"""Optional fff-backed retrieval engine (detection seam only).

fff (fff-search) is a fast LOCAL fuzzy-path / grep / frecency engine. When an
fff wheel or `fff` binary is reachable on this machine, the navigator routes
retrieval through it for sub-10ms, typo-resistant results; otherwise CodeScent
falls back to its native rapidfuzz path and behaves exactly as it does today.

This module is the detection STUB: it only builds the detect + capability-probe +
selection seam. The actual retrieval routing lands later and consumes the
``FffClient`` capabilities declared here. There is ZERO behaviour change when
fff is absent (the common case): detection returns ``None`` and the caller uses
the native floor.

Local only — this module never opens a network connection, and the optional
``fff-search`` package is never imported at module load time (pure-Python
install stays fully functional without it).
"""

from __future__ import annotations

import importlib.util
import logging
import os
import shutil
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, cast, runtime_checkable

from pydantic import TypeAdapter, ValidationError

from codescent.core.paths import resolve_repo_root

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence
    from pathlib import Path

LOGGER = logging.getLogger("codescent.fff_backend")
FFF_COMMAND_ENV = "CODESCENT_FFF_CMD"
FFF_CANDIDATES = ("fff", "fff-search")
FFF_PACKAGE_CANDIDATES = ("fff_search", "fff")
# Capability names a detected fff client may expose; see ``probe_capabilities``.
FFF_CAPABILITIES = ("fuzzy_paths", "grep_content", "multi_grep", "frecency")


class FffClientError(RuntimeError):
    """A local fff engine was unreachable or returned unusable data."""


@dataclass(frozen=True, slots=True)
class ContentHit:
    """A single content match: where it is and the matched line of text."""

    path: str
    line: int
    text: str


@runtime_checkable
class FffClient(Protocol):
    """Minimal contract the navigator needs from an optional local fff engine.

    The router consumes these capabilities and re-applies CodeScent bounding /
    confidence / freshness on the way out, so a present-but-partial fff engine
    (missing one capability) degrades per-capability rather than crashing -- see
    ``probe_capabilities``.
    """

    def healthy(self) -> bool: ...
    def fuzzy_paths(self, query: str) -> tuple[str, ...]: ...
    def grep_content(self, pattern: str) -> tuple[ContentHit, ...]: ...
    def multi_grep(self, patterns: Sequence[str]) -> tuple[ContentHit, ...]: ...
    def frecency(self) -> Mapping[str, float]: ...


_PATHS_ADAPTER = TypeAdapter(list[str])
_HITS_ADAPTER = TypeAdapter(list[ContentHit])
_FRECENCY_ADAPTER = TypeAdapter(dict[str, float])


def _validate[T](adapter: TypeAdapter[list[T]], payload: object) -> tuple[T, ...]:
    try:
        return tuple(adapter.validate_python(payload))
    except ValidationError as exc:
        message = "fff payload failed validation"
        raise FffClientError(message) from exc


@dataclass(frozen=True, slots=True)
class FffCliClient:
    """Talk to a local fff engine over an injectable JSON contract (no network).

    A ``runner`` may be injected for testing so no real fff
    transport is spawned. ``command`` is the resolved binary path when detected
    via PATH / env override, or ``None`` when only the ``fff-search`` wheel was
    found. The concrete request/response shapes are finalised later; this stub
    is constructible and forwards through the ``runner``.
    """

    command: str | None
    repo_root: Path
    runner: Callable[..., object] | None = None

    def healthy(self) -> bool:
        if self.runner is None:
            # Detection already succeeded; the live reachability probe lands
            # later alongside the real transport. Assume usable until then.
            return True
        try:
            payload = self._invoke("health")
        except FffClientError:
            return False
        if isinstance(payload, dict):
            health = cast("dict[str, object]", payload)
            return bool(health.get("ok", True))
        return bool(payload)

    def fuzzy_paths(self, query: str) -> tuple[str, ...]:
        return _validate(_PATHS_ADAPTER, self._invoke("fuzzy_paths", query))

    def grep_content(self, pattern: str) -> tuple[ContentHit, ...]:
        return _validate(_HITS_ADAPTER, self._invoke("grep", pattern))

    def multi_grep(self, patterns: Sequence[str]) -> tuple[ContentHit, ...]:
        return _validate(_HITS_ADAPTER, self._invoke("multi_grep", tuple(patterns)))

    def frecency(self) -> Mapping[str, float]:
        try:
            return _FRECENCY_ADAPTER.validate_python(self._invoke("frecency"))
        except ValidationError as exc:
            message = "fff frecency payload failed validation"
            raise FffClientError(message) from exc

    def _invoke(self, subcommand: str, /, *args: object) -> object:
        # ponytail: real fff argv/transport contract lands later; the stub only
        # forwards through an injected runner so the detection seam is testable.
        if self.runner is None:
            message = f"fff retrieval is not wired until U8: {subcommand}"
            raise FffClientError(message)
        return self.runner(subcommand, *args)


def probe_capabilities(client: object) -> frozenset[str]:
    """Return the ``FffClient`` capabilities a detected client actually exposes.

    Never raises: a partial or stubbed fff engine missing a capability simply
    omits it from the returned set, so the caller can degrade to the native
    path per capability gap instead of crashing.

    Args:
        client: A detected fff client (or any object) to inspect.

    Returns:
        The subset of ``FFF_CAPABILITIES`` the client exposes as callables.
    """
    return frozenset(
        name for name in FFF_CAPABILITIES if callable(getattr(client, name, None))
    )


def _fff_package_available() -> bool:
    """Detect the optional ``fff-search`` wheel without importing it eagerly."""
    for name in FFF_PACKAGE_CANDIDATES:
        try:
            spec = importlib.util.find_spec(name)
        except (ImportError, ValueError):
            continue
        if spec is not None:
            return True
    return False


def detect_fff(
    repo_root: Path | str,
    *,
    runner: Callable[..., object] | None = None,
) -> FffClient | None:
    """Detect a LOCAL fff engine; return None cleanly when fff is absent.

    Resolution order: ``CODESCENT_FFF_CMD`` env override, then an ``fff`` binary
    on PATH, then the optional ``fff-search`` Python wheel. When none are found,
    returns ``None`` so the caller uses the native rapidfuzz floor.

    Args:
        repo_root: Repository root the engine should search.
        runner: Optional transport seam injected for tests; when ``None`` the
            stub client raises until the real transport is supplied.

    Returns:
        An ``FffClient`` when an fff engine is detected, else ``None``.
    """
    command = os.environ.get(FFF_COMMAND_ENV)
    if command is None:
        for candidate in FFF_CANDIDATES:
            found = shutil.which(candidate)
            if found is not None:
                command = found
                break
    package = _fff_package_available() if command is None else False
    if command is None and not package:
        LOGGER.debug("fff not detected; using native rapidfuzz search")
        return None
    LOGGER.info("fff engine detected (command=%s, package=%s)", command, package)
    return FffCliClient(
        command=command,
        repo_root=resolve_repo_root(repo_root),
        runner=runner,
    )


def select_search_backend(
    repo_root: Path | str,
    *,
    client: FffClient | None = None,
    runner: Callable[..., object] | None = None,
) -> FffClient | None:
    """Pick the retrieval engine: fff when present and healthy, else native.

    The return contract differs from ``select_graph_backend`` on purpose: there
    is no fff "backend object" wrapping a native fallback in this unit. A return
    value of ``None`` means **use the native rapidfuzz retrieval path** (the
    always-on floor). A ``None`` result means native; a non-``None`` result is
    the fff engine to route through.

    Args:
        repo_root: Repository root the engine should search.
        client: A pre-built client to use instead of detection (tests).
        runner: Optional transport seam forwarded to ``detect_fff``.

    Returns:
        The detected ``FffClient`` when fff is present and healthy, else
        ``None`` to signal the native rapidfuzz fallback.
    """
    resolved = client if client is not None else detect_fff(repo_root, runner=runner)
    if resolved is None:
        return None
    if not _healthy(resolved):
        LOGGER.info("fff detected but unhealthy; using native search backend")
        return None
    LOGGER.info("using fff search backend")
    return resolved


def _healthy(client: FffClient) -> bool:
    probe = getattr(client, "healthy", None)
    if not callable(probe):
        return True
    try:
        return bool(probe())
    except FffClientError:
        return False
