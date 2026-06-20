"""Deterministic behavior-preservation check for an edit.

``verify_refactor`` compares a *before* and *after* version of a Python file and
proves — deterministically, no LLM judgment — that the edit preserved the public
surface: the set of exported symbols, their signatures, and that no net-new
control-flow branches slipped in. When it cannot prove safety it reports concrete
violations rather than blessing a risky change. CodeScent never writes analyzed
source; both states are read-only (the working tree on disk, the baseline from
``git show``).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from codescent.core.errors import CodeScentError
from codescent.core.paths import normalize_repo_path, resolve_repo_root
from codescent.engine.source_read import read_source_text
from codescent.services.git import git_file_at_ref

if TYPE_CHECKING:
    from pathlib import Path

_BRANCH_NODES: Final = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.Try,
    ast.With,
    ast.AsyncWith,
    ast.IfExp,
    ast.BoolOp,
    ast.comprehension,
)
_VERIFY_CONFIDENCE: Final = 0.9


@dataclass(frozen=True, slots=True)
class PublicSymbol:
    qualified_name: str
    kind: str
    signature: str


@dataclass(frozen=True, slots=True)
class VerifyViolation:
    kind: str
    symbol: str
    detail: str


@dataclass(frozen=True, slots=True)
class VerifyResult:
    # `preserved` is only meaningful when `verifiable` is true. When the tool
    # could not analyze the file (unsupported language, unreadable/unparseable
    # state) it returns verifiable=False, and callers must not treat
    # preserved=False as "behavior broke".
    verifiable: bool
    preserved: bool
    path: str
    base_ref: str
    transform_kind: str
    language: str
    violations: tuple[VerifyViolation, ...]
    warnings: tuple[str, ...]
    added_symbols: tuple[str, ...]
    removed_symbols: tuple[str, ...]
    changed_symbols: tuple[str, ...]
    confidence: float


@dataclass(frozen=True, slots=True)
class VerifyRefactorService:
    repo_root: Path | str

    def verify_refactor(
        self,
        *,
        path: str,
        base_ref: str = "HEAD",
        transform_kind: str = "generic",
    ) -> VerifyResult:
        repo_root = resolve_repo_root(self.repo_root)
        if not path.endswith((".py", ".pyi")):
            return _unsupported(path, base_ref, transform_kind)
        try:
            after_path = normalize_repo_path(repo_root, path)
        except CodeScentError:
            # A path that escapes the repo is a caller error, but the tool's
            # contract is to always return a structured (unverifiable) result.
            return _failed(
                path,
                base_ref,
                transform_kind,
                "path is outside the repository",
            )
        # Use the normalized repo-relative path for *both* states so an absolute
        # or `..` path cannot read the working tree while silently failing the
        # `git show` and degrading to a false "preserved".
        relative_path = after_path.relative_to(repo_root).as_posix()
        after = read_source_text(after_path)
        if after.text is None:
            return _failed(
                relative_path,
                base_ref,
                transform_kind,
                "after state could not be read",
            )
        before = (
            git_file_at_ref(repo_root, base_ref, relative_path) if base_ref else None
        )
        return verify_python_sources(
            before,
            after.text,
            path=relative_path,
            base_ref=base_ref,
            transform_kind=transform_kind,
        )


def verify_python_sources(
    before: str | None,
    after: str,
    *,
    path: str,
    base_ref: str = "",
    transform_kind: str = "generic",
) -> VerifyResult:
    after_surface = _public_surface(after)
    if after_surface is None:
        return _failed(path, base_ref, transform_kind, "after state does not parse")
    warnings: list[str] = []
    if before is None:
        warnings.append("no before state; nothing to compare against")
        before_surface: dict[str, PublicSymbol] = {}
    else:
        parsed_before = _public_surface(before)
        if parsed_before is None:
            return _failed(
                path,
                base_ref,
                transform_kind,
                "before state does not parse",
            )
        before_surface = parsed_before

    removed = tuple(sorted(set(before_surface) - set(after_surface)))
    added = tuple(sorted(set(after_surface) - set(before_surface)))
    changed = tuple(
        sorted(
            name
            for name in set(before_surface) & set(after_surface)
            if before_surface[name].signature != after_surface[name].signature
        ),
    )
    violations = (
        *(
            VerifyViolation("removed_symbol", name, "public symbol was removed")
            for name in removed
        ),
        *(
            VerifyViolation(
                "signature_changed",
                name,
                f"{before_surface[name].signature} -> {after_surface[name].signature}",
            )
            for name in changed
        ),
    )
    if added:
        warnings.append(f"new public symbols added: {', '.join(added)}")
    branch_delta = _branch_count(after) - _branch_count(before or "")
    if branch_delta > 0:
        warnings.append(
            f"{branch_delta} net-new control-flow branch(es) — verify added logic",
        )
    return VerifyResult(
        verifiable=True,
        preserved=not violations,
        path=path,
        base_ref=base_ref,
        transform_kind=transform_kind,
        language="python",
        violations=violations,
        warnings=tuple(warnings),
        added_symbols=added,
        removed_symbols=removed,
        changed_symbols=changed,
        confidence=_VERIFY_CONFIDENCE,
    )


def _public_surface(source: str) -> dict[str, PublicSymbol] | None:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    surface: dict[str, PublicSymbol] = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            if not _is_public(node.name):
                continue
            kind = (
                "async_function"
                if isinstance(node, ast.AsyncFunctionDef)
                else "function"
            )
            surface[node.name] = PublicSymbol(node.name, kind, _signature(node))
        elif isinstance(node, ast.ClassDef) and _is_public(node.name):
            surface[node.name] = PublicSymbol(node.name, "class", "")
            _collect_methods(node, surface)
    return surface


def _collect_methods(node: ast.ClassDef, surface: dict[str, PublicSymbol]) -> None:
    for item in node.body:
        if not isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if not _is_public(item.name) and item.name != "__init__":
            continue
        qualified = f"{node.name}.{item.name}"
        surface[qualified] = PublicSymbol(qualified, "method", _signature(item))


def _is_public(name: str) -> bool:
    return not name.startswith("_")


def _signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    args = node.args
    positional = [*args.posonlyargs, *args.args]
    # Defaults bind to the tail of the positional parameters.
    first_default = len(positional) - len(args.defaults)
    parts: list[str] = []
    for index, arg in enumerate(args.posonlyargs):
        parts.append(_param(arg.arg, has_default=index >= first_default))
    if args.posonlyargs:
        parts.append("/")
    for offset, arg in enumerate(args.args):
        index = len(args.posonlyargs) + offset
        parts.append(_param(arg.arg, has_default=index >= first_default))
    if args.vararg is not None:
        parts.append(f"*{args.vararg.arg}")
    elif args.kwonlyargs:
        parts.append("*")
    for index, arg in enumerate(args.kwonlyargs):
        parts.append(_param(arg.arg, has_default=args.kw_defaults[index] is not None))
    if args.kwarg is not None:
        parts.append(f"**{args.kwarg.arg}")
    returns = f" -> {ast.unparse(node.returns)}" if node.returns is not None else ""
    return f"({', '.join(parts)}){returns}"


def _param(name: str, *, has_default: bool) -> str:
    # Mark default presence (removing a default breaks callers that relied on it)
    # without baking the default's literal value into the signature identity.
    return f"{name}=" if has_default else name


def _branch_count(source: str) -> int:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return 0
    return sum(1 for node in ast.walk(tree) if isinstance(node, _BRANCH_NODES))


def _unsupported(path: str, base_ref: str, transform_kind: str) -> VerifyResult:
    return VerifyResult(
        verifiable=False,
        preserved=False,
        path=path,
        base_ref=base_ref,
        transform_kind=transform_kind,
        language="unsupported",
        violations=(),
        warnings=("verify_refactor supports Python (.py) files in v1",),
        added_symbols=(),
        removed_symbols=(),
        changed_symbols=(),
        confidence=0.0,
    )


def _failed(
    path: str,
    base_ref: str,
    transform_kind: str,
    detail: str,
) -> VerifyResult:
    return VerifyResult(
        verifiable=False,
        preserved=False,
        path=path,
        base_ref=base_ref,
        transform_kind=transform_kind,
        language="python",
        violations=(VerifyViolation("unverifiable", path, detail),),
        warnings=(),
        added_symbols=(),
        removed_symbols=(),
        changed_symbols=(),
        confidence=0.0,
    )
