from pathlib import Path
from textwrap import dedent

from codescent.engine.rules.structural_duplicates import (
    group_structural_duplicates,
    structural_duplicate_findings,
    structural_fingerprints,
)


def test_structural_fingerprint_normalizes_renamed_identifiers() -> None:
    first = _function_fingerprint(
        """
        def summarize_orders(orders):
            total = 0
            for order in orders:
                if order.active:
                    total += order.amount * 2
            return total
        """,
    )
    second = _function_fingerprint(
        """
        def build_invoice_lines(records):
            subtotal = 0
            for record in records:
                if record.enabled:
                    subtotal += record.price * 7
            return subtotal
        """,
    )

    assert first == second


def test_structural_fingerprint_preserves_operator_shape() -> None:
    multiplied = _function_fingerprint(
        """
        def summarize_orders(orders):
            total = 0
            for order in orders:
                if order.active:
                    total += order.amount * 2
            return total
        """,
    )
    added = _function_fingerprint(
        """
        def summarize_orders(orders):
            total = 0
            for order in orders:
                if order.active:
                    total += order.amount + 2
            return total
        """,
    )

    assert multiplied != added


def test_structural_fingerprint_normalizes_class_layout() -> None:
    first = _class_fingerprint(
        """
        class OrderExporter:
            def render(self, orders):
                rows = []
                for order in orders:
                    if order.active:
                        rows.append(order.name)
                return rows
        """,
    )
    second = _class_fingerprint(
        """
        class AccountWriter:
            def write(self, accounts):
                output = []
                for account in accounts:
                    if account.enabled:
                        output.append(account.label)
                return output
        """,
    )

    assert first == second


def test_structural_fingerprint_ignores_trivial_bodies() -> None:
    records = structural_fingerprints(
        dedent(
            """
            def passthrough(value):
                return value
            """,
        ),
    )

    assert records == ()


def test_group_structural_duplicates_filters_singletons(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write(
        repo / "src" / "alpha.py",
        """
        def summarize_orders(orders):
            total = 0
            for order in orders:
                if order.active:
                    total += order.amount * 2
            return total
        """,
    )
    _write(
        repo / "src" / "beta.py",
        """
        def build_invoice_lines(records):
            subtotal = 0
            for record in records:
                if record.enabled:
                    subtotal += record.price * 7
            return subtotal
        """,
    )
    _write(
        repo / "src" / "gamma.py",
        """
        def distinct_flow(records):
            output = []
            for record in records:
                if record.enabled:
                    output.append(record.price + 2)
            return output
        """,
    )
    _write(
        repo / "src" / "trivial_a.py",
        """
        def passthrough(value):
            return value
        """,
    )
    _write(
        repo / "src" / "trivial_b.py",
        """
        def identity(item):
            return item
        """,
    )

    clusters = group_structural_duplicates(repo)

    assert len(clusters) == 1
    assert clusters[0].member_count == 2
    assert [location.path for location in clusters[0].locations] == [
        "src/alpha.py",
        "src/beta.py",
    ]
    assert [location.name for location in clusters[0].locations] == [
        "summarize_orders",
        "build_invoice_lines",
    ]


def test_structural_duplicate_findings_are_bounded_and_anchored(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _write(
        repo / "src" / "alpha.py",
        """
        def summarize_orders(orders):
            total = 0
            for order in orders:
                if order.active:
                    total += order.amount * 2
            return total
        """,
    )
    _write(
        repo / "src" / "beta.py",
        """
        def build_invoice_lines(records):
            subtotal = 0
            for record in records:
                if record.enabled:
                    subtotal += record.price * 7
            return subtotal
        """,
    )

    findings = structural_duplicate_findings(repo)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.rule_id == "python.structural_near_duplicate"
    assert finding.file_path == "src/alpha.py"
    assert finding.symbol == "summarize_orders"
    assert finding.evidence["count"] == 2
    assert isinstance(finding.evidence["fingerprint"], str)
    assert finding.evidence["fingerprint"].startswith("sha256:")
    assert finding.evidence["locations"] == (
        "src/alpha.py:2-7:summarize_orders; src/beta.py:2-7:build_invoice_lines"
    )
    assert finding.suggested_action == (
        "Extract a shared helper or parameterize the duplicated logic."
    )


def test_structural_duplicate_findings_cap_location_evidence(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    for index in range(6):
        _write(
            repo / "src" / f"module_{index}.py",
            f"""
            def repeated_shape_{index}(items):
                total = 0
                for item in items:
                    if item.enabled:
                        total += item.value * {index + 2}
                return total
            """,
        )

    findings = structural_duplicate_findings(repo)

    assert len(findings) == 1
    assert findings[0].evidence["count"] == 6
    assert findings[0].evidence["locations"] == (
        "src/module_0.py:2-7:repeated_shape_0; "
        "src/module_1.py:2-7:repeated_shape_1; "
        "src/module_2.py:2-7:repeated_shape_2; "
        "src/module_3.py:2-7:repeated_shape_3; +2 more"
    )


def test_structural_findings_annotate_reachable_entry_point_members(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _write(
        repo / "src" / "alpha.py",
        """
        @app.command()
        def summarize_orders(orders):
            total = 0
            for order in orders:
                if order.active:
                    total += order.amount * 2
            return total
        """,
    )
    _write(
        repo / "src" / "beta.py",
        """
        def build_invoice_lines(records):
            subtotal = 0
            for record in records:
                if record.enabled:
                    subtotal += record.price * 7
            return subtotal
        """,
    )

    findings = structural_duplicate_findings(repo)

    assert len(findings) == 1
    finding = findings[0]
    # The decorated member is reachable, so the message flags it; the duplicate
    # is still reported (duplication is a smell regardless of reachability).
    assert "Reachable via entry points: summarize_orders." in finding.message


def test_structural_findings_omit_note_without_entry_point_members(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _write(
        repo / "src" / "alpha.py",
        """
        def summarize_orders(orders):
            total = 0
            for order in orders:
                if order.active:
                    total += order.amount * 2
            return total
        """,
    )
    _write(
        repo / "src" / "beta.py",
        """
        def build_invoice_lines(records):
            subtotal = 0
            for record in records:
                if record.enabled:
                    subtotal += record.price * 7
            return subtotal
        """,
    )

    findings = structural_duplicate_findings(repo)

    assert len(findings) == 1
    assert "Reachable via entry points" not in findings[0].message


def _function_fingerprint(source: str) -> str:
    records = structural_fingerprints(dedent(source))
    functions = [record for record in records if record.kind == "function"]
    assert len(functions) == 1
    return functions[0].fingerprint


def _class_fingerprint(source: str) -> str:
    records = structural_fingerprints(dedent(source))
    classes = [record for record in records if record.kind == "class"]
    assert len(classes) == 1
    return classes[0].fingerprint


def _write(path: Path, source: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(dedent(source))
