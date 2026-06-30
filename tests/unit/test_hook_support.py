"""U2: search-command detection, pattern extraction, and the usability gate.

Pure, side-effect-free string logic. The Bash path inspects the command string
only and never executes or evaluates it (R22).
"""

from codescent.cli.hook_support import (
    detect_search_command,
    extract_pattern,
    usable_pattern,
)


def test_detect_search_command_true_for_search_binaries() -> None:
    assert detect_search_command("grep -n foo src/")
    assert detect_search_command("rg --hidden bar")
    assert detect_search_command("ag baz")
    assert detect_search_command("ripgrep qux")
    assert detect_search_command("  grep foo")  # leading whitespace
    assert detect_search_command("/usr/bin/grep foo")  # absolute path


def test_detect_search_command_false_for_non_search() -> None:
    assert not detect_search_command("ls -la")
    assert not detect_search_command("cat file.txt")
    assert not detect_search_command("egrep foo")  # out of the R2 set
    assert not detect_search_command("")


def test_usable_pattern_accepts_identifiers() -> None:
    assert usable_pattern("parseConfig") == "parseConfig"
    assert usable_pattern("handle_request") == "handle_request"
    assert usable_pattern('"parseConfig"') == "parseConfig"


def test_usable_pattern_rejects_noise() -> None:
    assert usable_pattern(".*") is None
    assert usable_pattern(r"\d+") is None
    assert usable_pattern("a") is None
    assert usable_pattern("()") is None
    assert usable_pattern("--") is None
    assert usable_pattern("") is None
    assert usable_pattern(None) is None


def test_usable_pattern_extracts_identifier_from_mixed() -> None:
    assert usable_pattern("foo.*bar") == "foo"


def test_extract_pattern_from_structured_tools() -> None:
    assert extract_pattern("Grep", {"pattern": "parseConfig"}) == "parseConfig"
    assert extract_pattern("Glob", {"pattern": "buildPlan"}) == "buildPlan"
    assert extract_pattern("Read", {"file_path": "x.py"}) is None


def test_extract_pattern_from_bash_positional() -> None:
    assert extract_pattern("Bash", {"command": 'grep -rn "parseConfig" src/'}) == (
        "parseConfig"
    )
    assert extract_pattern("Bash", {"command": "rg buildPlan"}) == "buildPlan"


def test_extract_pattern_handles_e_flag() -> None:
    # -e supplies the pattern; it must not be skipped as an ordinary flag.
    assert extract_pattern("Bash", {"command": "grep -e foo src/"}) == "foo"
    assert extract_pattern("Bash", {"command": "rg --regexp=bar"}) == "bar"


def test_extract_pattern_no_shell_execution() -> None:
    # Covers R22: metacharacters are parsed as literal text, never evaluated.
    command = 'grep "$(rm -rf /)" .'
    result = extract_pattern("Bash", {"command": command})
    # Whatever token comes back is inert string data — the point is no crash and
    # no substitution. The captured token still contains the literal text.
    assert result is None or "rm" in result or "$" in result


def test_extract_pattern_edge_cases() -> None:
    assert extract_pattern("Bash", {"command": ""}) is None
    assert extract_pattern("Bash", {"command": "grep"}) is None  # only the binary
    assert extract_pattern("Bash", {"command": "grep -i -n"}) is None  # only flags
    assert extract_pattern("Bash", {}) is None
