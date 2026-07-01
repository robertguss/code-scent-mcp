import subprocess
from dataclasses import dataclass
from pathlib import Path
from shutil import which
from typing import Final

GIT_STATUS_TIMEOUT_SECONDS: Final = 5
GIT_HISTORY_TIMEOUT_SECONDS: Final = 5
GIT_LOG_MAX_COMMITS: Final = 400
CO_CHANGE_MAX_RESULTS: Final = 10
COMMIT_HASH_LENGTH: Final = 40
COMMIT_HASH_CHARACTERS: Final = frozenset("0123456789abcdef")
PORCELAIN_STATUS_PREFIX_WIDTH: Final = 3
MIN_PORCELAIN_STATUS_LINE_LENGTH: Final = PORCELAIN_STATUS_PREFIX_WIDTH + 1
# Directory prefixes whose contents churn on nearly every commit and bury real
# coupling in co-change / blast-radius signals (R3). Generalizes the historical
# ``.codescent`` skip.
CO_CHANGE_EXCLUDED_PREFIXES: Final = (".codescent", ".beads/")
# Dependency lockfiles rewritten on nearly every dependency bump; noise for
# source-to-source co-change.
CO_CHANGE_EXCLUDED_LOCKFILES: Final = frozenset(
    {
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "poetry.lock",
        "uv.lock",
        "Pipfile.lock",
        "Cargo.lock",
        "go.sum",
    },
)


def _is_excluded_cochange_path(path: str) -> bool:
    """High-churn state/artifact paths that must not dominate co-change signals.

    Excludes the ``.codescent`` runtime dir, ``.beads`` issue state, ``*.jsonl``
    append-only state logs, and common dependency lockfiles — all rewritten on
    nearly every commit, so they co-change with everything and bury the real
    source-to-source coupling the caller is after.
    """
    if path.startswith(CO_CHANGE_EXCLUDED_PREFIXES):
        return True
    if path.endswith(".jsonl"):
        return True
    return path.rsplit("/", maxsplit=1)[-1] in CO_CHANGE_EXCLUDED_LOCKFILES


@dataclass(frozen=True, slots=True)
class GitState:
    available: bool
    status: str


@dataclass(frozen=True, slots=True)
class FileAuthorChurn:
    """Per-file authorship concentration from one ``git log`` pass.

    ``churn`` is the recent commit count touching the file, ``top_author_share``
    is the dominant author's fraction of those commits (1.0 == single author),
    and ``author_count`` is the number of distinct authors.
    """

    churn: int
    top_author_share: float
    author_count: int


