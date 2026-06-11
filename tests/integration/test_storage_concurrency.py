import threading
from pathlib import Path

from codescent.storage import RepositoryStorage, initialize_storage


def test_concurrent_reader_waits_for_writer_without_corruption(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    state = initialize_storage(repo)
    storage = RepositoryStorage(state)
    reader_started = threading.Event()
    reader_finished = threading.Event()
    read_counts: list[int] = []

    def read_after_writer() -> None:
        reader_started.set()
        with RepositoryStorage(state).read_connection() as connection:
            rows: list[tuple[int]] = connection.execute(
                "select count(*) from telemetry",
            ).fetchall()
            read_counts.append(rows[0][0])
        reader_finished.set()

    with storage.write_transaction() as connection:
        _ = connection.execute(
            """
            insert into telemetry (event_name, created_at, payload_json)
            values ('writer_started', 'now', '{}')
            """,
        )
        reader = threading.Thread(target=read_after_writer)
        reader.start()
        assert reader_started.wait(timeout=1.0)
        assert not reader_finished.wait(timeout=0.1)

    reader.join(timeout=1.0)

    assert not reader.is_alive()
    assert read_counts == [1]
