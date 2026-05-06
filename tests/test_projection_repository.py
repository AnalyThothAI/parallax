from __future__ import annotations

from gmgn_twitter_intel.storage.projection_repository import ProjectionRepository
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate


def test_projection_offsets_runs_and_dirty_ranges_round_trip(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = ProjectionRepository(conn)

        run = repo.start_run(
            projection_name="token-social-buckets",
            projection_version="token-social-buckets-v1",
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
            dirty_ranges_written=1,
        )
        repo.advance_offset(
            projection_name="token-social-buckets",
            projection_version="token-social-buckets-v1",
            source_table="event_token_attributions",
            source_max_received_at_ms=2_000,
            source_max_id="attr-7",
            last_run_id=run["run_id"],
            lag_ms=25,
            status="ready",
        )
        dirty_id = repo.enqueue_dirty_range(
            projection_name="token-flow-window-snapshots",
            projection_version="token-flow-window-snapshots-v1",
            entity_type="token",
            entity_key="token:eth:0xpepe",
            window="5m",
            scope="all",
            start_ms=1_500,
            end_ms=1_800,
            reason="source_attribution",
        )
        claimed = repo.claim_dirty_ranges(
            projection_name="token-flow-window-snapshots",
            projection_version="token-flow-window-snapshots-v1",
            limit=5,
        )
        offset = repo.get_offset("token-social-buckets")
        runs = repo.list_runs(projection_name="token-social-buckets")
    finally:
        conn.close()

    assert offset["source_max_id"] == "attr-7"
    assert offset["lag_ms"] == 25
    assert runs[0]["rows_written"] == 3
    assert claimed[0]["dirty_id"] == dirty_id
    assert claimed[0]["status"] == "running"


def test_projection_dirty_range_enqueue_is_idempotent(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = ProjectionRepository(conn)

        first_id = repo.enqueue_dirty_range(
            projection_name="token-social-buckets",
            projection_version="token-social-buckets-v1",
            entity_type="token",
            entity_key="token:eth:0xpepe",
            window=None,
            scope="all",
            start_ms=1_000,
            end_ms=2_000,
            reason="backfill",
        )
        second_id = repo.enqueue_dirty_range(
            projection_name="token-social-buckets",
            projection_version="token-social-buckets-v1",
            entity_type="token",
            entity_key="token:eth:0xpepe",
            window=None,
            scope="all",
            start_ms=1_000,
            end_ms=2_000,
            reason="backfill",
        )
        ranges = repo.list_dirty_ranges(projection_name="token-social-buckets", limit=10)
    finally:
        conn.close()

    assert second_id == first_id
    assert [item["dirty_id"] for item in ranges] == [first_id]