def detect_git_state(repo_root: Path) -> GitState:
    if not (repo_root / ".git").exists():
        return GitState(available=False, status="not_git")

    git_path = which("git")
    if git_path is None:
        return GitState(available=False, status="git_missing")

    try:
        result = subprocess.run(
            [
                git_path,
                "-C",
                str(repo_root),
                "status",
                "--porcelain",
                "--",
                ".",
                ":(exclude).codescent",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=GIT_STATUS_TIMEOUT_SECONDS,
        )
    except subprocess.CalledProcessError:
        return GitState(available=False, status="not_git")
    except subprocess.TimeoutExpired:
        return GitState(available=False, status="git_timeout")

    if result.stdout.strip():
        return GitState(available=True, status="dirty")
    return GitState(available=True, status="clean")


def git_changed_paths(repo_root: Path) -> frozenset[str]:
    if not (repo_root / ".git").exists():
        return frozenset()

    git_path = which("git")
    if git_path is None:
        return frozenset()

    try:
        result = subprocess.run(
            [
                git_path,
                "-C",
                str(repo_root),
                "status",
                "--porcelain",
                "--untracked-files=all",
                "--",
                ".",
                ":(exclude).codescent",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=GIT_STATUS_TIMEOUT_SECONDS,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return frozenset()

    return frozenset(_parse_git_status_paths(result.stdout))


def git_untracked_paths(repo_root: Path) -> frozenset[str]:
    """Repo-relative paths git reports as untracked (new, unstaged files).

    Returns an empty set when this is not a git repo, git is missing, or git
    errors, so a ``git:untracked`` constraint self-disables cleanly rather than
    raising. Excludes the ``.codescent`` runtime directory, matching the other
    status helpers.
    """
    if not (repo_root / ".git").exists():
        return frozenset()

    git_path = which("git")
    if git_path is None:
        return frozenset()

    try:
        result = subprocess.run(
            [
                git_path,
                "-C",
                str(repo_root),
                "ls-files",
                "--others",
                "--exclude-standard",
                "--",
                ".",
                ":(exclude).codescent",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=GIT_STATUS_TIMEOUT_SECONDS,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return frozenset()

    return frozenset(
        line.strip() for line in result.stdout.splitlines() if line.strip()
    )


def git_changed_paths_since(repo_root: Path, base_ref: str) -> frozenset[str] | None:
    """Repo-relative paths changed since ``base_ref`` (merge-base..working tree).

    Returns ``None`` when the diff cannot be computed (not a git repo, git
    missing, or an unknown ref) so callers can fall back to whole-repo scoping
    instead of treating "no diff" as "nothing changed".
    """
    if not base_ref or not (repo_root / ".git").exists():
        return None
    git_path = which("git")
    if git_path is None:
        return None
    merge_base = _git_merge_base(git_path, repo_root, base_ref)
    diff_target = merge_base or base_ref
    try:
        result = subprocess.run(
            [
                git_path,
                "-C",
                str(repo_root),
                "diff",
                "--name-only",
                diff_target,
                "--",
                ".",
                ":(exclude).codescent",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=GIT_STATUS_TIMEOUT_SECONDS,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    changed = frozenset(
        line.strip() for line in result.stdout.splitlines() if line.strip()
    )
    return changed | git_changed_paths(repo_root)


def git_file_at_ref(repo_root: Path, ref: str, path: str) -> str | None:
    """Return the text of ``path`` as of git ``ref``, or None if unavailable.

    None means "no before state to compare against" (not a git repo, git
    missing, unknown ref, or the file did not exist at that ref).
    """
    if not (repo_root / ".git").exists():
        return None
    git_path = which("git")
    if git_path is None:
        return None
    try:
        result = subprocess.run(
            [git_path, "-C", str(repo_root), "show", f"{ref}:{path}"],
            check=True,
            capture_output=True,
            text=True,
            timeout=GIT_STATUS_TIMEOUT_SECONDS,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    return result.stdout


def _git_merge_base(git_path: str, repo_root: Path, base_ref: str) -> str | None:
    try:
        result = subprocess.run(
            [git_path, "-C", str(repo_root), "merge-base", base_ref, "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=GIT_STATUS_TIMEOUT_SECONDS,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() or None


def git_related_paths(repo_root: Path, path: str) -> tuple[str, ...]:
    if not (repo_root / ".git").exists():
        return ()

    git_path = which("git")
    if git_path is None:
        return ()

    commit_result = subprocess.run(
        [git_path, "-C", str(repo_root), "log", "--format=%H", "--", path],
        capture_output=True,
        check=False,
        text=True,
        timeout=GIT_HISTORY_TIMEOUT_SECONDS,
    )
    if commit_result.returncode != 0:
        return ()

    related: set[str] = set()
    for commit in commit_result.stdout.splitlines():
        show_result = subprocess.run(
            [
                git_path,
                "-C",
                str(repo_root),
                "show",
                "--pretty=format:",
                "--name-only",
                "--no-renames",
                commit,
            ],
            capture_output=True,
            check=False,
            text=True,
            timeout=GIT_HISTORY_TIMEOUT_SECONDS,
        )
        if show_result.returncode != 0:
            continue
        for changed_path in show_result.stdout.splitlines():
            if not changed_path or changed_path == path:
                continue
            if _is_excluded_cochange_path(changed_path):
                continue
            related.add(changed_path)
    return tuple(sorted(related))


def git_co_change_counts(repo_root: Path, path: str) -> tuple[tuple[str, int], ...]:
    """Return paths that changed in the same commits as ``path``."""
    if not (repo_root / ".git").exists():
        return ()

    git_path = which("git")
    if git_path is None:
        return ()

    try:
        result = subprocess.run(
            [
                git_path,
                "-C",
                str(repo_root),
                "log",
                "--full-diff",
                "--no-renames",
                "--format=%H",
                "--name-only",
                "-n",
                str(GIT_LOG_MAX_COMMITS),
                "--",
                path,
            ],
            capture_output=True,
            check=False,
            text=True,
            timeout=GIT_HISTORY_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return ()
    if result.returncode != 0:
        return ()

    counts: dict[str, int] = {}
    commit_paths: set[str] = set()
    for line in result.stdout.splitlines():
        changed_path = line.strip()
        if not changed_path:
            continue
        if _is_commit_hash(changed_path):
            _add_co_change_counts(counts, commit_paths, path)
            commit_paths.clear()
            continue
        commit_paths.add(changed_path)
    _add_co_change_counts(counts, commit_paths, path)

    return tuple(
        sorted(counts.items(), key=lambda item: (-item[1], item[0]))[
            :CO_CHANGE_MAX_RESULTS
        ],
    )


def git_change_counts(repo_root: Path) -> dict[str, int]:
    """Return recent commit counts per path from one git history pass."""
    if not (repo_root / ".git").exists():
        return {}

    git_path = which("git")
    if git_path is None:
        return {}

    try:
        result = subprocess.run(
            [
                git_path,
                "-C",
                str(repo_root),
                "log",
                "--no-renames",
                "--format=%H",
                "--name-only",
                "-n",
                str(GIT_LOG_MAX_COMMITS),
                "--",
                ".",
                ":(exclude).codescent",
            ],
            capture_output=True,
            check=False,
            text=True,
            timeout=GIT_HISTORY_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return {}
    if result.returncode != 0:
        return {}

    counts: dict[str, int] = {}
    commit_paths: set[str] = set()
    for line in result.stdout.splitlines():
        changed_path = line.strip()
        if not changed_path:
            continue
        if _is_commit_hash(changed_path):
            _add_change_counts(counts, commit_paths)
            commit_paths.clear()
            continue
        commit_paths.add(changed_path)
    _add_change_counts(counts, commit_paths)

    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def git_author_churn(repo_root: Path) -> dict[str, FileAuthorChurn]:
    """Return per-file churn + author concentration from one ``git log`` pass.

    Extends the single-pass log idiom of :func:`git_change_counts` to also
    capture each commit's author (``%H%x00%an``) so callers can flag knowledge
    silos (high-churn, single-/dominant-author files). One ``git log``
    invocation parsed in a single pass — no per-commit subprocess. Returns
    ``{}`` when there is no git repo, git is missing, or there is no history, so
    callers self-disable cleanly.
    """
    if not (repo_root / ".git").exists():
        return {}

    git_path = which("git")
    if git_path is None:
        return {}

    try:
        result = subprocess.run(
            [
                git_path,
                "-C",
                str(repo_root),
                "log",
                "--no-renames",
                "--format=%H%x00%an",
                "--name-only",
                "-n",
                str(GIT_LOG_MAX_COMMITS),
                "--",
                ".",
                ":(exclude).codescent",
            ],
            capture_output=True,
            check=False,
            text=True,
            timeout=GIT_HISTORY_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return {}
    if result.returncode != 0:
        return {}

    totals: dict[str, int] = {}
    authors: dict[str, dict[str, int]] = {}
    commit_paths: set[str] = set()
    current_author: str | None = None
    for line in result.stdout.splitlines():
        # The header line is ``<hash>\x00<author>``; file paths never contain a
        # NUL, so the delimiter cleanly separates headers from name-only output.
        if "\x00" in line:
            _add_author_churn(totals, authors, commit_paths, current_author)
            commit_paths = set()
            current_author = line.split("\x00", 1)[1]
            continue
        changed_path = line.strip()
        if changed_path:
            commit_paths.add(changed_path)
    _add_author_churn(totals, authors, commit_paths, current_author)

    return {
        path: FileAuthorChurn(
            churn=total,
            top_author_share=max(authors[path].values()) / total,
            author_count=len(authors[path]),
        )
        for path, total in sorted(totals.items())
    }


def _add_author_churn(
    totals: dict[str, int],
    authors: dict[str, dict[str, int]],
    commit_paths: set[str],
    author: str | None,
) -> None:
    if author is None:
        return
    for changed_path in commit_paths:
        if _is_excluded_cochange_path(changed_path):
            continue
        totals[changed_path] = totals.get(changed_path, 0) + 1
        per_author = authors.setdefault(changed_path, {})
        per_author[author] = per_author.get(author, 0) + 1


def _add_change_counts(counts: dict[str, int], commit_paths: set[str]) -> None:
    for changed_path in commit_paths:
        if _is_excluded_cochange_path(changed_path):
            continue
        counts[changed_path] = counts.get(changed_path, 0) + 1


def _add_co_change_counts(
    counts: dict[str, int],
    commit_paths: set[str],
    target_path: str,
) -> None:
    for changed_path in commit_paths:
        if changed_path == target_path or _is_excluded_cochange_path(changed_path):
            continue
        counts[changed_path] = counts.get(changed_path, 0) + 1


def _is_commit_hash(line: str) -> bool:
    return len(line) == COMMIT_HASH_LENGTH and all(
        character in COMMIT_HASH_CHARACTERS for character in line
    )


def _parse_git_status_paths(stdout: str) -> tuple[str, ...]:
    paths: list[str] = []
    for line in stdout.splitlines():
        if len(line) < MIN_PORCELAIN_STATUS_LINE_LENGTH or line.startswith("!!"):
            continue
        path = line[PORCELAIN_STATUS_PREFIX_WIDTH:]
        if " -> " in path:
            path = path.rsplit(" -> ", maxsplit=1)[1]
        paths.append(path.strip('"'))
    return tuple(paths)
