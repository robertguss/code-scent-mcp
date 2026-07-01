from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

from codescent.core.models import TokenBudgets
from codescent.services.answer_pack import AnswerPackService
from codescent.services.context_support import (
    SymbolMatchPayload,  # noqa: TC001  (runtime: fastmcp builds the TypedDict schema)
)

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from codescent.services.answer_pack import AnswerPack


class AnswerPackToolPayload(TypedDict):
    ok: bool
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
    next_tools: tuple[str, ...]


def register_answer_pack_tools(mcp: FastMCP) -> None:
    _ = mcp.tool(
        description=(
            "Token-budgeted, deduped answer pack for ONE specific question: "
            "top files, key symbols, related tests, in-scope findings, and "
            "related files in a single object. Pass max_tokens to fit a budget; "
            "when content is dropped a ctx_ result id is returned to expand the "
            "full set via retrieve_result. Prefer start_task to open fresh work; "
            "reach for answer_pack when a specific question must fit a token "
            "budget. e.g. answer_pack(query='how does login work', "
            "max_tokens=4000). Read-only for source; bounded output."
        ),
    )(answer_pack)


def answer_pack(
    query: str,
    repo: str = ".",
    focus_path: str | None = None,
    max_tokens: int | None = None,
    budget: int | None = None,
) -> AnswerPackToolPayload:
    # Self-bound: when the caller passes neither budget nor max_tokens, fall back
    # to the shared context budget so the pack always truncates + offers a
    # result_id instead of returning an unbounded object (KTD5 — reuse the
    # existing TokenBudgets().context default rather than add a redundant knob).
    effective_budget = budget if budget is not None else max_tokens
    if effective_budget is None:
        effective_budget = TokenBudgets().context
    pack = AnswerPackService(repo).answer_pack(
        query,
        focus_path=focus_path,
        budget=effective_budget,
    )
    return _answer_pack_payload(pack)


def _answer_pack_payload(pack: AnswerPack) -> AnswerPackToolPayload:
    return {
        "ok": True,
        "query": pack.query,
        "top_files": pack.top_files,
        "key_symbols": pack.key_symbols,
        "related_tests": pack.related_tests,
        "findings": pack.findings,
        "related_files": pack.related_files,
        "result_id": pack.result_id,
        "truncated": pack.truncated,
        "estimated_tokens": pack.estimated_tokens,
        "warnings": pack.warnings,
        "next_tools": _next_tools(pack),
    }


def _next_tools(pack: AnswerPack) -> tuple[str, ...]:
    tools: list[str] = []
    if pack.key_symbols:
        tools.append(f"get_symbol_context:{pack.key_symbols[0]['qualified_name']}")
    tools.append("select_tests")
    if pack.result_id is not None:
        tools.append(f"retrieve_result:{pack.result_id}")
    return tuple(tools)
