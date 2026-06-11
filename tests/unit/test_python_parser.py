from pathlib import Path

from codescent.engine.parsers.python import parse_python_file
from codescent.services.symbols import SymbolService


def test_extracts_python_symbols_imports_and_tests(tmp_path: Path) -> None:
    source = tmp_path / "tests" / "test_service.py"
    source.parent.mkdir()
    _ = source.write_text(
        """from __future__ import annotations
import os
from pkg.worker import run_task


class Service:
    def execute(self) -> str:
        return run_task(os.getcwd())


async def test_execute() -> None:
    service = Service()
    assert service.execute()
""",
    )

    parsed = parse_python_file(source, "tests/test_service.py")

    assert parsed.path == "tests/test_service.py"
    assert parsed.is_test is True
    assert {imported.module for imported in parsed.imports} == {
        "__future__",
        "os",
        "pkg.worker",
    }
    assert {
        (symbol.name, symbol.qualified_name, symbol.kind) for symbol in parsed.symbols
    } == {
        ("Service", "tests.test_service.Service", "class"),
        ("execute", "tests.test_service.Service.execute", "method"),
        ("test_execute", "tests.test_service.test_execute", "async_function"),
    }
    assert all(symbol.start_line <= symbol.end_line for symbol in parsed.symbols)
    assert all(symbol.confidence == 1.0 for symbol in parsed.symbols)


def test_uncertain_relationships_have_low_confidence(tmp_path: Path) -> None:
    source = tmp_path / "src" / "service.py"
    source.parent.mkdir()
    _ = source.write_text(
        """def dispatch(handler_name: str, payload: dict[str, str]) -> None:
    handler = globals()[handler_name]
    handler(payload)
""",
    )

    parsed = parse_python_file(source, "src/service.py")

    handler_reference = next(
        reference for reference in parsed.references if reference.name == "handler"
    )

    assert handler_reference.confidence < 0.6


def test_malformed_python_file_does_not_abort_repo_extraction(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    valid = repo / "src" / "pkg" / "service.py"
    broken = repo / "src" / "pkg" / "broken.py"
    valid.parent.mkdir(parents=True)
    _ = valid.write_text("def ok() -> None:\n    pass\n")
    _ = broken.write_text("def broken(:\n")

    result = SymbolService(repo).extract()
    files = {parsed.path: parsed for parsed in result.files}

    assert files["src/pkg/service.py"].symbols[0].qualified_name == "pkg.service.ok"
    assert files["src/pkg/broken.py"].parse_error is not None
    assert files["src/pkg/broken.py"].symbols == ()
