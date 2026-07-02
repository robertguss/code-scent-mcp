from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Final, cast

from codescent.core.token_estimate import estimate_tokens
from codescent.services.findings import FindingsService
from codescent.services.result_store import ResultStoreService
from codescent.services.task_brief import ACTIONABLE_STATUSES

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from codescent.services.context import ContextService
    from codescent.services.context_support import SymbolMatchPayload
    from codescent.services.result_store import JsonValue
    from codescent.storage.repositories import FindingRow

TOP_FILE_CAP: Final = 8
SYMBOL_CAP: Final = 12
RELATED_TEST_CAP: Final = 8
FINDING_CAP: Final = 10
RELATED_FILE_CAP: Final = 6
SEED_FILE_LIMIT: Final = 4
# Bounded pull per seed file: enough to fill both the related-file and the
# related-test caps without an unbounded fetch (the two share one ranked query).
RELATED_PULL_LIMIT: Final = RELATED_FILE_CAP + RELATED_TEST_CAP


@dataclass(frozen=True, slots=True)
class AnswerPack:
    query: str
    top_files: tuple[str, ...]
    key_symbols: tuple[SymbolMatchPayload, ...]
    related_tests: tuple[str, ...]
    findings: tuple[dict[str, str], ...]
    related_files: tuple[str, ...]
    result_id: str | None
    truncated: bool
    estimated_tokens: int
    warnings: tuple[str, ...]


@dataclass(slots=True)
class Contributors:
    top_files: list[str]
    key_symbols: list[SymbolMatchPayload]
    related_tests: list[str]
    findings: list[dict[str, str]]
    related_files: list[str]


