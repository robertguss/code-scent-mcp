from codescent.cli.admin import ReindexDebouncer


def test_debouncer_coalesces_burst_into_single_fire() -> None:
    debouncer = ReindexDebouncer(window_seconds=2.0)

    # A burst keeps growing the change set, so the window keeps restarting.
    assert debouncer.observe(("a.py",), now=0.0) is False
    assert debouncer.observe(("a.py", "b.py"), now=0.5) is False
    assert debouncer.observe(("a.py", "b.py"), now=1.0) is False  # stable, < window
    assert debouncer.observe(("a.py", "b.py"), now=2.5) is True  # stable >= window
    # Fires exactly once; the window resets after firing.
    assert debouncer.observe(("a.py", "b.py"), now=3.0) is False


def test_debouncer_resets_when_index_becomes_fresh() -> None:
    debouncer = ReindexDebouncer(window_seconds=1.0)

    assert debouncer.observe(("a.py",), now=0.0) is False
    # Empty set (index already fresh) clears any pending window.
    assert debouncer.observe((), now=0.5) is False
    # A later change restarts the window from scratch.
    assert debouncer.observe(("a.py",), now=5.0) is False
    assert debouncer.observe(("a.py",), now=6.0) is True
