from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest

from parallax.app.runtime.repository_session import repositories_for_connection
from parallax.domains.narrative_intel._constants import NARRATIVE_SCHEMA_VERSION
from parallax.domains.narrative_intel.repositories.narrative_admission_dirty_target_repository import (
    NarrativeAdmissionDirtyTargetRepository,
)
from parallax.domains.token_intel.interfaces import TOKEN_RADAR_PROJECTION_VERSION
from parallax.domains.token_intel.services.token_radar_projection import TokenRadarProjection
from tests.integration.test_narrative_repository import (
    _insert_intent,
    _insert_legacy_digest,
    _insert_legacy_semantic,
    _insert_radar_publication_state,
    _insert_radar_row,
    make_event,
    open_repo,
)
from tests.integration.test_token_radar_repository import _insert_pricefeed, _insert_token_intent, _valid_factor_row
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate


def test_token_radar_publish_enqueues_narrative_admission_in_same_transaction(tmp_path) -> None:
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
        target_feature_row = _valid_factor_row()
        target_feature_snapshot = deepcopy(target_feature_row["factor_snapshot_json"])
        target_feature_snapshot["subject"] = {
            **target_feature_snapshot["subject"],
            "chain_id": "solana",
            "address": "asset-unit-address",
        }
        target_feature_row["factor_snapshot_json"] = target_feature_snapshot
        repos.token_radar.upsert_target_feature(
            projection_version=TOKEN_RADAR_PROJECTION_VERSION,
            window="1h",
            scope="all",
            row=target_feature_row,
            computed_at_ms=1_777_999_990_000,
            commit=False,
        )
        result = TokenRadarProjection(repos=repos).refresh_rank_set(
            window="1h",
            scope="all",
            now_ms=1_778_000_000_000,
            limit=10,
        )

        target = NarrativeAdmissionDirtyTargetRepository(conn).claim_due(
            now_ms=1_778_000_000_000,
            limit=10,
            lease_owner="test-narrative",
            lease_ms=60_000,
        )[0]
        digest_count = conn.execute("SELECT count(*) AS count FROM discussion_digest_dirty_targets").fetchone()
    finally:
        conn.close()

    assert result["status"] == "ready"
    assert target["target_type"] == "Asset"
    assert target["target_id"] == "asset-1"
    assert target["window"] == "1h"
    assert target["scope"] == "all"
    assert target["projection_version"] == TOKEN_RADAR_PROJECTION_VERSION
    assert target["schema_version"] == NARRATIVE_SCHEMA_VERSION
    assert target["dirty_reason"] == "token_radar_entered"
    assert target["source_watermark_ms"] == 1_778_000_000_000
    assert target["attempt_count"] == 1
    assert digest_count["count"] == 0


