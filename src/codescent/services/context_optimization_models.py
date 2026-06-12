from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal, NotRequired, TypedDict

DEFAULT_SESSION_ID: Final = "sess_default"
DEFAULT_RESULT_TTL_SECONDS: Final = 86_400
MAX_RETRIEVAL_LIMIT: Final = 50
OPAQUE_ID_HEX_LENGTH: Final = 16

RetrievalMode = Literal["exact", "summary", "filtered", "sample"]
JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]


class ResultItem(TypedDict, total=False):
    path: str
    file: str
    line: int
    start_line: int
    symbol: str
    score: float
    confidence: float
    certainty: str
    caller: str
    snippet: str
    text: str


class ResultPayload(TypedDict):
    items: tuple[ResultItem, ...]


class SummaryPayload(TypedDict):
    summary: str


class RetrievalHint(TypedDict):
    mode: RetrievalMode
    description: str


class ContextEnvelope(TypedDict):
    kind: str
    mode: RetrievalMode
    summary: str
    omitted_count: int
    original_result_id: str | None
    retrieval_available: bool
    retrieval_hints: tuple[RetrievalHint, ...]
    confidence: str
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StoredResult:
    result_id: str
    session_id: str
    expires_at: str
    raw_token_estimate: int
    returned_token_estimate: int


class RetrievalPayload(TypedDict):
    ok: bool
    result_id: str
    mode: str
    session_id: str
    payload: ResultPayload
    error_code: NotRequired[str]
    warnings: tuple[str, ...]


class ContextStatsPayload(TypedDict):
    ok: bool
    session_id: str | None
    tool_calls: int
    summarized_results: int
    retrievals: int
    estimated_raw_tokens: int
    estimated_returned_tokens: int
    estimated_tokens_avoided: int
    largest_summarized_results: tuple[str, ...]
    most_used_tools: tuple[str, ...]
    warnings: tuple[str, ...]
