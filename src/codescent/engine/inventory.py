import hashlib
from pathlib import Path

from codescent.core.models import IndexedFile
from codescent.core.paths import resolve_repo_root

DEFAULT_EXCLUDED_NAMES = frozenset(
    {
        ".codescent",
        ".git",
        ".hg",
        ".mypy_cache",
        ".next",
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
DEFAULT_EXCLUDED_FILENAMES = frozenset(
    {
        ".env",
        ".env.local",
        "package-lock.json",
        "pnpm-lock.yaml",
        "uv.lock",
        "yarn.lock",
    },
)
MINIFIED_SUFFIXES = (".min.js", ".min.css")
LANGUAGE_BY_SUFFIX = {
    ".py": "python",
    ".pyi": "python",
}


def build_file_inventory(root: Path | str) -> tuple[IndexedFile, ...]:
    repo_root = resolve_repo_root(root)
    files: list[IndexedFile] = []

    for path in sorted(repo_root.rglob("*")):
        if not path.is_file() or _is_excluded(repo_root, path):
            continue
        if path.is_symlink() and not _stays_inside_root(repo_root, path):
            continue

        language = LANGUAGE_BY_SUFFIX.get(path.suffix)
        if language is None:
            continue

        content = path.read_bytes()
        if _is_binary(content):
            continue

        relative = path.relative_to(repo_root).as_posix()
        files.append(
            IndexedFile(
                path=relative,
                language=language,
                hash=hashlib.sha256(content).hexdigest(),
                size_bytes=len(content),
                line_count=_line_count(content),
                is_test=_is_test_path(relative),
                is_generated=False,
            ),
        )

    return tuple(files)


def _is_excluded(repo_root: Path, path: Path) -> bool:
    relative = path.relative_to(repo_root)
    parts = relative.parts

    if path.name in DEFAULT_EXCLUDED_FILENAMES:
        return True
    if any(part in DEFAULT_EXCLUDED_NAMES for part in parts):
        return True
    return path.name.endswith(MINIFIED_SUFFIXES)


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
