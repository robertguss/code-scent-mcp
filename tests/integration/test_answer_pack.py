from __future__ import annotations

from typing import TYPE_CHECKING, cast

from codescent.core.models import TokenBudgets
from codescent.core.token_estimate import estimate_tokens
from codescent.mcp.answer_pack_tools import answer_pack as answer_pack_tool
from codescent.services.answer_pack import (
    RELATED_FILE_CAP,
    AnswerPackService,
    serialize_answer_pack,
)
from codescent.services.code_health import CodeHealthService
from codescent.services.result_store import ResultStoreService

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from codescent.services.answer_pack import AnswerPack


def test_answer_pack_dedupes_files_across_sources(tmp_path: Path) -> None:
    repo = _linked_repo(tmp_path)

    pack = AnswerPackService(repo).answer_pack("alpha")

    # Both query-seeded files surface as top files exactly once.
    assert "src/app/alpha.py" in pack.top_files
    assert "src/app/alphaview.py" in pack.top_files
    # alphaview imports alpha, so it is a related candidate of alpha; because it
    # is already a top file it must NOT be duplicated into related_files.
    assert set(pack.top_files).isdisjoint(pack.related_files)
    # A directory-proximity neighbour that is neither a seed nor a test shows up.
    assert "src/app/sidebar.py" in pack.related_files
    # Symbols are deduped by qualified name.
    qualified = [symbol["qualified_name"] for symbol in pack.key_symbols]
    assert len(qualified) == len(set(qualified))


def test_answer_pack_enforces_token_budget(tmp_path: Path) -> None:
    repo = _wide_repo(tmp_path)

    full = AnswerPackService(repo).answer_pack("mod")
    budget = full.estimated_tokens // 2
    bounded = AnswerPackService(repo).answer_pack("mod", budget=budget)

    assert budget < full.estimated_tokens
    assert bounded.truncated is True
    assert bounded.estimated_tokens <= budget
    assert estimate_tokens(serialize_answer_pack(bounded)) <= budget
    assert _item_count(bounded) < _item_count(full)


def test_answer_pack_query_over_budget_reports_honestly(tmp_path: Path) -> None:
    # f5gn: when the query alone exceeds the budget, trimming every contributor
    # still cannot fit it. The pack must report that honestly (bypass the false
    # "fit" claim) and still fetch the full set BEFORE trimming (retrievable).
    repo = _wide_repo(tmp_path)
    long_query = "mod " * 40  # its token floor alone exceeds the tiny budget below
    budget = 3

    pack = AnswerPackService(repo).answer_pack(long_query, budget=budget)

    assert pack.truncated is True
    # Honest reporting: the pack does not pretend to fit a budget it cannot.
    assert pack.estimated_tokens > budget
    assert any("query alone exceeds the token budget" in note for note in pack.warnings)
    # The misleading "no context found" note must NOT fire on a budget-trimmed pack.
    assert not any("no answer pack context" in note for note in pack.warnings)

    # fetch-before-trim: the handle resolves to the full untrimmed set.
    assert pack.result_id is not None
    retrieved = ResultStoreService(repo).retrieve_result(
        pack.result_id,
        mode="exact",
        limit=100,
    )
    stored = retrieved["items"][0]
    assert isinstance(stored, dict)
    assert stored["top_files"]  # the full set was stored despite the trim to empty


def test_answer_pack_handle_expands_to_full_set_without_rerunning(
    tmp_path: Path,
) -> None:
    repo = _wide_repo(tmp_path)

    full = AnswerPackService(repo).answer_pack("mod")
    bounded = AnswerPackService(repo).answer_pack("mod", budget=40)

    assert bounded.truncated is True
    assert bounded.result_id is not None
    # The handle resolves to the stored fuller payload purely from the result
    # store (no retrieval/composition is re-run).
    retrieved = ResultStoreService(repo).retrieve_result(
        bounded.result_id,
        mode="exact",
        limit=100,
    )
    stored = retrieved["items"][0]
    assert isinstance(stored, dict)
    assert stored["top_files"] == list(full.top_files)
    assert stored["related_files"] == list(full.related_files)
    assert _stored_item_count(stored) > _item_count(bounded)


def test_answer_pack_caps_each_contributor_even_with_huge_budget(
    tmp_path: Path,
) -> None:
    repo = _wide_repo(tmp_path)

    pack = AnswerPackService(repo).answer_pack(
        "mod0",
        focus_path="src/app/mod0.py",
        budget=10**9,
    )

    # Many sibling modules are related; the pull is capped regardless of budget.
    assert pack.truncated is False
    assert len(pack.related_files) == RELATED_FILE_CAP
    assert len(pack.related_files) <= RELATED_FILE_CAP


def test_answer_pack_empty_query_returns_bounded_empty_pack(tmp_path: Path) -> None:
    repo = _linked_repo(tmp_path)

    pack = AnswerPackService(repo).answer_pack("")

    assert pack.top_files == ()
    assert pack.key_symbols == ()
    assert pack.related_tests == ()
    assert pack.findings == ()
    assert pack.related_files == ()
    assert pack.result_id is None
    assert pack.truncated is False
    assert pack.estimated_tokens >= 0
    assert any("no answer pack context" in warning for warning in pack.warnings)