def test_token_radar_refresh_rolls_back_current_rows_when_narrative_enqueue_fails(tmp_path) -> None:
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
        repos = replace(repos, narrative_admission_dirty_targets=_FailingNarrativeAdmissionDirtyTargets(conn))
        repos.token_radar.upsert_target_feature(
            projection_version=TOKEN_RADAR_PROJECTION_VERSION,
            window="1h",
            scope="all",
            row=_valid_factor_row(),
            computed_at_ms=1_777_999_990_000,
            commit=False,
        )

        with pytest.raises(RuntimeError, match="forced narrative enqueue failure"):
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
              (SELECT count(*) FROM pulse_trigger_dirty_targets) AS pulse_count,
              (SELECT count(*) FROM narrative_admission_dirty_targets) AS narrative_count,
              (SELECT count(*) FROM discussion_digest_dirty_targets) AS digest_count
            """
        ).fetchone()
    finally:
        conn.close()

    assert counts["current_count"] == 0
    assert counts["pulse_count"] == 0
    assert counts["narrative_count"] == 0
    assert counts["digest_count"] == 0


class _FailingNarrativeAdmissionDirtyTargets:
    def __init__(self, conn):
        self._delegate = NarrativeAdmissionDirtyTargetRepository(conn)

    def enqueue_targets(self, *args, **kwargs):
        self._delegate.enqueue_targets(*args, **kwargs)
        raise RuntimeError("forced narrative enqueue failure")


def test_load_radar_admission_target_uses_exact_target_and_latest_ready_publication_state(tmp_path) -> None:
    conn, evidence, repo = open_repo(tmp_path)
    try:
        for event_id in ["event-target", "event-other"]:
            assert evidence.insert_event(make_event(event_id), is_watched=True) is True
            _insert_intent(conn, intent_id=f"intent-{event_id}", event_id=event_id, observed_at_ms=1_000)
        _insert_radar_publication_state(
            conn,
            window="24h",
            scope="all",
            projection_version=TOKEN_RADAR_PROJECTION_VERSION,
            computed_at_ms=1_000,
        )
        _insert_radar_row(
            conn,
            row_id="radar-target",
            event_id="event-target",
            intent_id="intent-event-target",
            target_id="asset:target",
            rank=3,
            computed_at_ms=1_000,
        )
        _insert_radar_row(
            conn,
            row_id="radar-other",
            event_id="event-other",
            intent_id="intent-event-other",
            target_id="asset:other",
            rank=1,
            computed_at_ms=1_000,
        )
        conn.execute(
            """
            UPDATE token_radar_publication_state
            SET current_published_at_ms = 2_000,
                latest_attempt_started_at_ms = 2_000,
                latest_attempt_finished_at_ms = 2_000,
                updated_at_ms = 2_000
            WHERE projection_version = %s
              AND "window" = '24h'
              AND scope = 'all'
            """,
            (TOKEN_RADAR_PROJECTION_VERSION,),
        )
        conn.commit()

        context = repo.load_radar_admission_target(
            target_type="Asset",
            target_id="asset:target",
            window="24h",
            scope="all",
            projection_version=TOKEN_RADAR_PROJECTION_VERSION,
            schema_version=NARRATIVE_SCHEMA_VERSION,
        )
    finally:
        conn.close()

    assert context["radar_row"]["target_id"] == "asset:target"
    assert context["radar_row"]["rank"] == 3
    assert context["radar_row"]["computed_at_ms"] == 2_000
    assert context["radar_row"]["row_computed_at_ms"] == 1_000
    assert context["existing_admission"] is None


def test_stale_admission_target_only_removes_claimed_target_window_scope(tmp_path) -> None:
    conn, evidence, repo = open_repo(tmp_path)
    try:
        for event_id in ["event-exited", "event-other"]:
            assert evidence.insert_event(make_event(event_id), is_watched=True) is True
        repo.upsert_admissions(
            [
                {
                    "target_type": "chain_token",
                    "target_id": "solana:Exited",
                    "window": "1h",
                    "scope": "matched",
                    "schema_version": NARRATIVE_SCHEMA_VERSION,
                    "source_event_ids": ["event-exited"],
                    "source_max_received_at_ms": 2_000,
                    "source_event_count": 1,
                    "independent_author_count": 1,
                },
                {
                    "target_type": "chain_token",
                    "target_id": "solana:Other",
                    "window": "1h",
                    "scope": "matched",
                    "schema_version": NARRATIVE_SCHEMA_VERSION,
                    "source_event_ids": ["event-other"],
                    "source_max_received_at_ms": 2_000,
                    "source_event_count": 1,
                    "independent_author_count": 1,
                },
            ],
            now_ms=2_000,
        )
        _insert_legacy_semantic(
            conn,
            event_id="event-exited",
            target_id="solana:Exited",
            status="labeled",
            computed_at_ms=2_100,
        )
        _insert_legacy_semantic(
            conn,
            event_id="event-other",
            target_id="solana:Other",
            status="labeled",
            computed_at_ms=2_100,
        )
        for target_id, event_id in [("solana:Exited", "event-exited"), ("solana:Other", "event-other")]:
            source_fingerprint = conn.execute(
                """
                SELECT source_fingerprint
                FROM narrative_admissions
                WHERE target_id = %s
                """,
                (target_id,),
            ).fetchone()["source_fingerprint"]
            _insert_legacy_digest(
                conn,
                digest_id=f"digest:{target_id}",
                target_id=target_id,
                window="1h",
                scope="matched",
                source_event_ids=[event_id],
                source_fingerprint=source_fingerprint,
                headline=f"Ready digest {target_id}",
                computed_at_ms=2_200,
            )

        result = repo.stale_admission_target(
            target_type="chain_token",
            target_id="solana:Exited",
            window="1h",
            scope="matched",
            schema_version=NARRATIVE_SCHEMA_VERSION,
            now_ms=3_000,
        )
        remaining_admissions = {
            row["target_id"] for row in conn.execute("SELECT target_id FROM narrative_admissions").fetchall()
        }
        remaining_digests = {
            row["target_id"] for row in conn.execute("SELECT target_id FROM token_discussion_digests").fetchall()
        }
        remaining_semantics = {
            row["target_id"] for row in conn.execute("SELECT target_id FROM token_mention_semantics").fetchall()
        }
        current = repo.current_digests_for_targets(
            [{"target_type": "chain_token", "target_id": "solana:Exited"}],
            window="1h",
            scope="matched",
            schema_version=NARRATIVE_SCHEMA_VERSION,
        )
    finally:
        conn.close()

    assert result == {"staled_admissions": 1, "staled_digests": 0, "staled_semantics": 0}
    assert remaining_admissions == {"solana:Other"}
    assert remaining_digests == {"solana:Exited", "solana:Other"}
    assert remaining_semantics == {"solana:Exited", "solana:Other"}
    assert current[("chain_token", "solana:Exited")]["currentness"]["display_status"] == "out_of_frontier"
