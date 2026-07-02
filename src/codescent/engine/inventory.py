import hashlib
from fnmatch import fnmatch
from pathlib import Path
from typing import Final

from codescent.core.models import IndexedFile, ProjectConfig
from codescent.core.paths import resolve_repo_root
from codescent.engine.source_read import read_source_bytes

DEFAULT_EXCLUDED_NAMES: Final = frozenset(
    {
        # Tool-local, gitignored, non-source dirs: beads issue/history data and
        # Claude agent worktrees/settings. Scanning them buries real findings
        # under tens of thousands of duplicate-literal hits (same class as the
        # already-excluded ``.codescent``; mirrors U3's co-change exclusion).
        ".beads",
        ".claude",
        ".codescent",
        ".git",
        ".hg",
        ".mypy_cache",
        ".next",
        ".omo",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "__pycache__",
        "__generated__",
        "archive",
        "build",
        "coverage",
        "data",
        "dist",
        "generated",
        "node_modules",
        "vendor",
    },
)
DEFAULT_EXCLUDED_FILENAMES: Final = frozenset(
    {
        ".env",
        ".env.local",
        "package-lock.json",
        "pnpm-lock.yaml",
        "uv.lock",
        "yarn.lock",
    },
)
MINIFIED_SUFFIXES: Final = (".min.js", ".min.css")
LANGUAGE_BY_SUFFIX: Final = {
    ".js": "javascript",
    ".jsx": "javascript",
    ".py": "python",
    ".pyi": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
}


CODESCENTIGNORE_FILENAME: Final = ".codescentignore"


def read_codescentignore(repo_root: Path) -> tuple[str, ...]:
    """Read repo-root ``.codescentignore`` patterns (blanks/``#`` comments skipped).

    Absent or unreadable file yields ``()`` -- backward compatible. Full
    ``.gitignore`` semantics (negation, nested files, pathspec) are deferred;
    each line is treated as one exclude pattern for the shared matcher.
    """
    try:
        text = (repo_root / CODESCENTIGNORE_FILENAME).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ()
    return tuple(
        stripped
        for line in text.splitlines()
        for stripped in (line.strip(),)
        if stripped and not stripped.startswith("#")
    )


def build_file_inventory(
    root: Path | str,
    *,
    config: ProjectConfig | None = None,
) -> tuple[IndexedFile, ...]:
    repo_root = resolve_repo_root(root)
    project_config = config or ProjectConfig()
    ignore_patterns = read_codescentignore(repo_root)
    files: list[IndexedFile] = []

    for path in sorted(repo_root.rglob("*")):
        if not path.is_file() or _is_excluded(
            repo_root,
            path,
            project_config,
            ignore_patterns,
        ):
            continue
        if path.is_symlink() and not _stays_inside_root(repo_root, path):
            continue

        language = LANGUAGE_BY_SUFFIX.get(path.suffix)
        if language is None:
            continue

        source = read_source_bytes(path)
        content = source.content
        if content is None:
            continue
        if _is_binary(content):
            continue

        relative = path.relative_to(repo_root).as_posix()
        files.append(
            IndexedFile(
                path=relative,
                language=language,
                hash=hashlib.sha256(content).hexdigest(),
                size_bytes=source.size_bytes,
                line_count=_line_count(content),
                is_test=_is_test_path(relative),
                is_generated=False,
            ),
        )

    return tuple(files)


def _is_excluded(
    repo_root: Path,
    path: Path,
    config: ProjectConfig,
    ignore_patterns: tuple[str, ...] = (),
) -> bool:
    return excluded_by_names_or_patterns(
        path.relative_to(repo_root),
        config,
        ignore_patterns,
    )


def excluded_by_names_or_patterns(
    relative: Path,
    config: ProjectConfig,
    ignore_patterns: tuple[str, ...] = (),
) -> bool:
    """Single-sourced name/pattern exclusion shared by inventory + generic pack.

    Covers the default excluded dir names/filenames, minified suffixes, and the
    config exclude/generated/vendor/build patterns plus any ``.codescentignore``
    patterns -- so both the index and the generic literal pack stay in sync.
    """
    if relative.name in DEFAULT_EXCLUDED_FILENAMES:
        return True
    if any(part in DEFAULT_EXCLUDED_NAMES for part in relative.parts):
        return True
    if _matches_config_exclude(relative.as_posix(), config, ignore_patterns):
        return True
    return relative.name.endswith(MINIFIED_SUFFIXES)


def _matches_config_exclude(
    relative_path: str,
    config: ProjectConfig,
    ignore_patterns: tuple[str, ...] = (),
) -> bool:
    patterns = (
        *config.exclude,
        *config.generated,
        *config.vendor,
        *config.build,
        *ignore_patterns,
    )
    return any(_matches_path_pattern(relative_path, pattern) for pattern in patterns)


def _matches_path_pattern(relative_path: str, pattern: str) -> bool:
    normalized = pattern.strip().strip("/")
    if not normalized:
        return False
    if relative_path == normalized or relative_path.startswith(f"{normalized}/"):
        return True
    # Glob patterns (e.g. ``docs/generated/**``) go through fnmatch; plain path
    # prefixes are handled above, so this only widens wildcard patterns.
    return fnmatch(relative_path, normalized)


def _stays_inside_root(repo_root: Path, path: Path) -> bool:
    try:
        _ = path.resolve().relative_to(repo_root)
    except ValueError:
        return False
    return True


def _is_binary(content: bytes) -> bool:
    return b"\x00" in content


def _line_count(content: bytes) -> int:
    if not content:
        return 0
    line_breaks = content.count(b"\n")
    if content.endswith(b"\n"):
        return line_breaks
    return line_breaks + 1


def _is_test_path(relative_path: str) -> bool:
    return relative_path.startswith("tests/") or "/test_" in relative_path
