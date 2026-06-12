from __future__ import annotations

import pytest
from pydantic import ValidationError

from codescent.core.models import (
    CommandHints,
    ConfigSource,
    ContextOptions,
    ContextPack,
    EvalResult,
    Finding,
    IndexedFile,
    PageOptions,
    ProjectConfig,
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
        "ContextPack",
        "RefactorPlan",
        "SuggestedVerification",
        "EvalResult",
    ]