def test_answer_pack_default_is_bounded(tmp_path: Path) -> None:
    repo = _wide_repo(tmp_path)

    pack = AnswerPackService(repo).answer_pack("mod")

    assert pack.result_id is None
    assert pack.truncated is False
    assert len(pack.top_files) <= 8
    assert len(pack.key_symbols) <= 12
    assert len(pack.related_tests) <= 8
    assert len(pack.findings) <= 10
    assert len(pack.related_files) <= RELATED_FILE_CAP
    assert all(
        set(finding) == {"id", "rule_id", "file_path", "severity"}
        for finding in pack.findings
    )


def test_answer_pack_tool_accepts_max_tokens_alias(tmp_path: Path) -> None:
    repo = _wide_repo(tmp_path)
    full = AnswerPackService(repo).answer_pack("mod")
    budget = full.estimated_tokens // 2

    payload = answer_pack_tool("mod", repo=str(repo), max_tokens=budget)

    assert payload["ok"] is True
    assert payload["truncated"] is True
    assert payload["result_id"] is not None
    assert payload["estimated_tokens"] <= budget
    assert any(tool.startswith("retrieve_result:") for tool in payload["next_tools"])


def test_answer_pack_tool_self_bounds_without_caller_budget(tmp_path: Path) -> None:
    repo = _large_repo(tmp_path)
    # The full pack is larger than the default budget, and the caller passes
    # neither budget nor max_tokens (U5): the tool must self-bound anyway.
    full = AnswerPackService(repo).answer_pack("orchestrate")
    default_budget = TokenBudgets().context
    assert full.estimated_tokens > default_budget

    payload = answer_pack_tool("orchestrate", repo=str(repo))

    assert payload["truncated"] is True
    assert payload["result_id"] is not None
    assert payload["estimated_tokens"] <= default_budget


def test_answer_pack_tool_small_query_not_truncated_by_self_bound(
    tmp_path: Path,
) -> None:
    repo = _wide_repo(tmp_path)
    # The full pack fits under the default budget, so the self-bound must not
    # truncate a pack that was already small.
    assert AnswerPackService(repo).answer_pack("mod").estimated_tokens < (
        TokenBudgets().context
    )

    payload = answer_pack_tool("mod", repo=str(repo))

    assert payload["truncated"] is False
    assert payload["result_id"] is None


def test_answer_pack_tool_explicit_budget_still_honored(tmp_path: Path) -> None:
    repo = _wide_repo(tmp_path)
    full = AnswerPackService(repo).answer_pack("mod")
    budget = full.estimated_tokens // 2

    payload = answer_pack_tool("mod", repo=str(repo), budget=budget)

    assert payload["truncated"] is True
    assert payload["estimated_tokens"] <= budget


def _large_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    base = (
        repo
        / "src"
        / "very"
        / "deeply"
        / "nested"
        / "enterprise"
        / "package"
        / "structure"
        / "components"
        / "orchestration"
    )
    base.mkdir(parents=True)
    for index in range(30):
        module = (
            base / f"widget_reconciliation_orchestration_service_module_{index:03d}.py"
        )
        _ = module.write_text(
            "def orchestrate_widget_reconciliation_workflow_handler_variant"
            f"_{index:03d}(configuration_payload_reference_argument) -> int:\n"
            "    # TODO: split this orchestration responsibility into smaller units\n"
            "    # FIXME: preserve backward compatibility with legacy queue names\n"
            "    # HACK: keep the old behavior until the big migration finally lands\n"
            f"    return {index}\n",
        )
    _ = CodeHealthService(repo).scan()
    return repo


def _item_count(pack: AnswerPack) -> int:
    return (
        len(pack.top_files)
        + len(pack.key_symbols)
        + len(pack.related_tests)
        + len(pack.findings)
        + len(pack.related_files)
    )


def _stored_item_count(stored: object) -> int:
    if not isinstance(stored, dict):
        return 0
    total = 0
    for value in cast("dict[str, object]", stored).values():
        if isinstance(value, list):
            total += len(cast("list[object]", value))
    return total


def _linked_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    app = repo / "src" / "app"
    tests_dir = repo / "tests"
    app.mkdir(parents=True)
    tests_dir.mkdir()
    _ = (app / "alpha.py").write_text('def alpha_fn() -> str:\n    return "a"\n')
    _ = (app / "alphaview.py").write_text(
        """from app.alpha import alpha_fn


def alphaview_fn() -> str:
    return alpha_fn()
""",
    )
    _ = (app / "sidebar.py").write_text('def sidebar_fn() -> str:\n    return "s"\n')
    _ = (tests_dir / "test_alpha.py").write_text(
        """from app.alpha import alpha_fn


def test_alpha() -> None:
    assert alpha_fn() == "a"
""",
    )
    return repo


def _wide_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    app = repo / "src" / "app"
    tests_dir = repo / "tests"
    app.mkdir(parents=True)
    tests_dir.mkdir()
    for index in range(10):
        _ = (app / f"mod{index}.py").write_text(
            f"""def mod{index}_fn() -> int:
    # TODO: split orchestration
    # FIXME: keep compatibility
    # HACK: preserve old behavior
    return {index}
""",
        )
    _ = (tests_dir / "test_mod0.py").write_text(
        """from app.mod0 import mod0_fn


def test_mod0() -> None:
    assert mod0_fn() == 0
""",
    )
    _ = CodeHealthService(repo).scan()
    return repo


def test_answer_pack_inherits_fuzzy_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _no_backend(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(
        "codescent.services.search.select_search_backend",
        _no_backend,
    )
    repo = _linked_repo(tmp_path)

    pack = AnswerPackService(repo).answer_pack("alphaview rendering helper function")

    assert "src/app/alphaview.py" in pack.top_files
