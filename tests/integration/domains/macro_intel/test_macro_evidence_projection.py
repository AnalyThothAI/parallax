from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from parallax.domains.macro_intel._constants import MACRO_EVIDENCE_PROJECTION_VERSION
from parallax.domains.macro_intel.runtime.macro_view_projection_worker import (
    MacroViewProjectionWorker,
)
from parallax.platform.config.settings import MacroViewProjectionWorkerSettings
from tests.postgres_test_utils import (
    connect_postgres_test,
    repository_session_for_connection,
)
from tests.postgres_test_utils import reset_postgres_schema as migrate

NOW_MS = 1_774_483_200_000  # 2026-03-26T00:00:00Z


def test_non_empty_projection_replay_is_atomic_and_zero_write(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        _seed_observation(
            conn,
            concept_key="asset:spy",
            series_key="test:SPY",
            observed_at=date(2026, 3, 20),
            value="582.40",
            unit="price",
        )
        _seed_observation(
            conn,
            concept_key="rates:dgs10",
            series_key="test:DGS10",
            observed_at=date(2026, 3, 20),
            value="4.25",
            unit="percent",
        )
        _enqueue_current(conn, now_ms=NOW_MS)
        worker = _worker(conn)

        first = worker.run_once_sync(now_ms=NOW_MS)
        first_row = conn.execute(
            "SELECT *, xmin::text AS row_version FROM macro_view_snapshots WHERE snapshot_key = 'current'"
        ).fetchone()
        queue_after_first = _queue_count(conn)
        conn.commit()

        _enqueue_current(conn, now_ms=NOW_MS + 60_000)
        second = worker.run_once_sync(now_ms=NOW_MS + 60_000)
        second_row = conn.execute(
            "SELECT *, xmin::text AS row_version FROM macro_view_snapshots WHERE snapshot_key = 'current'"
        ).fetchone()
        queue_after_second = _queue_count(conn)
        conn.commit()
    finally:
        conn.close()

    assert first.processed == 1
    assert first.failed == 0
    assert first.notes["snapshot_rows_written"] == 1
    assert first_row is not None
    assert first_row["projection_version"] == MACRO_EVIDENCE_PROJECTION_VERSION
    assert first_row["fact_watermark"] == date(2026, 3, 20)
    assert first_row["market_cutoff"] == date(2026, 3, 25)
    assert first_row["computed_at_ms"] == NOW_MS
    assert {
        first_row["overview_json"]["page_id"],
        first_row["cross_asset_json"]["page_id"],
        first_row["rates_inflation_json"]["page_id"],
        first_row["growth_labor_json"]["page_id"],
        first_row["liquidity_funding_json"]["page_id"],
        first_row["credit_json"]["page_id"],
    } == {
        "overview",
        "cross_asset",
        "rates_inflation",
        "growth_labor",
        "liquidity_funding",
        "credit",
    }
    assert queue_after_first == 0

    assert second.processed == 1
    assert second.failed == 0
    assert second.notes["projected_rows_written"] == 0
    assert second.notes["snapshot_rows_written"] == 0
    assert second.notes["rows_written"] == 0
    assert second_row is not None
    assert second_row["row_version"] == first_row["row_version"]
    assert second_row["computed_at_ms"] == NOW_MS
    assert second_row["payload_hash"] == first_row["payload_hash"]
    assert queue_after_second == 0


def test_snapshot_failure_rolls_back_series_and_does_not_ack_dirty_target(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        _seed_observation(
            conn,
            concept_key="rates:dgs10",
            series_key="test:DGS10",
            observed_at=date(2026, 3, 20),
            value="4.25",
            unit="percent",
        )
        _enqueue_current(conn, now_ms=NOW_MS)
        conn.execute(
            """
            ALTER TABLE macro_view_snapshots
            ADD CONSTRAINT test_reject_macro_snapshot CHECK (payload_hash = 'rejected-by-test')
            """
        )
        conn.commit()
        worker = _worker(conn)

        failed = worker.run_once_sync(now_ms=NOW_MS)
        snapshot_count_after_failure = _table_count(conn, "macro_view_snapshots")
        series_count_after_failure = _table_count(conn, "macro_observation_series_rows")
        failed_target = conn.execute(
            """
            SELECT attempt_count, leased_until_ms, lease_owner, last_error
            FROM macro_projection_dirty_targets
            WHERE projection_name = 'macro_evidence'
              AND projection_version = %s
            """,
            (MACRO_EVIDENCE_PROJECTION_VERSION,),
        ).fetchone()
        conn.commit()

        conn.execute("ALTER TABLE macro_view_snapshots DROP CONSTRAINT test_reject_macro_snapshot")
        conn.commit()
        repaired = worker.run_once_sync(now_ms=NOW_MS + 2)
        snapshot_count_after_repair = _table_count(conn, "macro_view_snapshots")
        queue_after_repair = _queue_count(conn)
        conn.commit()
    finally:
        conn.close()

    assert failed.failed == 1
    assert failed.processed == 0
    assert snapshot_count_after_failure == 0
    assert series_count_after_failure == 0
    assert failed_target is not None
    assert failed_target["attempt_count"] == 1
    assert failed_target["leased_until_ms"] is None
    assert failed_target["lease_owner"] is None
    assert "test_reject_macro_snapshot" in failed_target["last_error"]

    assert repaired.processed == 1
    assert repaired.failed == 0
    assert snapshot_count_after_repair == 1
    assert queue_after_repair == 0


def test_clock_recheck_publishes_stale_transition_without_new_dirty_target(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        _seed_observation(
            conn,
            concept_key="vol:vix",
            series_key="test:VIXCLS",
            observed_at=date(2026, 3, 20),
            value="18.2",
            unit="index",
        )
        _enqueue_current(conn, now_ms=NOW_MS)
        worker = _worker(conn)

        first = worker.run_once_sync(now_ms=NOW_MS)
        first_row = conn.execute(
            "SELECT cross_asset_json, xmin::text AS row_version "
            "FROM macro_view_snapshots WHERE snapshot_key = 'current'"
        ).fetchone()
        conn.commit()

        later = worker.run_once_sync(now_ms=NOW_MS + 3 * 24 * 60 * 60 * 1000)
        later_row = conn.execute(
            "SELECT cross_asset_json, xmin::text AS row_version "
            "FROM macro_view_snapshots WHERE snapshot_key = 'current'"
        ).fetchone()
        queue_after_later = _queue_count(conn)
        conn.commit()
    finally:
        conn.close()

    assert first.processed == 1
    assert later.processed == 1
    assert later.notes["claimed"] == 0
    assert later.notes["recheck_reason"] == "freshness_clock"
    assert first_row is not None and later_row is not None
    first_vix = next(item for item in first_row["cross_asset_json"]["volatility"] if item["concept_key"] == "vol:vix")
    later_vix = next(item for item in later_row["cross_asset_json"]["volatility"] if item["concept_key"] == "vol:vix")
    assert first_vix["status"] == "available"
    assert later_vix["status"] == "stale"
    assert later_row["row_version"] != first_row["row_version"]
    assert queue_after_later == 0


def test_current_rebuild_prunes_retired_series_and_future_retired_dirty_targets_are_ignored(tmp_path) -> None:
    retired_concept = "retired:macro_concept"
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        _seed_observation(
            conn,
            concept_key="rates:dgs10",
            series_key="test:DGS10",
            observed_at=date(2026, 3, 20),
            value="4.25",
            unit="percent",
        )
        _enqueue_current(conn, now_ms=NOW_MS)
        worker = _worker(conn)
        initial = worker.run_once_sync(now_ms=NOW_MS)
        conn.execute(
            """
            INSERT INTO macro_observation_series_rows(
              projection_version, concept_key, observed_at, value_numeric,
              source_name, series_key, unit, frequency, data_quality,
              event_metadata_json
            ) VALUES (%s, %s, %s, 1, 'retired', 'retired:series',
                      'index', 'daily', 'ok', '{}'::jsonb)
            """,
            (MACRO_EVIDENCE_PROJECTION_VERSION, retired_concept, date(2026, 3, 20)),
        )
        conn.commit()

        _enqueue_current(conn, now_ms=NOW_MS + 60_000)
        pruned = worker.run_once_sync(now_ms=NOW_MS + 60_000)
        retired_rows_after_prune = _series_concept_count(conn, retired_concept)
        conn.commit()

        _seed_observation(
            conn,
            concept_key=retired_concept,
            series_key="retired:series",
            observed_at=date(2026, 3, 21),
            value="2",
            unit="index",
        )
        _enqueue_concept_change(conn, concept_key=retired_concept, now_ms=NOW_MS + 120_000)
        ignored = worker.run_once_sync(now_ms=NOW_MS + 120_000)
        retired_rows_after_dirty_target = _series_concept_count(conn, retired_concept)
        queue_after_ignored = _queue_count(conn)
        material_fact_count = conn.execute(
            "SELECT COUNT(*) AS count FROM macro_observations WHERE concept_key = %s",
            (retired_concept,),
        ).fetchone()["count"]
        conn.commit()
    finally:
        conn.close()

    assert initial.processed == 1
    assert initial.failed == 0
    assert pruned.processed == 1
    assert pruned.failed == 0
    assert pruned.notes["projected_rows_written"] == 1
    assert pruned.notes["snapshot_rows_written"] == 0
    assert retired_rows_after_prune == 0
    assert ignored.processed == 1
    assert ignored.failed == 0
    assert ignored.notes["projected_rows_written"] == 0
    assert ignored.notes["snapshot_rows_written"] == 0
    assert retired_rows_after_dirty_target == 0
    assert queue_after_ignored == 0
    assert material_fact_count == 1


def _seed_observation(
    conn,
    *,
    concept_key: str,
    series_key: str,
    observed_at: date,
    value: str,
    unit: str,
) -> None:
    with repository_session_for_connection(conn) as repos, repos.transaction():
        outcome = repos.macro_intel.upsert_observation(
            {
                "source_name": "integration-test",
                "concept_key": concept_key,
                "series_key": series_key,
                "source_priority": 100,
                "observed_at": observed_at,
                "value_numeric": Decimal(value),
                "unit": unit,
                "frequency": "daily",
                "data_quality": "ok",
                "source_ts": observed_at.isoformat(),
                "raw_payload": {"source": "integration-test"},
                "ingested_at_ms": NOW_MS,
            }
        )
    assert outcome["status"] == "inserted"


def _enqueue_current(conn, *, now_ms: int) -> None:
    with repository_session_for_connection(conn) as repos, repos.transaction():
        repos.macro_intel.enqueue_macro_projection_dirty_target(
            projection_name="macro_evidence",
            projection_version=MACRO_EVIDENCE_PROJECTION_VERSION,
            now_ms=now_ms,
            reason="integration_replay",
        )


def _enqueue_concept_change(conn, *, concept_key: str, now_ms: int) -> None:
    with repository_session_for_connection(conn) as repos, repos.transaction():
        enqueued = repos.macro_intel.enqueue_macro_projection_dirty_targets_for_changes(
            changed_observations=[
                {
                    "concept_key": concept_key,
                    "observed_at": date(2026, 3, 21),
                }
            ],
            projection_name="macro_evidence",
            projection_version=MACRO_EVIDENCE_PROJECTION_VERSION,
            now_ms=now_ms,
            reason="integration_retired_concept_change",
        )
    assert enqueued == 1


def _series_concept_count(conn, concept_key: str) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM macro_observation_series_rows
        WHERE projection_version = %s AND concept_key = %s
        """,
        (MACRO_EVIDENCE_PROJECTION_VERSION, concept_key),
    ).fetchone()
    return int(row["count"])


def _queue_count(conn) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM macro_projection_dirty_targets
        WHERE projection_name = 'macro_evidence'
          AND projection_version = %s
        """,
        (MACRO_EVIDENCE_PROJECTION_VERSION,),
    ).fetchone()
    return int(row["count"])


def _table_count(conn, table_name: str) -> int:
    allowed = {"macro_view_snapshots", "macro_observation_series_rows"}
    if table_name not in allowed:
        raise ValueError(f"unsupported integration count table: {table_name}")
    row = conn.execute(f"SELECT COUNT(*) AS count FROM {table_name}").fetchone()
    return int(row["count"])


def _worker(conn) -> MacroViewProjectionWorker:
    return MacroViewProjectionWorker(
        settings=MacroViewProjectionWorkerSettings(
            enabled=True,
            interval_seconds=0,
            batch_size=250,
            statement_timeout_seconds=30,
            lease_ms=300_000,
            retry_ms=1,
            max_attempts=3,
            lookback_days=1095,
            limit_per_series=800,
        ),
        db=_SingleConnectionDB(conn),
        telemetry=SimpleNamespace(),
        clock_ms=lambda: NOW_MS,
    )


class _SingleConnectionDB:
    def __init__(self, conn) -> None:
        self.conn = conn

    def worker_session(
        self,
        _name: str,
        *,
        statement_timeout_seconds: float,
    ) -> AbstractContextManager:
        assert statement_timeout_seconds == 30
        return repository_session_for_connection(self.conn)
