from __future__ import annotations

import json
from typing import cast

import pytest
from pydantic import ValidationError

from codescent.core.models import (
    CommandHints,
    ConfigSource,
    ContextOptions,
    ContextPack,
    EnvelopeConfidence,
    EnvelopeMode,
    EvalResult,
    Finding,
    IndexedFile,
    PageOptions,
    ProjectConfig,
    RefactorPlan,
    RepoConfig,
    RepoStatus,
    ResponseEnvelope,
    ScanRun,
    SearchOptions,
    SearchResult,
    SuggestedVerification,
    Symbol,
)


def test_context_defaults_are_bounded() -> None:
    options = ContextOptions()

    assert options.default_token_budget == 3000
    assert options.source_line_cap == 80
    assert options.max_source_line_cap == 200
    assert options.include_source is False


@pytest.mark.parametrize(
    "payload",
    [
        {"default_token_budget": 0},
        {"source_line_cap": 201},
        {"max_source_line_cap": 10},
    ],
)
def test_context_options_reject_invalid_bounds(payload: dict[str, int]) -> None:
    with pytest.raises(ValidationError):
        _ = ContextOptions.model_validate(payload)


def test_search_options_reject_unbounded_limits() -> None:
    options = SearchOptions.model_validate({"limit": 1_000})

    assert options.limit == 100


def test_pagination_bounds_are_enforced() -> None:
    options = PageOptions.model_validate({"limit": 999, "offset": -5})

    assert options.limit == 100
    assert options.offset == 0
    assert options.model_dump() == {"limit": 100, "offset": 0}


def test_config_source_orders_from_defaults_to_tool_args() -> None:
    assert list(ConfigSource) == [
        ConfigSource.DEFAULTS,
        ConfigSource.PROJECT_CONFIG,
        ConfigSource.CLI_FLAGS,
        ConfigSource.TOOL_ARGS,
    ]


def test_project_config_parses_full_prd_surface_with_precedence() -> None:
    config = ProjectConfig.model_validate(
        {
            "include": ["src", "tests"],
            "exclude": ["dist", "vendor"],
            "generated": ["src/generated"],
            "vendor": ["vendor"],
            "build": ["dist"],
            "language_packs": ["python", "typescript"],
            "framework_packs": ["react", "nextjs"],
            "rule_packs": ["python-maintainability"],
            "commands": {
                "test": ["pytest"],
                "typecheck": ["basedpyright"],
                "lint": ["ruff check ."],
                "build": ["python -m build"],
            },
            "token_budgets": {"context": 4500, "file": 600, "dashboard": 12000},
            "privacy": {"runtime_network": False, "allow_llm_review": True},
            "llm": {"provider": "openai", "model": "gpt-5.4"},
        },
    )
    merged = config.with_overrides(
        cli_flags={"include": ("src",), "token_budgets": {"context": 3000}},
        tool_args={"commands": {"test": ("pytest tests/test_config.py",)}},
    )

    assert config.include == ("src", "tests")
    assert config.exclude == ("dist", "vendor")
    assert config.generated == ("src/generated",)
    assert config.vendor == ("vendor",)
    assert config.build == ("dist",)
    assert config.language_packs == ("python", "typescript")
    assert config.framework_packs == ("react", "nextjs")
    assert config.rule_packs == ("python-maintainability",)
    assert config.commands == CommandHints(
        test=("pytest",),
        typecheck=("basedpyright",),
        lint=("ruff check .",),
        build=("python -m build",),
    )
    assert config.token_budgets.context == 4500
    assert config.privacy.runtime_network is False
    assert config.privacy.allow_llm_review is True
    assert config.llm is not None
    assert config.llm.provider == "openai"
    assert merged.include == ("src",)
    assert merged.token_budgets.context == 3000
    assert merged.commands.test == ("pytest tests/test_config.py",)


def test_project_config_defaults_enable_python_and_typescript_packs() -> None:
    config = ProjectConfig()

    assert config.language_packs == ("python", "typescript")
    assert config.rule_packs == ("python-maintainability", "ts-react-next")


