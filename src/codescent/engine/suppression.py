"""Inline suppression directives: ``# codescent: ignore[<rule_id>]``.

A pure, deterministic parser + matcher. It only READS source lines (passed in by
the caller); it never writes to disk. The pipeline in
``services/code_health.py`` reads the source, calls these functions, and persists
the matched findings with a ``suppressed`` status plus an audit trail.

Grammar (Python ``#`` and TS/Go ``//`` comments)::

    # codescent: ignore[rule_id]          -> silence one rule
    # codescent: ignore[rule_a, rule_b]   -> silence several rules
    # codescent: ignore                    -> bare form, silence every rule
    // codescent: ignore[rule_id]          -> same, for // languages

A directive matches a finding when the comment sits on the finding's own line OR
on the line directly above it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from codescent.engine.rules.model import CodeHealthFinding

# `#` or `//` then `codescent: ignore`, optionally followed by `[rule, rule]`.
# `\bignore\b` keeps `ignored`/`ignorelist` from matching; the keyword is
# case-sensitive so it never fires on prose.
_IGNORE_RE = re.compile(r"(?:#|//)\s*codescent\s*:\s*ignore\b\s*(?:\[([^\]]*)\])?")

# Evidence keys that carry a finding's 1-based source line, in priority order.
_LINE_EVIDENCE_KEYS = ("start_line", "line")


@dataclass(frozen=True, slots=True)
class IgnoreDirective:
    """One parsed ignore comment located at ``line`` (1-based)."""

    line: int
    rule_ids: frozenset[str]  # empty == bare form (every rule)
    comment: str  # verbatim comment text, kept for the audit trail

    def matches_rule(self, rule_id: str) -> bool:
        return not self.rule_ids or rule_id in self.rule_ids


@dataclass(frozen=True, slots=True)
class SuppressionMatch:
    """A finding silenced by ``comment`` (the directive that matched it)."""

    stable_key: str
    rule_id: str
    comment: str


def parse_ignore_directives(lines: Sequence[str]) -> tuple[IgnoreDirective, ...]:
    """Extract every ignore directive from ``lines`` (1-based line numbers)."""
    directives: list[IgnoreDirective] = []
    for index, text in enumerate(lines, start=1):
        match = _IGNORE_RE.search(text)
        if match is None:
            continue
        raw = match.group(1)
        rule_ids: frozenset[str] = (
            frozenset(_split_rule_ids(raw)) if raw is not None else frozenset()
        )
        directives.append(
            IgnoreDirective(
                line=index,
                rule_ids=rule_ids,
                comment=text[match.start() :].strip(),
            ),
        )
    return tuple(directives)


def finding_candidate_lines(
    finding: CodeHealthFinding,
    symbol_lines: Mapping[tuple[str, str], int],
) -> frozenset[int]:
    """Resolve the 1-based source line(s) a finding can be suppressed at.

    Uses explicit ``start_line``/``line`` evidence when present, and otherwise
    resolves the finding's symbol to its definition line via ``symbol_lines``
    (``(file_path, qualified_name) -> start_line``). File-level findings with no
    line and no symbol return an empty set and are never inline-suppressible.
    """
    lines: set[int] = set()
    for key in _LINE_EVIDENCE_KEYS:
        value = finding.evidence.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 1:
            lines.add(value)
    if finding.symbol is not None:
        start = symbol_lines.get((finding.file_path, finding.symbol))
        if start is not None:
            lines.add(start)
    return frozenset(lines)


def suppressing_directive(
    finding_lines: Iterable[int],
    directives: Sequence[IgnoreDirective],
    rule_id: str,
) -> IgnoreDirective | None:
    """Return the directive that silences ``rule_id`` at one of ``finding_lines``.

    Matches a comment on the finding's own line or the line directly above it.
    """
    by_line = {directive.line: directive for directive in directives}
    for line in finding_lines:
        for comment_line in (line, line - 1):
            directive = by_line.get(comment_line)
            if directive is not None and directive.matches_rule(rule_id):
                return directive
    return None


def match_suppressions(
    findings: Iterable[CodeHealthFinding],
    directives_by_file: Mapping[str, Sequence[IgnoreDirective]],
    symbol_lines: Mapping[tuple[str, str], int],
) -> dict[str, SuppressionMatch]:
    """Map ``stable_key -> SuppressionMatch`` for every silenced finding."""
    matches: dict[str, SuppressionMatch] = {}
    for finding in findings:
        directives = directives_by_file.get(finding.file_path)
        if not directives:
            continue
        lines = finding_candidate_lines(finding, symbol_lines)
        if not lines:
            continue
        directive = suppressing_directive(lines, directives, finding.rule_id)
        if directive is not None:
            matches[finding.stable_key] = SuppressionMatch(
                stable_key=finding.stable_key,
                rule_id=finding.rule_id,
                comment=directive.comment,
            )
    return matches


def _split_rule_ids(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]
