from __future__ import annotations

from parallax.domains.token_intel.repositories.projection_repository import ProjectionRepository
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate


def test_projection_offsets_and_runs_round_trip(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = ProjectionRepository(conn)

        run = repo.start_run(
            projection_name="token-radar",
            projection_version="token-radar-current-test",
            mode="incremental",
            source_start_ms=1_000,
            source_end_ms=2_000,
            run_id="run-1",
        )
        repo.finish_run(
            run_id=run["run_id"],
            status="done",
            rows_read=7,
            rows_written=3,
        )
        repo.advance_offset(
            projection_name="token-radar",
            projection_version="token-radar-current-test",
            source_table="token_intent_resolutions",
            source_max_received_at_ms=2_000,
            source_max_id="token-resolution-7",
            last_run_id=run["run_id"],
            lag_ms=25,
            status="ready",
        )
        offset = repo.get_offset("token-radar")
        runs = repo.list_runs(projection_name="token-radar", limit=20)
    finally:
        conn.close()

    assert offset["source_max_id"] == "token-resolution-7"
    assert offset["lag_ms"] == 25
    assert runs[0]["rows_written"] == 3


def test_mark_stale_running_runs_marks_abandoned_without_commit():
    conn = FakeProjectionConn(rowcount=2)

    count = ProjectionRepository(conn).mark_stale_running_runs(
        projection_name="token-radar",
        projection_version="token-radar-v5-auditable",
        stale_before_ms=1_000,
        finished_at_ms=2_000,
        commit=False,
    )

    assert count == 2
    assert "SET status = 'abandoned'" in conn.sql
    assert "error = 'stale_running_timeout'" in conn.sql
    assert conn.params == (2_000, "token-radar", "token-radar-v5-auditable", 1_000)
    assert conn.commits == 0


def test_start_run_generates_unique_ids_when_clock_is_same(monkeypatch):
    conn = FakeStartRunConn()
    monkeypatch.setattr(
        "parallax.domains.token_intel.repositories.projection_repository._now_ms",
        lambda: 2_000,
    )
    repo = ProjectionRepository(conn)

    first = repo.start_run(
        projection_name="token-radar",
        projection_version="token-radar-v5-auditable",
        mode="rebuild",
        source_start_ms=1_000,
        source_end_ms=2_000,
        commit=False,
    )
    second = repo.start_run(
        projection_name="token-radar",
        projection_version="token-radar-v5-auditable",
        mode="rebuild",
        source_start_ms=1_000,
        source_end_ms=2_000,
        commit=False,
    )

    assert first["run_id"] != second["run_id"]
    assert first["started_at_ms"] == 2_000
    assert second["started_at_ms"] == 2_000


class FakeProjectionConn:
    def __init__(self, *, rowcount: int):
        self.rowcount = rowcount
        self.sql = ""
        self.params = ()
        self.commits = 0

    def execute(self, sql, params=None):
        self.sql = str(sql)
        self.params = params or ()
        return self

    def commit(self):
        self.commits += 1


class FakeStartRunConn:
    def __init__(self):
        self.rows: dict[str, dict[str, object]] = {}
        self.selected_run_id = ""
        self.rowcount = 0

    def execute(self, sql, params=None):
        sql_text = str(sql)
        params = params or ()
        if "INSERT INTO projection_runs" in sql_text:
            run_id = str(params[0])
            if run_id in self.rows:
                raise AssertionError(f"duplicate run_id {run_id}")
            self.rows[run_id] = {
                "run_id": run_id,
                "projection_name": params[1],
                "projection_version": params[2],
                "mode": params[3],
                "status": "running",
                "source_start_ms": params[4],
                "source_end_ms": params[5],
                "rows_read": 0,
                "rows_written": 0,
                "started_at_ms": params[6],
            }
            self.selected_run_id = run_id
            self.rowcount = 1
        elif "SELECT * FROM projection_runs" in sql_text:
            self.selected_run_id = str(params[0])
            self.rowcount = 1 if self.selected_run_id in self.rows else 0
        return self

    def fetchone(self):
        return self.rows.get(self.selected_run_id)

    def commit(self):
        pass
