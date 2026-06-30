from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

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
            "Use CodeScent to assemble ONE bounded, deduped answer pack for a "
            "task: top files, key symbols, related tests, in-scope findings, and "
            "related files composed into a single object (a file shared across "
            "sources appears once). Pass max_tokens to fit a token budget; when "
            "content is dropped a ctx_ result id is returned so you can expand the "
            "full set with retrieve_result without rerunning retrieval. Read-only "
            "for analyzed source; bounded output."
        ),
    )(answer_pack)


def answer_pack(
    query: str,
    repo: str = ".",
    focus_path: str | None = None,
    max_tokens: int | None = None,
    budget: int | None = None,
) -> AnswerPackToolPayload:
    effective_budget = budget if budget is not None else max_tokens
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
