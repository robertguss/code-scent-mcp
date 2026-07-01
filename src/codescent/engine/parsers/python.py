from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Final, TypedDict, override

HIGH_CONFIDENCE: Final = 1.0
LOW_CONFIDENCE: Final = 0.4


class SymbolPayload(TypedDict):
    name: str
    qualified_name: str
    kind: str
    start_line: int
    end_line: int
    confidence: float


class ImportPayload(TypedDict):
    module: str
    name: str | None
    line: int
    confidence: float


class ReferencePayload(TypedDict):
    name: str
    line: int
    confidence: float


@dataclass(frozen=True, slots=True)
class ParsedSymbol:
    name: str
    qualified_name: str
    kind: str
    start_line: int
    end_line: int
    confidence: float

    def to_payload(self) -> SymbolPayload:
        return {
            "name": self.name,
            "qualified_name": self.qualified_name,
            "kind": self.kind,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "confidence": self.confidence,
        }


@dataclass(frozen=True, slots=True)
class ParsedImport:
    module: str
    name: str | None
    line: int
    confidence: float

    def to_payload(self) -> ImportPayload:
        return {
            "module": self.module,
            "name": self.name,
            "line": self.line,
            "confidence": self.confidence,
        }


@dataclass(frozen=True, slots=True)
class ParsedReference:
    name: str
    line: int
    confidence: float

    def to_payload(self) -> ReferencePayload:
        return {
            "name": self.name,
            "line": self.line,
            "confidence": self.confidence,
        }


@dataclass(frozen=True, slots=True)
class ParsedPythonFile:
    path: str
    module: str
    is_test: bool
    symbols: tuple[ParsedSymbol, ...]
    imports: tuple[ParsedImport, ...]
    references: tuple[ParsedReference, ...]
    parse_error: str | None = None

    def to_payload(
        self,
    ) -> dict[
        str,
        str
        | bool
        | None
        | tuple[SymbolPayload, ...]
        | tuple[ImportPayload, ...]
        | tuple[ReferencePayload, ...],
    ]:
        return {
            "path": self.path,
            "module": self.module,
            "is_test": self.is_test,
            "symbols": tuple(symbol.to_payload() for symbol in self.symbols),
            "imports": tuple(imported.to_payload() for imported in self.imports),
            "references": tuple(
                reference.to_payload() for reference in self.references
            ),
            "parse_error": self.parse_error,
        }


def parse_python_file(path: Path | str, relative_path: str) -> ParsedPythonFile:
    source_path = Path(path)
    module = _module_name(relative_path)
    try:
        tree = ast.parse(source_path.read_text(), filename=relative_path)
    except SyntaxError as error:
        return ParsedPythonFile(
            path=relative_path,
            module=module,
            is_test=_is_test_path(relative_path),
            symbols=(),
            imports=(),
            references=(),
            parse_error=_syntax_error_message(error),
        )
    visitor = _PythonParser(module=module)
    visitor.visit(tree)
    return ParsedPythonFile(
        path=relative_path,
        module=module,
        is_test=_is_test_path(relative_path),
        symbols=tuple(visitor.symbols),
        imports=tuple(visitor.imports),
        references=tuple(visitor.references),
    )


class _PythonParser(ast.NodeVisitor):
    def __init__(self, *, module: str) -> None:
        self._module: str = module
        self._class_stack: list[str] = []
        self.symbols: list[ParsedSymbol] = []
        self.imports: list[ParsedImport] = []
        self.references: list[ParsedReference] = []

    @override
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        qualified_name = _qualified_name(self._module, (*self._class_stack, node.name))
        self.symbols.append(_symbol(node, node.name, qualified_name, "class"))
        self._class_stack.append(node.name)
        self.generic_visit(node)
        _ = self._class_stack.pop()

    @override
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._record_function(node, is_async=False)
        self.generic_visit(node)

    @override
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._record_function(node, is_async=True)
        self.generic_visit(node)

    @override
    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append(
                ParsedImport(
                    module=alias.name,
                    name=alias.asname,
                    line=node.lineno,
                    confidence=HIGH_CONFIDENCE,
                ),
            )

    @override
    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = "." * node.level + (node.module or "")
        for alias in node.names:
            self.imports.append(
                ParsedImport(
                    module=module,
                    name=alias.name,
                    line=node.lineno,
                    confidence=HIGH_CONFIDENCE,
                ),
            )

    @override
    def visit_Call(self, node: ast.Call) -> None:
        reference = _call_reference(node)
        if reference is not None:
            self.references.append(reference)
        self.generic_visit(node)

    @override
    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        # A variable annotation (``x: MyType``) uses ``MyType`` even if the name
        # appears nowhere else, so emit it as a reference (R9).
        self.references.extend(_annotation_references(node.annotation))
        self.generic_visit(node)

    def _record_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        *,
        is_async: bool,
    ) -> None:
        kind = _function_kind(self._class_stack, is_async=is_async)
        qualified_name = _qualified_name(self._module, (*self._class_stack, node.name))
        self.symbols.append(_symbol(node, node.name, qualified_name, kind))
        # Return and parameter type annotations use their type names; count them
        # so a class used only in a signature is not a dead-code false positive (R9).
        self.references.extend(_annotation_references(node.returns))
        for annotation in _parameter_annotations(node.args):
            self.references.extend(_annotation_references(annotation))


