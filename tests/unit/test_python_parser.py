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


def test_type_annotation_references_are_captured(tmp_path: Path) -> None:
    source = tmp_path / "src" / "models.py"
    source.parent.mkdir(parents=True)
    _ = source.write_text(
        """class Foo:
    pass


class Bar:
    pass


class Baz:
    pass


class Qux:
    pass


def handler(x: Foo, items: tuple[Bar, ...]) -> Baz:
    value: Qux = x
    return value
""",
    )

    parsed = parse_python_file(source, "src/models.py")
    names = {reference.name for reference in parsed.references}

    # Return (Baz), parameter (Foo), nested-generic (Bar), and variable (Qux)
    # annotations each contribute their type name.
    assert {"Foo", "Bar", "Baz", "Qux"} <= names


def test_non_annotation_references_are_unchanged(tmp_path: Path) -> None:
    source = tmp_path / "src" / "svc.py"
    source.parent.mkdir(parents=True)
    _ = source.write_text(
        """def run():
    helper()
    obj.method()
""",
    )

    parsed = parse_python_file(source, "src/svc.py")

    assert sorted(reference.name for reference in parsed.references) == [
        "helper",
        "method",
    ]


def test_qualified_annotation_does_not_leak_namespace(tmp_path: Path) -> None:
    source = tmp_path / "src" / "typed.py"
    source.parent.mkdir(parents=True)
    _ = source.write_text(
        """def f(x: typing.Optional[int], y: collections.abc.Sequence) -> mod.MyType:
    return x
""",
    )

    names = [
        reference.name
        for reference in parse_python_file(source, "src/typed.py").references
    ]

    # Only the referenced type names -- the dotted-name qualifiers (which are
    # namespaces, not types) must not pollute the reference set.
    assert {"MyType", "Optional", "Sequence"} <= set(names)
    assert not ({"mod", "typing", "collections", "abc"} & set(names))


def test_call_inside_annotation_is_not_double_counted(tmp_path: Path) -> None:
    source = tmp_path / "src" / "ann.py"
    source.parent.mkdir(parents=True)
    _ = source.write_text(
        """def f(z: Annotated[int, Field()]) -> None:
    return None
""",
    )

    names = [
        reference.name
        for reference in parse_python_file(source, "src/ann.py").references
    ]

    # ``Field()`` is emitted once by visit_Call; the annotation walker must not
    # count it a second time.
    assert names.count("Field") == 1
