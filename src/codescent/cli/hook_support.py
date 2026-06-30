"""Pure search-detection and pattern-extraction logic for the hook (U2).

Side-effect-free string logic shared by the ``hook-augment`` entrypoint. The
Bash path inspects the command string only — it tokenizes with :mod:`shlex`
(which parses, never executes) and returns the pattern as inert data, so a
search term is never handed to a shell (R22).
"""

from __future__ import annotations

import re
import shlex
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Mapping

# The content/file-search binaries the hook enriches (R2).
_SEARCH_BINARIES: Final = frozenset({"rg", "grep", "ripgrep", "ag"})
# Flags whose *following* token is the search pattern (grep/rg).
_PATTERN_FLAGS: Final = frozenset({"-e", "--regexp", "-f", "--file"})
# Flags that consume a separate value, so that value is not the pattern.
_ARG_FLAGS: Final = frozenset(
    {"-A", "-B", "-C", "-m", "-d", "--max-count", "--context"},
)
# A usable pattern needs an identifier-like token of length >= 3 (KTD4).
_IDENTIFIER_RE: Final[re.Pattern[str]] = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")


def _tokenize(command: str) -> list[str]:
    stripped = command.strip()
    if not stripped:
        return []
    try:
        return shlex.split(stripped)
    except ValueError:
        # Unbalanced quotes etc. — fall back to a naive split; still no execution.
        return stripped.split()


def detect_search_command(command: str) -> bool:
    """True when ``command`` invokes a content/file search binary (R2).

    Inspects the leading token only; never executes the command.
    """
    tokens = _tokenize(command)
    if not tokens:
        return False
    return PurePosixPath(tokens[0]).name in _SEARCH_BINARIES


def extract_pattern(tool_name: str, tool_input: Mapping[str, object]) -> str | None:
    """Pull the raw search term from a Grep/Glob input or a Bash command.

    Returns the unvalidated candidate string (run it through
    :func:`usable_pattern` before use) or ``None`` when none is present.
    """
    if tool_name in {"Grep", "Glob"}:
        pattern = tool_input.get("pattern")
        return pattern if isinstance(pattern, str) and pattern else None
    if tool_name == "Bash":
        command = tool_input.get("command")
        if not isinstance(command, str):
            return None
        return _extract_bash_pattern(command)
    return None


def _extract_bash_pattern(command: str) -> str | None:
    tokens = _tokenize(command)
    if not tokens or PurePosixPath(tokens[0]).name not in _SEARCH_BINARIES:
        return None
    rest = tokens[1:]
    index = 0
    while index < len(rest):
        token = rest[index]
        if token in _PATTERN_FLAGS:
            return rest[index + 1] if index + 1 < len(rest) else None
        if token.startswith(("--regexp=", "--file=")):
            return token.split("=", 1)[1] or None
        if token in _ARG_FLAGS:
            index += 2
            continue
        if token.startswith("-"):
            index += 1
            continue
        return token
    return None


def usable_pattern(pattern: str | None) -> str | None:
    """Return the first identifier-like token of length >= 3, else ``None`` (KTD4).

    Rejects pure-regex/wildcard/punctuation patterns and too-short tokens so the
    hook never builds a noisy, low-value shortlist (R3).
    """
    if not pattern:
        return None
    match = _IDENTIFIER_RE.search(pattern)
    return match.group(0) if match else None
