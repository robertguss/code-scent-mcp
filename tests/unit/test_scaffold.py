import ast

import pytest

from codescent.services.scaffold import (
    build_characterization_scaffold,
    module_path_from_file,
)


def test_module_path_from_file_drops_src_and_init() -> None:
    assert module_path_from_file("src/pkg/config.py") == "pkg.config"
    assert module_path_from_file("pkg/config.py") == "pkg.config"
    assert module_path_from_file("src/pkg/__init__.py") == "pkg"


def test_scaffold_code_parses_and_imports_the_target() -> None:
    scaffold = build_characterization_scaffold(
        file_path="src/codescent/services/scaffold.py",
        qualified_symbols=("codescent.services.scaffold.module_path_from_file",),
    )
    # Parses cleanly (a syntactically valid module).
    _ = ast.parse(scaffold.code)
    assert "from codescent.services.scaffold import module_path_from_file" in (
        scaffold.code
    )
    assert scaffold.symbol == "module_path_from_file"
    assert scaffold.filename == "test_module_path_from_file_characterization.py"

    # Executing the module runs the import (proving the target is importable)
    # and defines the test function without running it.
    namespace: dict[str, object] = {}
    exec(compile(scaffold.code, scaffold.filename, "exec"), namespace)  # noqa: S102
    assert "module_path_from_file" in namespace
    assert scaffold.test_name in namespace


def test_scaffold_is_honest_no_fake_green() -> None:
    scaffold = build_characterization_scaffold(
        file_path="src/codescent/services/scaffold.py",
        qualified_symbols=("codescent.services.scaffold.module_path_from_file",),
    )
    # No silently-passing assertion is emitted.
    assert "assert True" not in scaffold.code
    assert "raise NotImplementedError(" in scaffold.code

    # The placeholder test fails loudly when run -> never a false-positive pass.
    namespace: dict[str, object] = {}
    exec(compile(scaffold.code, scaffold.filename, "exec"), namespace)  # noqa: S102
    placeholder = namespace[scaffold.test_name]
    assert callable(placeholder)
    with pytest.raises(NotImplementedError):
        _ = placeholder()


def test_scaffold_falls_back_to_module_import_without_symbols() -> None:
    scaffold = build_characterization_scaffold(
        file_path="src/pkg/config.py",
        qualified_symbols=(),
    )
    _ = ast.parse(scaffold.code)
    assert "import pkg.config" in scaffold.code
    assert scaffold.symbol == ""
    assert any("module" in note for note in scaffold.notes)
