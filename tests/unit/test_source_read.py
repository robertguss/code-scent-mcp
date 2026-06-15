from pathlib import Path

from codescent.engine.source_read import (
    read_source_bytes,
    read_source_lines,
    read_source_text,
)


def test_source_read_helpers_return_normal_content(tmp_path: Path) -> None:
    source = tmp_path / "small.py"
    _ = source.write_text("first\nsecond\n")

    byte_result = read_source_bytes(source)
    text_result = read_source_text(source)
    line_result = read_source_lines(source)

    assert byte_result.content == b"first\nsecond\n"
    assert byte_result.oversized is False
    assert text_result.text == "first\nsecond\n"
    assert text_result.oversized is False
    assert line_result.lines == ("first", "second")
    assert line_result.oversized is False


def test_source_read_helpers_mark_oversized_without_materializing(
    tmp_path: Path,
) -> None:
    source = tmp_path / "huge.py"
    _ = source.write_text("abcdef")

    byte_result = read_source_bytes(source, max_bytes=3)
    text_result = read_source_text(source, max_bytes=3)
    line_result = read_source_lines(source, max_bytes=3)

    assert byte_result.content is None
    assert byte_result.size_bytes == 6
    assert byte_result.oversized is True
    assert text_result.text is None
    assert text_result.size_bytes == 6
    assert text_result.oversized is True
    assert line_result.lines is None
    assert line_result.size_bytes == 6
    assert line_result.oversized is True
