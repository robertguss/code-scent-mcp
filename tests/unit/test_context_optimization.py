from codescent.services.context_optimization import (
    ContextEnvelope,
    ResultPayload,
    RetrievalHint,
    estimate_tokens,
    result_id_for_payload,
    should_store_result,
    summarize_result,
)


def test_estimate_tokens_is_local_and_stable_for_text_payload() -> None:
    payload: ResultPayload = {
        "items": (
            {
                "path": "src/app.py",
                "line": 10,
                "symbol": "load_config",
                "snippet": "def load_config():\n    return {'debug': False}\n",
            },
        ),
    }

    assert estimate_tokens(payload) == estimate_tokens(payload)
    assert estimate_tokens(payload) > 0


def test_result_id_is_opaque_ctx_hash_for_same_payload() -> None:
    payload: ResultPayload = {
        "items": (
            {
                "path": "src/app.py",
                "line": 10,
                "symbol": "load_config",
                "snippet": "def load_config(): pass",
            },
        ),
    }

    first = result_id_for_payload(
        tool_name="search_content",
        session_id="sess_default",
        query="load_config",
        payload=payload,
    )
    second = result_id_for_payload(
        tool_name="search_content",
        session_id="sess_default",
        query="load_config",
        payload=payload,
    )

    assert first == second
    assert first.startswith("ctx_")
    assert len(first) == 20


def test_should_store_result_when_count_exceeds_returned_limit() -> None:
    payload: ResultPayload = {
        "items": tuple(
            {
                "path": f"src/app_{index}.py",
                "line": index + 1,
                "symbol": "load_config",
                "snippet": "load_config()",
            }
            for index in range(4)
        ),
    }

    assert should_store_result(payload, returned_limit=3) is True


def test_summarize_result_builds_retrievable_envelope() -> None:
    payload: ResultPayload = {
        "items": tuple(
            {
                "path": f"src/app_{index}.py",
                "line": index + 1,
                "symbol": "load_config",
                "snippet": "load_config()",
            }
            for index in range(4)
        ),
    }

    envelope = summarize_result(
        kind="search_content",
        result_id="ctx_1234567890abcdef",
        payload=payload,
        returned_limit=2,
    )

    assert envelope == ContextEnvelope(
        kind="search_content",
        mode="summary",
        summary="4 items; showing 2. Retrieve ctx_1234567890abcdef for full result.",
        omitted_count=2,
        original_result_id="ctx_1234567890abcdef",
        retrieval_available=True,
        retrieval_hints=(
            RetrievalHint(mode="exact", description="return the full stored payload"),
            RetrievalHint(mode="filtered", description="filter by file or symbol"),
            RetrievalHint(mode="sample", description="return a bounded sample"),
        ),
        confidence="high",
        warnings=(),
    )
