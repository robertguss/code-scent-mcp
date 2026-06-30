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


def test_extract_pattern_skips_value_taking_flags() -> None:
    # A value-consuming flag's argument must not be mistaken for the pattern.
    assert extract_pattern("Bash", {"command": "rg -t python load_config"}) == (
        "load_config"
    )
    assert extract_pattern("Bash", {"command": "rg --type python load_config"}) == (
        "load_config"
    )
    assert extract_pattern("Bash", {"command": "rg -g glob load_config"}) == (
        "load_config"
    )


def test_extract_pattern_file_flag_is_not_the_pattern() -> None:
    # -f/--file read patterns FROM a file; the filename is not a search term.
    assert extract_pattern("Bash", {"command": "grep -f patterns.txt"}) is None
    assert extract_pattern("Bash", {"command": "grep --file=patterns.txt"}) is None


def test_usable_pattern_output_is_identifier_charset() -> None:
    # The sole sanitization point: output is always plain identifier characters,
    # so no shell/regex metacharacter can reach the search sink (R22).
    allowed = set(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_",
    )
    for raw in ('"$(rm -rf /)"', "foo;bar|baz", "a.*b", "load_config", "--", "$x"):
        result = usable_pattern(raw)
        assert result is None or set(result) <= allowed
