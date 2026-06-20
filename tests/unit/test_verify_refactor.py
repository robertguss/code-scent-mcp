from codescent.services.verify_refactor import verify_python_sources

_BEFORE = """def load_config(path):
    return path


class Reader:
    def __init__(self, path):
        self.path = path

    def read(self, encoding):
        return encoding
"""


def test_identical_sources_preserve_behavior() -> None:
    result = verify_python_sources(_BEFORE, _BEFORE, path="config.py")

    assert result.preserved is True
    assert result.violations == ()
    assert result.removed_symbols == ()
    assert result.changed_symbols == ()


def test_removed_public_symbol_is_a_violation() -> None:
    after = "def load_config(path):\n    return path\n"

    result = verify_python_sources(_BEFORE, after, path="config.py")

    assert result.preserved is False
    assert "Reader" in result.removed_symbols
    assert {violation.kind for violation in result.violations} == {"removed_symbol"}


def test_signature_change_on_a_surviving_symbol_is_a_violation() -> None:
    after = _BEFORE.replace("def load_config(path):", "def load_config(path, strict):")

    result = verify_python_sources(_BEFORE, after, path="config.py")

    assert result.preserved is False
    assert result.changed_symbols == ("load_config",)
    violation = next(v for v in result.violations if v.kind == "signature_changed")
    assert violation.symbol == "load_config"
    assert "strict" in violation.detail


def test_added_public_symbol_is_a_warning_not_a_violation() -> None:
    after = _BEFORE + "\n\ndef new_helper(value):\n    return value\n"

    result = verify_python_sources(_BEFORE, after, path="config.py")

    assert result.preserved is True
    assert "new_helper" in result.added_symbols
    assert any("new public symbols" in warning for warning in result.warnings)


def test_net_new_branch_is_warned_but_preserves_the_surface() -> None:
    after = _BEFORE.replace(
        "def load_config(path):\n    return path",
        "def load_config(path):\n    if path:\n        return path\n    return path",
    )

    result = verify_python_sources(_BEFORE, after, path="config.py")

    assert result.preserved is True
    assert any("net-new control-flow" in warning for warning in result.warnings)


def test_private_helpers_are_not_part_of_the_public_surface() -> None:
    after = _BEFORE + "\n\ndef _private_helper(value):\n    return value\n"

    result = verify_python_sources(_BEFORE, after, path="config.py")

    assert result.preserved is True
    assert result.added_symbols == ()


def test_missing_before_state_preserves_but_warns() -> None:
    result = verify_python_sources(None, _BEFORE, path="config.py")

    assert result.preserved is True
    assert any("no before state" in warning for warning in result.warnings)


def test_unparseable_after_state_is_unverifiable() -> None:
    result = verify_python_sources(_BEFORE, "def broken(:\n", path="config.py")

    assert result.preserved is False
    assert result.violations[0].kind == "unverifiable"
