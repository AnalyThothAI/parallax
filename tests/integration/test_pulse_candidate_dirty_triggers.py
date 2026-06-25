from __future__ import annotations

from dataclasses import replace

import pytest

from parallax.app.runtime.repository_session import repositories_for_connection
from parallax.domains.pulse_lab.repositories.pulse_trigger_dirty_target_repository import (
    PulseTriggerDirtyTargetRepository,
)
from parallax.domains.token_intel.interfaces import TOKEN_RADAR_DEFAULT_VENUE, TOKEN_RADAR_PROJECTION_VERSION
from parallax.domains.token_intel.repositories.token_radar_repository import TokenRadarRepository
from parallax.domains.token_intel.services.token_radar_projection import TokenRadarProjection
from tests.integration.test_token_radar_repository import _insert_pricefeed, _insert_token_intent, _valid_factor_row
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate


def test_token_radar_publish_enqueues_pulse_trigger_in_same_transaction(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        _insert_token_intent(conn, intent_id="intent-1", event_id="event-1")
        _insert_pricefeed(conn, "feed-1")

        repos = repositories_for_connection(
            conn,
            pulse_job_running_timeout_ms=300_000,
            notification_delivery_running_timeout_ms=300_000,
            notification_delivery_stale_running_terminalization_batch_size=100,
        )
        repos.token_radar.upsert_target_feature(
            projection_version=TOKEN_RADAR_PROJECTION_VERSION,
            window="1h",
            scope="all",
            row=_valid_factor_row(),
            computed_at_ms=1_777_999_990_000,
            commit=False,
        )
        result = TokenRadarProjection(repos=repos).refresh_rank_set(
            window="1h",
            scope="all",
            now_ms=1_778_000_000_000,
            limit=10,
        )

        trigger = PulseTriggerDirtyTargetRepository(conn).claim_due(
            now_ms=1_778_000_000_000,
            limit=10,
            lease_owner="test-pulse",
            lease_ms=60_000,
        )[0]
    finally:
        conn.close()

    assert result["status"] == "ready"
    assert trigger["target_type"] == "Asset"
    assert trigger["target_id"] == "asset-1"
    assert trigger["window"] == "1h"
    assert trigger["scope"] == "all"
    assert trigger["dirty_reason"] == "token_radar_entered"
    assert trigger["source_watermark_ms"] == 1_778_000_000_000
    assert trigger["attempt_count"] == 1


def test_token_radar_publish_rolls_back_pulse_trigger_enqueue_with_current_row(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        _insert_token_intent(conn, intent_id="intent-1", event_id="event-1")
        _insert_pricefeed(conn, "feed-1")
        repo = TokenRadarRepository(conn)

        def enqueue_then_fail(**kwargs):
            PulseTriggerDirtyTargetRepository(conn).enqueue_targets(
                [
                    {
                        "target_type": "Asset",
                        "target_id": "asset-1",
                        "window": kwargs["window"],
                        "scope": kwargs["scope"],
                        "payload_hash": "rollback-test",
                        "source_watermark_ms": kwargs["computed_at_ms"],
                    }
                ],
                reason="token_radar_entered",
                now_ms=kwargs["computed_at_ms"],
                commit=False,
            )
            raise RuntimeError("forced rollback")

        with pytest.raises(RuntimeError, match="forced rollback"), conn.transaction():
            repo.publish_current_generation(
                projection_version=TOKEN_RADAR_PROJECTION_VERSION,
                window="1h",
                scope="all",
                venue=TOKEN_RADAR_DEFAULT_VENUE,
                generation_id="gen-rollback",
                published_at_ms=1_778_000_000_000,
                source_frontier_ms=1_778_000_000_000,
                rows=[_valid_factor_row()],
                on_current_changes=enqueue_then_fail,
                commit=False,
            )

        counts = conn.execute(
            """
            SELECT
              (SELECT count(*) FROM token_radar_current_rows) AS current_count,
              (SELECT count(*) FROM pulse_trigger_dirty_targets) AS trigger_count
            """
        ).fetchone()
    finally:
        conn.close()

    assert counts["current_count"] == 0
    assert counts["trigger_count"] == 0


def test_token_radar_refresh_rolls_back_current_rows_when_pulse_enqueue_fails(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        _insert_token_intent(conn, intent_id="intent-1", event_id="event-1")
        _insert_pricefeed(conn, "feed-1")
        repos = replace(
            repositories_for_connection(
                conn,
                pulse_job_running_timeout_ms=300_000,
                notification_delivery_running_timeout_ms=300_000,
                notification_delivery_stale_running_terminalization_batch_size=100,
            ),
            pulse_trigger_dirty_targets=_FailingPulseTriggerDirtyTargets(conn),
        )
        repos.token_radar.upsert_target_feature(
            projection_version=TOKEN_RADAR_PROJECTION_VERSION,
            window="1h",
            scope="all",
            row=_valid_factor_row(),
            computed_at_ms=1_777_999_990_000,
            commit=False,
        )

        with pytest.raises(RuntimeError, match="forced pulse enqueue failure"):
            TokenRadarProjection(repos=repos).refresh_rank_set(
                window="1h",
                scope="all",
                now_ms=1_778_000_000_000,
                limit=10,
            )

        counts = conn.execute(
            """
            SELECT
              (SELECT count(*) FROM token_radar_current_rows) AS current_count,
              (SELECT count(*) FROM pulse_trigger_dirty_targets) AS trigger_count,
              (
                SELECT latest_attempt_status
                FROM token_radar_publication_state
                WHERE "window" = '1h' AND scope = 'all'
              ) AS status
            """
        ).fetchone()
    finally:
        conn.close()

    assert counts["current_count"] == 0
    assert counts["trigger_count"] == 0
    assert counts["status"] == "failed"


def test_pulse_trigger_old_claim_cannot_complete_or_error_newer_payload(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = PulseTriggerDirtyTargetRepository(conn)
        repo.enqueue_targets(
            [
                {
                    "target_type": "Asset",
                    "target_id": "asset-1",
                    "window": "1h",
                    "scope": "all",
                    "payload_hash": "payload-v1",
                    "source_watermark_ms": 100,
                    "priority": 50,
                }
            ],
            reason="token_radar_changed",
            now_ms=100,
        )
        old_claim = repo.claim_due(now_ms=100, limit=1, lease_owner="old-worker", lease_ms=60_000)[0]

        repo.enqueue_targets(
            [
                {
                    "target_type": "Asset",
                    "target_id": "asset-1",
                    "window": "1h",
                    "scope": "all",
                    "payload_hash": "payload-v2",
                    "source_watermark_ms": 200,
                    "priority": 40,
                }
            ],
            reason="token_radar_rank_changed",
            now_ms=200,
        )
        stale_done = repo.mark_done([old_claim], now_ms=201)
        stale_error = repo.mark_error(
            [old_claim],
            error="stale completion",
            max_attempts=3,
            worker_name="pulse_candidate",
            now_ms=202,
            retry_ms=10_000,
        )
        new_claim = repo.claim_due(now_ms=203, limit=1, lease_owner="new-worker", lease_ms=60_000)[0]
    finally:
        conn.close()

    assert stale_done == 0
    assert stale_error == 0
    assert new_claim["payload_hash"] == "payload-v2"
    assert new_claim["lease_owner"] == "new-worker"
    assert new_claim["attempt_count"] == 1
    assert new_claim["last_error"] is None
    assert new_claim["dirty_reason"] == "token_radar_rank_changed"


class _FailingPulseTriggerDirtyTargets:
    def __init__(self, conn):
        self._delegate = PulseTriggerDirtyTargetRepository(conn)

    def enqueue_targets(self, *args, **kwargs):
        self._delegate.enqueue_targets(*args, **kwargs)
        raise RuntimeError("forced pulse enqueue failure")