def test_core_model_inventory_is_available() -> None:
    required_models = [
        RepoConfig,
        IndexedFile,
        Symbol,
        Finding,
        ScanRun,
        RepoStatus,
        PageOptions,
        SearchResult,
        ResponseEnvelope,
        ContextPack,
        RefactorPlan,
        SuggestedVerification,
        EvalResult,
    ]

    assert [model.__name__ for model in required_models] == [
        "RepoConfig",
        "IndexedFile",
        "Symbol",
        "Finding",
        "ScanRun",
        "RepoStatus",
        "PageOptions",
        "SearchResult",
        "ResponseEnvelope",
        "ContextPack",
        "RefactorPlan",
        "SuggestedVerification",
        "EvalResult",
    ]


@pytest.mark.parametrize(
    ("mode", "warnings", "retrieval_available", "original_result_id", "stats"),
    [
        (
            EnvelopeMode.EXACT,
            (),
            False,
            None,
            None,
        ),
        (
            EnvelopeMode.SUMMARIZED,
            ("heuristic summary may omit edge cases",),
            True,
            "ctx_abc123",
            cast(
                "dict[str, int | float]",
                {"returned_count": 2, "omitted_count": 8},
            ),
        ),
        (
            EnvelopeMode.FILTERED,
            ("filtered to test files only",),
            True,
            "ctx_filter_001",
            cast(
                "dict[str, int | float]",
                {"returned_count": 1, "omitted_count": 4},
            ),
        ),
        (
            EnvelopeMode.SAMPLE,
            ("sampled from a larger result set",),
            True,
            "ctx_sample_001",
            cast(
                "dict[str, int | float]",
                {"returned_count": 3, "omitted_count": 12},
            ),
        ),
        (
            EnvelopeMode.TRUNCATED,
            ("truncated at the configured limit",),
            False,
            None,
            cast(
                "dict[str, int | float]",
                {"returned_count": 20, "omitted_count": 80},
            ),
        ),
    ],
)
def test_response_envelope_serializes_modes_deterministically(
    mode: EnvelopeMode,
    warnings: tuple[str, ...],
    retrieval_available: bool,
    original_result_id: str | None,
    stats: dict[str, int | float] | None,
) -> None:
    envelope = ResponseEnvelope(
        kind="symbol_search_result",
        mode=mode,
        summary="Compact result envelope.",
        items=({"path": "src/app.py", "score": 0.99},),
        omitted_count=0 if mode is EnvelopeMode.EXACT else 4,
        original_result_id=original_result_id,
        retrieval_available=retrieval_available,
        retrieval_hints=(f"retrieve_result(id='{original_result_id}')",)
        if original_result_id is not None
        else (),
        confidence=(
            EnvelopeConfidence.HIGH
            if mode is EnvelopeMode.EXACT
            else EnvelopeConfidence.MEDIUM
        ),
        warnings=warnings,
        stats=stats,
    )

    assert envelope.model_dump(mode="json") == {
        "kind": "symbol_search_result",
        "mode": mode.value,
        "summary": "Compact result envelope.",
        "items": [{"path": "src/app.py", "score": 0.99}],
        "omitted_count": 0 if mode is EnvelopeMode.EXACT else 4,
        "original_result_id": original_result_id,
        "retrieval_available": retrieval_available,
        "retrieval_hints": [
            f"retrieve_result(id='{original_result_id}')",
        ]
        if original_result_id is not None
        else [],
        "confidence": (
            EnvelopeConfidence.HIGH.value
            if mode is EnvelopeMode.EXACT
            else EnvelopeConfidence.MEDIUM.value
        ),
        "warnings": list(warnings),
        "stats": stats,
    }
    assert envelope.model_dump_json() == json.dumps(
        {
            "kind": "symbol_search_result",
            "mode": mode.value,
            "summary": "Compact result envelope.",
            "items": [{"path": "src/app.py", "score": 0.99}],
            "omitted_count": 0 if mode is EnvelopeMode.EXACT else 4,
            "original_result_id": original_result_id,
            "retrieval_available": retrieval_available,
            "retrieval_hints": [
                f"retrieve_result(id='{original_result_id}')",
            ]
            if original_result_id is not None
            else [],
            "confidence": (
                EnvelopeConfidence.HIGH.value
                if mode is EnvelopeMode.EXACT
                else EnvelopeConfidence.MEDIUM.value
            ),
            "warnings": list(warnings),
            "stats": stats,
        },
        separators=(",", ":"),
    )


def test_response_envelope_rejects_invalid_mode() -> None:
    with pytest.raises(ValidationError):
        _ = ResponseEnvelope.model_validate(
            {
                "kind": "symbol_search_result",
                "mode": "partial",
                "summary": "Invalid mode.",
                "items": [],
            },
        )