def _symbol(
    node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef,
    name: str,
    qualified_name: str,
    kind: str,
) -> ParsedSymbol:
    return ParsedSymbol(
        name=name,
        qualified_name=qualified_name,
        kind=kind,
        start_line=node.lineno,
        end_line=node.end_lineno or node.lineno,
        confidence=HIGH_CONFIDENCE,
    )


def _call_reference(node: ast.Call) -> ParsedReference | None:
    match node.func:
        case ast.Name(id=name):
            return ParsedReference(
                name=name,
                line=node.lineno,
                confidence=LOW_CONFIDENCE,
            )
        case ast.Attribute(attr=name):
            return ParsedReference(
                name=name,
                line=node.lineno,
                confidence=LOW_CONFIDENCE,
            )
        case _:
            return None


def _parameter_annotations(args: ast.arguments) -> list[ast.expr | None]:
    """Every parameter's annotation across all arg kinds (pos-only..kwarg)."""
    annotations = [
        arg.annotation for arg in (*args.posonlyargs, *args.args, *args.kwonlyargs)
    ]
    annotations.extend(
        extra.annotation for extra in (args.vararg, args.kwarg) if extra is not None
    )
    return annotations


def _annotation_references(annotation: ast.expr | None) -> list[ParsedReference]:
    """References for every type name used in ``annotation`` (nested generics too).

    Walks the annotation collecting the referenced type names, so
    ``tuple[Foo, ...]`` yields ``Foo`` and ``mod.MyType`` yields ``MyType`` (the
    leading ``mod`` is a namespace, not a referenced type, so it is skipped --
    otherwise tokens like ``typing``/``collections`` pollute related-file
    matching). Names inside an embedded call such as ``Annotated[int, Field()]``
    are left to ``visit_Call`` so they are not double-counted. These are
    ``LOW_CONFIDENCE`` like call references (ponytail: annotations are static but
    the name-use index only needs presence, not certainty).

    ponytail: explicit string forward-refs (``x: "Foo"``) parse to ``Constant``
    and are skipped; ``from __future__ import annotations`` keeps real AST nodes,
    so it is unaffected.
    """
    if annotation is None:
        return []
    skip: set[int] = set()
    for node in ast.walk(annotation):
        if isinstance(node, ast.Call):
            skip.update(id(child) for child in ast.walk(node))
        elif isinstance(node, ast.Attribute) and isinstance(
            node.value,
            ast.Name | ast.Attribute,
        ):
            # The value side of a dotted name is a namespace qualifier; only the
            # final attribute (`.attr`) names the referenced type.
            skip.add(id(node.value))
    references: list[ParsedReference] = []
    for node in ast.walk(annotation):
        if id(node) in skip:
            continue
        if isinstance(node, ast.Name):
            references.append(
                ParsedReference(
                    name=node.id, line=node.lineno, confidence=LOW_CONFIDENCE
                ),
            )
        elif isinstance(node, ast.Attribute):
            references.append(
                ParsedReference(
                    name=node.attr,
                    line=node.lineno,
                    confidence=LOW_CONFIDENCE,
                ),
            )
    return references


def _function_kind(class_stack: list[str], *, is_async: bool) -> str:
    if class_stack:
        return "async_method" if is_async else "method"
    return "async_function" if is_async else "function"


def _module_name(relative_path: str) -> str:
    without_suffix = relative_path.removesuffix(".py")
    raw_parts = tuple(part for part in without_suffix.split("/") if part != "__init__")
    parts = raw_parts[1:] if raw_parts[:1] == ("src",) else raw_parts
    return ".".join(parts)


def _qualified_name(module: str, parts: tuple[str, ...]) -> str:
    return ".".join((module, *parts))


def _is_test_path(relative_path: str) -> bool:
    path = Path(relative_path)
    return path.name.startswith("test_") or "tests" in path.parts


def _syntax_error_message(error: SyntaxError) -> str:
    line = error.lineno or 0
    offset = error.offset or 0
    return f"{error.msg} at line {line}, column {offset}"