def related_neighbors(
    context: ContextService,
    top_files: tuple[str, ...],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    top_set = set(top_files)
    tests: list[str] = []
    related: list[str] = []
    for path in top_files:
        try:
            file_context = context.get_file_context(path)
            neighbors = context.get_related_files(path, limit=RELATED_PULL_LIMIT)
        except LookupError:
            continue
        tests.extend(file_context["likely_tests"])
        for neighbor in neighbors["results"]:
            neighbor_path = neighbor["path"]
            if is_test_path(neighbor_path):
                tests.append(neighbor_path)
            elif neighbor_path not in top_set:
                related.append(neighbor_path)
    return (
        dedupe_cap((test for test in tests if test not in top_set), RELATED_TEST_CAP),
        dedupe_cap(related, RELATED_FILE_CAP),
    )


def in_scope_findings(repo_root: Path, scope: set[str]) -> tuple[dict[str, str], ...]:
    if not scope:
        return ()
    findings = sorted(
        FindingsService(repo_root).get_smell_report().findings,
        key=lambda finding: (finding.file_path, finding.rule_id, finding.id),
    )
    return tuple(
        _finding_payload(finding)
        for finding in findings
        if finding.file_path in scope and finding.status in ACTIONABLE_STATUSES
    )[:FINDING_CAP]


def _finding_payload(finding: FindingRow) -> dict[str, str]:
    return {
        "id": finding.id,
        "rule_id": finding.rule_id,
        "file_path": finding.file_path,
        "severity": finding.severity,
    }


def store_full(
    repo_root: Path,
    query: str,
    parts: Contributors,
    full_tokens: int,
) -> str:
    stored = ResultStoreService(repo_root).store_result(
        project_id=f"repo:{repo_root.as_posix()}",
        tool_name="answer_pack",
        input_payload={"query": query},
        raw_result=_contributor_dict(query, parts),
        raw_token_estimate=full_tokens,
    )
    return stored.id


def fit_budget(
    query: str,
    parts: Contributors,
    budget: int,
    *,
    full_tokens: int | None = None,
) -> None:
    tokens = full_tokens
    if tokens is None:
        tokens = estimate_tokens(serialize_contributors(query, parts))
    while tokens > budget:
        if not _drop_last(parts):
            return
        tokens = estimate_tokens(serialize_contributors(query, parts))


def _drop_last(parts: Contributors) -> bool:
    for sequence in (
        parts.related_files,
        parts.findings,
        parts.related_tests,
        parts.key_symbols,
        parts.top_files,
    ):
        if sequence:
            _ = sequence.pop()
            return True
    return False


def to_pack(  # noqa: PLR0913 - keyword-only budget/truncation presentation flags.
    query: str,
    parts: Contributors,
    *,
    result_id: str | None,
    truncated: bool,
    precomputed_tokens: int | None = None,
    budget_exceeded: bool = False,
) -> AnswerPack:
    estimated = (
        precomputed_tokens
        if precomputed_tokens is not None
        else estimate_tokens(serialize_contributors(query, parts))
    )
    return AnswerPack(
        query=query,
        top_files=tuple(parts.top_files),
        key_symbols=tuple(parts.key_symbols),
        related_tests=tuple(parts.related_tests),
        findings=tuple(parts.findings),
        related_files=tuple(parts.related_files),
        result_id=result_id,
        truncated=truncated,
        estimated_tokens=estimated,
        warnings=_warnings(
            parts,
            truncated=truncated,
            result_id=result_id,
            budget_exceeded=budget_exceeded,
        ),
    )


def _warnings(
    parts: Contributors,
    *,
    truncated: bool,
    result_id: str | None,
    budget_exceeded: bool,
) -> tuple[str, ...]:
    notes: list[str] = []
    # Only flag "no context" when the pack is genuinely empty (no results) --
    # not when the budget trimmed every contributor away (context existed).
    if not _has_content(parts) and not truncated:
        notes.append("no answer pack context found; broaden the query or run a scan")
    if truncated and result_id is not None:
        # Query-over-budget: even a fully-trimmed pack cannot fit the budget, so
        # say so plainly rather than claiming a fit; otherwise it did fit.
        reason = (
            "query alone exceeds the token budget"
            if budget_exceeded
            else "truncated to fit budget"
        )
        notes.append(f"answer pack {reason}; expand the full set via {result_id}")
    return tuple(notes)


def _has_content(parts: Contributors) -> bool:
    return bool(
        parts.top_files
        or parts.key_symbols
        or parts.related_tests
        or parts.findings
        or parts.related_files,
    )


def serialize_answer_pack(pack: AnswerPack) -> str:
    """Render the bounded contributor payload of ``pack`` as canonical JSON.

    The same shape that the budget estimator and the stored ``ctx_`` snapshot use,
    so ``estimate_tokens(serialize_answer_pack(pack)) == pack.estimated_tokens``.

    Args:
        pack: The composed answer pack to serialize.

    Returns:
        A deterministic JSON string of the pack's contributor lists.
    """
    return serialize_contributors(
        pack.query,
        Contributors(
            top_files=list(pack.top_files),
            key_symbols=list(pack.key_symbols),
            related_tests=list(pack.related_tests),
            findings=list(pack.findings),
            related_files=list(pack.related_files),
        ),
    )


def serialize_contributors(query: str, parts: Contributors) -> str:
    return json.dumps(
        _contributor_dict(query, parts),
        sort_keys=True,
        separators=(",", ":"),
    )


def _contributor_dict(query: str, parts: Contributors) -> dict[str, JsonValue]:
    payload: dict[str, object] = {
        "query": query,
        "top_files": list(parts.top_files),
        "key_symbols": [dict(symbol) for symbol in parts.key_symbols],
        "related_tests": list(parts.related_tests),
        "findings": [dict(finding) for finding in parts.findings],
        "related_files": list(parts.related_files),
    }
    return cast("dict[str, JsonValue]", cast("object", payload))


def dedupe_symbols(
    symbols: Iterable[SymbolMatchPayload],
) -> tuple[SymbolMatchPayload, ...]:
    seen: set[str] = set()
    deduped: list[SymbolMatchPayload] = []
    for symbol in symbols:
        key = symbol["qualified_name"]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(symbol)
        if len(deduped) >= SYMBOL_CAP:
            break
    return tuple(deduped)


def dedupe_cap(items: Iterable[str], limit: int) -> tuple[str, ...]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
        if len(deduped) >= limit:
            break
    return tuple(deduped)


def is_test_path(path: str) -> bool:
    parsed = PurePosixPath(path)
    return parsed.name.startswith("test_") or "tests" in parsed.parts
