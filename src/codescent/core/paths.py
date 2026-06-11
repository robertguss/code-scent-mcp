from pathlib import Path

from codescent.core.errors import CodeScentError, ErrorCode, ErrorSeverity


def resolve_repo_root(root: Path | str) -> Path:
    path = Path(root).expanduser()
    resolved = path.resolve()
    if not resolved.is_dir():
        raise CodeScentError(
            code=ErrorCode.INVALID_REPO_ROOT,
            message="Repository root must be an existing directory.",
            severity=ErrorSeverity.ERROR,
            details={"root": str(path)},
        )
    return resolved


def normalize_repo_path(root: Path | str, requested: Path | str) -> Path:
    repo_root = resolve_repo_root(root)
    candidate = (repo_root / requested).resolve()

    try:
        _ = candidate.relative_to(repo_root)
    except ValueError as exc:
        raise CodeScentError(
            code=ErrorCode.PATH_OUTSIDE_ROOT,
            message="Path escapes the repository root.",
            severity=ErrorSeverity.ERROR,
            details={"root": str(repo_root), "path": str(requested)},
        ) from exc

    return candidate
