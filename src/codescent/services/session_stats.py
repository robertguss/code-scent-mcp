from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING

from codescent.storage import RepositoryStorage, initialize_storage
from codescent.storage.repositories import SessionEventRepository, SessionEventRow

if TYPE_CHECKING:
    from pathlib import Path

type JsonScalar = str | int | float | bool | None
type JsonObject = dict[str, JsonScalar]

MAX_EVENTS: int = 500
MAX_LARGEST_RESULTS: int = 5
MAX_MOST_USED_TOOLS: int = 5
MAX_REPEATED_QUERIES: int = 10
MAX_WARNINGS: int = 10


@dataclass(frozen=True, slots=True)
class ContextStats:
    session_id: str
    tool_calls: int
    summarized_results: int
    retrievals: int
    estimated_raw_tokens: int
    estimated_returned_tokens: int
    estimated_tokens_avoided: int
    largest_summarized_results: tuple[JsonObject, ...]
    most_used_tools: tuple[str, ...]
    repeated_broad_queries: tuple[JsonObject, ...]
    warnings: tuple[JsonObject, ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "tool_calls": self.tool_calls,
            "summarized_results": self.summarized_results,
            "retrievals": self.retrievals,
            "estimated_raw_tokens": self.estimated_raw_tokens,
            "estimated_returned_tokens": self.estimated_returned_tokens,
            "estimated_tokens_avoided": self.estimated_tokens_avoided,
            "largest_summarized_results": list(self.largest_summarized_results),
            "most_used_tools": list(self.most_used_tools),
            "repeated_broad_queries": list(self.repeated_broad_queries),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class ContextStatsService:
    repo_root: Path | str

    def context_stats(self, *, project_id: str, session_id: str) -> ContextStats:
        state = initialize_storage(self.repo_root)
        repository = SessionEventRepository(RepositoryStorage(state))
        events = repository.list_events(
            project_id=project_id,
            session_id=session_id,
            limit=MAX_EVENTS,
        )
        return _aggregate_stats(session_id=session_id, events=events)


def _aggregate_stats(
    *,
    session_id: str,
    events: tuple[SessionEventRow, ...],
) -> ContextStats:
    tool_counter: Counter[str] = Counter()
    broad_query_counter: Counter[tuple[str, str]] = Counter()
    warning_counter: Counter[str] = Counter()
    largest_results: list[JsonObject] = []
    raw_tokens = 0
    returned_tokens = 0
    avoided_tokens = 0
    tool_calls = 0
    summarized_results = 0
    retrievals = 0

    for event in events:
        tool = event.tool_name or "unknown"
        payload = event.payload
        raw = _payload_int(payload, "raw_tokens")
        returned = _payload_int(payload, "returned_tokens")
        if event.event_type == "tool_called":
            tool_calls += 1
            tool_counter[tool] += 1
            if payload.get("broad_query") is True:
                fingerprint = _event_fingerprint(payload)
                broad_query_counter[(tool, fingerprint)] += 1
        elif event.event_type == "large_result_summarized":
            summarized_results += 1
            raw_tokens += raw
            returned_tokens += returned
            avoided_tokens += max(raw - returned, 0)
            largest_results.append(
                {
                    "tool": tool,
                    "query_fingerprint": str(payload.get("query_fingerprint", "")),
                    "input_fingerprint": _event_fingerprint(payload),
                    "raw_tokens": raw,
                    "returned_tokens": returned,
                },
            )
        elif event.event_type == "result_retrieved":
            retrievals += 1
            raw_tokens += raw
            returned_tokens += returned
        elif event.event_type == "agent_repeated_query":
            fingerprint = _event_fingerprint(payload)
            broad_query_counter[(tool, fingerprint)] += max(
                _payload_int(payload, "retrieval_count"),
                1,
            )
        elif event.event_type == "agent_requested_exact_large_result":
            raw_tokens += raw
            returned_tokens += returned
        elif event.event_type == "server_warning_returned":
            warning_code = str(payload.get("warning_code") or "unspecified")
            warning_counter[warning_code] += max(
                _payload_int(payload, "warning_count"),
                1,
            )

    largest_summarized_results = tuple(
        sorted(
            largest_results,
            key=lambda result: (
                -_sort_int(result["raw_tokens"]),
                str(result["tool"]),
                str(result["input_fingerprint"]),
            ),
        )[:MAX_LARGEST_RESULTS],
    )
    return ContextStats(
        session_id=session_id,
        tool_calls=tool_calls,
        summarized_results=summarized_results,
        retrievals=retrievals,
        estimated_raw_tokens=raw_tokens,
        estimated_returned_tokens=returned_tokens,
        estimated_tokens_avoided=avoided_tokens,
        largest_summarized_results=largest_summarized_results,
        most_used_tools=_most_used_tools(tool_counter),
        repeated_broad_queries=_repeated_broad_queries(broad_query_counter),
        warnings=_warnings(warning_counter),
    )


def _event_fingerprint(payload: JsonObject) -> str:
    fingerprint = payload.get("input_fingerprint") or payload.get("query_fingerprint")
    return str(fingerprint or "unknown")


def _payload_int(payload: JsonObject, key: str) -> int:
    return _sort_int(payload.get(key))


def _sort_int(value: JsonScalar) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, float):
        return max(int(value), 0)
    return 0


def _most_used_tools(tool_counter: Counter[str]) -> tuple[str, ...]:
    return tuple(
        tool
        for tool, _count in sorted(
            tool_counter.items(),
            key=lambda item: (-item[1], item[0]),
        )[:MAX_MOST_USED_TOOLS]
    )


def _repeated_broad_queries(
    broad_query_counter: Counter[tuple[str, str]],
) -> tuple[JsonObject, ...]:
    repeated: list[JsonObject] = [
        {"tool": tool, "input_fingerprint": fingerprint, "count": count}
        for (tool, fingerprint), count in broad_query_counter.items()
        if count > 1
    ]
    return tuple(
        sorted(
            repeated,
            key=lambda item: (
                -_sort_int(item["count"]),
                str(item["tool"]),
                str(item["input_fingerprint"]),
            ),
        )[:MAX_REPEATED_QUERIES],
    )


def _warnings(warning_counter: Counter[str]) -> tuple[JsonObject, ...]:
    warnings: list[JsonObject] = [
        {"warning_code": warning_code, "count": count}
        for warning_code, count in warning_counter.items()
    ]
    return tuple(
        sorted(
            warnings,
            key=lambda item: (-_sort_int(item["count"]), str(item["warning_code"])),
        )[:MAX_WARNINGS],
    )
