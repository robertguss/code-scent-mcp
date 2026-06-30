"""Enrichment payload builder for the grep-injection hook (U3).

Turns a usable pattern into the bounded, ranked, symbol-collapsed,
freshness/risk-tagged ``additionalContext`` string the hook injects. Read-only:
it ranks via :func:`ranked_matches` (which records nothing) and renders. The
payload is hard-capped near 240 tokens (R9) and ends with a pointer back to
codescent's own search tools.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from codescent.services.hook_retrieval import ranked_matches

if TYPE_CHECKING:
    from pathlib import Path

    from codescent.services.hook_retrieval import HookMatch

# ~240-token budget (R9), estimated at ~4 chars/token.
_MAX_TOKENS: Final = 240
_POINTER: Final = (
    "→ prefer codescent's search tools for ranked, bounded, fresh results."
)


def build_payload(
    repo_root: Path | str,
    pattern: str,
    *,
    limit: int = 5,
) -> str | None:
    """Bounded enrichment for ``pattern``, or ``None`` when there are no matches.

    Ranks up to ``limit`` matches read-only, renders one line each (enclosing
    symbol + repo-relative ``path:line`` + freshness tag, with a health tag only
    on git-modified matches), and trims to the token budget.
    """
    matches = ranked_matches(repo_root, pattern, limit=limit)
    if not matches:
        return None
    lines = [_render_line(match) for match in matches]
    while lines and _estimate_tokens(_assemble(pattern, lines)) > _MAX_TOKENS:
        _ = lines.pop()
    if not lines:
        return None
    return _assemble(pattern, lines)


def _assemble(pattern: str, lines: list[str]) -> str:
    header = f"codescent · `{pattern}` ({len(lines)} ranked, frecency+git):"
    return "\n".join([header, *lines, _POINTER])


def _render_line(match: HookMatch) -> str:
    symbol = _symbol_label(match)
    location = f"{match.path}:{match.line}"
    freshness = "modified" if match.git_modified else "fresh"
    line = f"  {symbol}  {location}  ~{freshness}"
    if match.git_modified and match.health:
        line += f"  ⚠ {','.join(match.health)}"
    return line


def _symbol_label(match: HookMatch) -> str:
    if match.symbol_name is None:
        return "(module level)"
    if match.symbol_kind in {"function", "method"}:
        return f"{match.symbol_name}()"
    return match.symbol_name


def _estimate_tokens(text: str) -> int:
    return len(text) // 4
