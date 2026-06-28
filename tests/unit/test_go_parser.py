from pathlib import Path

from codescent.engine.parsers.go import parse_go_file
from codescent.engine.parsers.python import LOW_CONFIDENCE

_SAMPLE = """package widgets

import (
\t"fmt"
\t"strings"
)

import "errors"

type Widget struct {
\tName string
}

type Renderer interface {
\tRender() string
}

func New(name string) *Widget {
\treturn &Widget{Name: name}
}

func (w *Widget) Render() string {
\treturn strings.ToUpper(w.Name)
}
"""


def test_parses_funcs_types_and_imports_as_low_confidence(tmp_path: Path) -> None:
    source = tmp_path / "widgets.go"
    _ = source.write_text(_SAMPLE)

    parsed = parse_go_file(source, "widgets.go")

    assert parsed.parse_error is None
    assert parsed.module == "widgets"

    symbols = {symbol.qualified_name: symbol for symbol in parsed.symbols}
    assert set(symbols) == {
        "widgets.Widget",
        "widgets.Renderer",
        "widgets.New",
        "widgets.Render",
    }
    assert symbols["widgets.Widget"].kind == "struct"
    assert symbols["widgets.Renderer"].kind == "interface"
    assert symbols["widgets.New"].kind == "function"
    assert symbols["widgets.Render"].kind == "method"
    # Heuristic regex parse -> every symbol/import is LOW_CONFIDENCE.
    assert all(symbol.confidence == LOW_CONFIDENCE for symbol in parsed.symbols)

    modules = {imported.module for imported in parsed.imports}
    assert modules == {"fmt", "strings", "errors"}
    assert all(imported.confidence == LOW_CONFIDENCE for imported in parsed.imports)


def test_symbol_spans_track_braces(tmp_path: Path) -> None:
    source = tmp_path / "widgets.go"
    _ = source.write_text(_SAMPLE)

    parsed = parse_go_file(source, "widgets.go")
    render = next(s for s in parsed.symbols if s.qualified_name == "widgets.Render")

    # `func (w *Widget) Render() string {` ... `}` spans 3 lines.
    assert render.end_line - render.start_line + 1 == 3


def test_degrades_gracefully_on_undecodable_file(tmp_path: Path) -> None:
    source = tmp_path / "broken.go"
    _ = source.write_bytes(b"\xff\xfe\x00 not utf-8 \x80")

    parsed = parse_go_file(source, "broken.go")

    assert parsed.parse_error is not None
    assert parsed.symbols == ()
    assert parsed.imports == ()
