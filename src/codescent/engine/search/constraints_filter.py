"""Apply a parsed constraint set as a path prefilter (plan unit U9 / bead P2.2).

Splits the AND-of-groups filtering away from the parser in
:mod:`codescent.engine.search.constraints`. ``build_predicate`` yields a
``keep(path) -> bool`` gate the retrieval layer applies to candidate paths
BEFORE ranking/collapse and the result bound; ``filter_paths`` is the eager
convenience used by tests. Size/time bounds ``stat`` the file under ``repo_root``
and drop a path that cannot be stat'd; git bounds consult injected status sets so
callers stay deterministic.
"""

from __future__ import annotations

import fnmatch
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from codescent.engine.search.constraints import GitPaths

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from pathlib import Path

    from codescent.engine.search.constraints import (
        ConstraintSet,
        ExcludePattern,
        SizeConstraint,
        TimeConstraint,
    )


@dataclass(frozen=True, slots=True)
class _FilterEnv:
    repo_root: Path
    git: GitPaths
    now: float


def build_predicate(
    constraints: ConstraintSet,
    repo_root: Path,
    *,
    git: GitPaths | None = None,
    now: float | None = None,
) -> Callable[[str], bool]:
    """Build a ``keep(path) -> bool`` predicate for a repo-relative path.

    Args:
        constraints: The parsed constraint set to enforce.
        repo_root: Repository root used to ``stat`` files for size/time bounds.
        git: Injected git status sets for ``git:`` constraints (tests/service).
        now: Reference epoch seconds for ``mtime`` bounds; defaults to wall clock.

    Returns:
        A predicate that returns ``True`` when ``path`` satisfies every group.
    """
    env = _FilterEnv(
        repo_root=repo_root,
        git=git if git is not None else GitPaths(),
        now=time.time() if now is None else now,
    )

    def keep(path: str) -> bool:
        return _path_allowed(path, constraints, env)

    return keep


def filter_paths(
    paths: Iterable[str],
    constraints: ConstraintSet,
    repo_root: Path,
    *,
    git: GitPaths | None = None,
    now: float | None = None,
) -> tuple[str, ...]:
    """Prefilter ``paths`` to those satisfying every constraint (AND).

    Args:
        paths: Candidate repo-relative paths to scope.
        constraints: The parsed constraint set.
        repo_root: Repository root for size/time ``stat`` lookups.
        git: Injected git status sets for ``git:`` constraints.
        now: Reference epoch seconds for ``mtime`` bounds.

    Returns:
        The kept paths in input order; the full input when ``constraints`` is
        empty (back-compat: an empty constraint string never narrows results).
    """
    if constraints.is_empty:
        return tuple(paths)
    keep = build_predicate(constraints, repo_root, git=git, now=now)
    return tuple(path for path in paths if keep(path))


def _path_allowed(path: str, constraints: ConstraintSet, env: _FilterEnv) -> bool:
    if not _pattern_ok(path, constraints):
        return False
    if not _git_ok(path, constraints, env):
        return False
    return _stat_ok(path, constraints, env)


def _pattern_ok(path: str, constraints: ConstraintSet) -> bool:
    return (
        all(fnmatch.fnmatch(path, glob) for glob in constraints.globs)
        and all(path.startswith(prefix) for prefix in constraints.prefixes)
        and not any(_excluded(path, pattern) for pattern in constraints.excludes)
    )


def _git_ok(path: str, constraints: ConstraintSet, env: _FilterEnv) -> bool:
    if "modified" in constraints.git_kinds and path not in env.git.modified:
        return False
    return not ("untracked" in constraints.git_kinds and path not in env.git.untracked)


def _stat_ok(path: str, constraints: ConstraintSet, env: _FilterEnv) -> bool:
    if not constraints.needs_stat:
        return True
    try:
        stats = (env.repo_root / path).stat()
    except OSError:
        return False
    return all(_size_ok(stats.st_size, size) for size in constraints.sizes) and all(
        _time_ok(stats.st_mtime, span, env.now) for span in constraints.times
    )


def _excluded(path: str, pattern: ExcludePattern) -> bool:
    if pattern.is_glob:
        return fnmatch.fnmatch(path, pattern.pattern)
    return path.startswith(pattern.pattern)


def _size_ok(size: int, constraint: SizeConstraint) -> bool:
    if constraint.op == "<":
        return size < constraint.threshold_bytes
    if constraint.op == "<=":
        return size <= constraint.threshold_bytes
    if constraint.op == ">":
        return size > constraint.threshold_bytes
    return size >= constraint.threshold_bytes


def _time_ok(mtime: float, constraint: TimeConstraint, now: float) -> bool:
    age = now - mtime
    if constraint.op == "<":
        return age < constraint.seconds
    return age > constraint.seconds
