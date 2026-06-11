from __future__ import annotations

import pytest
from pydantic import ValidationError

from codescent.core.models import (
    ConfigSource,
    ContextOptions,
    ContextPack,
    EvalResult,
    Finding,
    IndexedFile,
    RefactorPlan,
    RepoConfig,
    RepoStatus,
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


def test_config_source_orders_from_defaults_to_tool_args() -> None:
    assert list(ConfigSource) == [
        ConfigSource.DEFAULTS,
        ConfigSource.PROJECT_CONFIG,
        ConfigSource.CLI_FLAGS,
        ConfigSource.TOOL_ARGS,
    ]


def test_core_model_inventory_is_available() -> None:
    required_models = [
        RepoConfig,
        IndexedFile,
        Symbol,
        Finding,
        ScanRun,
        RepoStatus,
        SearchResult,
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
        "SearchResult",
        "ContextPack",
        "RefactorPlan",
        "SuggestedVerification",
        "EvalResult",
    ]
