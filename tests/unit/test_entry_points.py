from pathlib import Path
from textwrap import dedent

from codescent.engine.rules.entry_points import (
    build_entry_point_registry,
    registered_surface_reasons,
)

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "python-entrypoint"


def test_registered_surface_reasons_includes_new_tools_and_commands() -> None:
    reasons = registered_surface_reasons()

    # The capability-guide / resume / preflight tools must be recognized so the
    # dogfood gate never flags them dead (the cbm in-degree=0 trap).
    for tool in ("how_to_use", "resume_task", "refactor_preflight"):
        assert tool in reasons
        assert "MCP tool" in reasons[tool]

    assert "scan" in reasons
    assert "CLI command" in reasons["scan"]

    assert "_genuinely_dead" not in reasons


def test_registry_recognizes_each_entry_point_category() -> None:
    registry = build_entry_point_registry(_FIXTURE)

    # __all__ export.
    assert registry.is_entry_point("exported_handler")
    exported_reason = registry.reason_for("exported_handler")
    assert exported_reason is not None
    assert "__all__" in exported_reason

    # Decorator-registered callable (@app.command()).
    decorated_reason = registry.reason_for("decorated_command")
    assert decorated_reason is not None
    assert "decorator" in decorated_reason

    # Call-form registration: app.command(...)(public_entry).
    call_reason = registry.reason_for("public_entry")
    assert call_reason is not None
    assert "call" in call_reason

    # Registered MCP tool surfaced from public_surface, even though the fixture
    # never references it.
    how_to_use_reason = registry.reason_for("how_to_use")
    assert how_to_use_reason is not None
    assert "MCP tool" in how_to_use_reason

    # A private helper that is referenced internally is NOT an entry point.
    assert not registry.is_entry_point("_shared")

    # The genuinely-dead private function is NOT an entry point.
    assert not registry.is_entry_point("_genuinely_dead")
    assert registry.reason_for("_genuinely_dead") is None


def test_registry_detects_dynamic_dispatch(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(
        repo / "src" / "pkg" / "dispatch.py",
        """
        def route(name: str, target: object) -> object:
            return getattr(target, "dispatched_handler")
        """,
    )

    registry = build_entry_point_registry(repo)

    reason = registry.reason_for("dispatched_handler")
    assert reason is not None
    assert "dynamic dispatch" in reason


def test_registry_is_deterministic() -> None:
    first = build_entry_point_registry(_FIXTURE)
    second = build_entry_point_registry(_FIXTURE)

    assert first.reasons == second.reasons
    assert list(first.reasons.items()) == list(second.reasons.items())


def _write(path: Path, source: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(dedent(source))
