from gmgn_twitter_intel.models import TokenSnapshot
from gmgn_twitter_intel.pipeline.harness_ops import (
    attribute_harness_credits,
    materialize_market_ready_seeds,
    settle_harness_snapshots,
    update_harness_weights,
)
from gmgn_twitter_intel.storage.evidence_repository import EvidenceRepository
from gmgn_twitter_intel.storage.harness_repository import HarnessRepository
from gmgn_twitter_intel.storage.token_repository import TokenRepository
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate
from tests.test_api_http import make_event

ADDRESS = "0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416"


def test_harness_ops_settle_attribute_and_update_weights(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        evidence = EvidenceRepository(conn)
        tokens = TokenRepository(conn)
        harness = HarnessRepository(conn)
        evidence.insert_event(make_event("event-start", text="$DOG start", received_at_ms=1_000), is_watched=True)
        evidence.insert_event(make_event("event-exit", text="$DOG exit", received_at_ms=21_601_000), is_watched=True)
        tokens.upsert_snapshot(
            event_id="event-start",
            snapshot=_snapshot(price=1.0),
            received_at_ms=1_000,
            source_channel="test",
        )
        tokens.upsert_snapshot(
            event_id="event-exit",
            snapshot=_snapshot(price=1.2),
            received_at_ms=21_601_000,
            source_channel="test",
        )
        harness.create_snapshot(
            snapshot_id="snapshot-1",
            source_event_id="event-start",
            seed_id=None,
            asset="DOG",
            decision_time_ms=1_000,
            horizon="6h",
            combined_score=0.5,
            policy_signal="NO_TRADE",
            shadow_signal="LONG_SMALL",
            market_state={"baseline": "zero"},
            event_clusters=[
                {
                    "cluster_id": "cluster-1",
                    "event_type": "meme_phrase_seed",
                    "source": "cz_binance",
                    "event_score": 0.5,
                }
            ],
            versions={"config_version": "test-config"},
            risks=[],
        )

        settled = settle_harness_snapshots(harness=harness, tokens=tokens, horizon="6h", now_ms=22_700_000)
        credited = attribute_harness_credits(harness=harness, horizon="6h")
        weighted = update_harness_weights(harness=harness)
        duplicate_settle = settle_harness_snapshots(harness=harness, tokens=tokens, horizon="6h", now_ms=22_700_000)
        duplicate_credit = attribute_harness_credits(harness=harness, horizon="6h")
    finally:
        conn.close()

    assert settled["snapshots_scanned"] == 1
    assert settled["outcomes_written"] == 1
    assert credited["snapshots_scanned"] == 1
    assert credited["credits_written"] == 1
    assert weighted["weights_updated"] >= 3
    assert duplicate_settle["outcomes_written"] == 0
    assert duplicate_credit["credits_written"] == 0


def test_harness_ops_skip_missing_market_without_fabricating_outcome(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        harness = HarnessRepository(conn)
        tokens = TokenRepository(conn)
        harness.create_snapshot(
            snapshot_id="snapshot-missing",
            source_event_id="event-missing",
            seed_id=None,
            asset="UNKNOWN",
            decision_time_ms=1_000,
            horizon="6h",
            combined_score=0.5,
            policy_signal="NO_TRADE",
            shadow_signal="LONG_SMALL",
            market_state={"baseline": "zero"},
            event_clusters=[],
            versions={"config_version": "test-config"},
            risks=["unresolved_symbol"],
        )

        settled = settle_harness_snapshots(harness=harness, tokens=tokens, horizon="6h", now_ms=22_700_000)
        outcomes = harness.list_outcomes(window_ms=86_400_000, horizon="6h", limit=10)
        snapshot = harness.snapshot_by_id("snapshot-missing")
    finally:
        conn.close()

    assert settled["snapshots_scanned"] == 1
    assert settled["outcomes_written"] == 0
    assert settled["skipped_missing_market"] == 1
    assert outcomes == []
    assert snapshot["outcome_status"] == "missing_market"


def test_harness_ops_marks_missing_exit_history_as_terminal_data_gap(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        evidence = EvidenceRepository(conn)
        tokens = TokenRepository(conn)
        harness = HarnessRepository(conn)
        evidence.insert_event(make_event("event-entry", text="$DOG start", received_at_ms=1_000), is_watched=True)
        tokens.upsert_snapshot(
            event_id="event-entry",
            snapshot=_snapshot(price=1.0),
            received_at_ms=1_000,
            source_channel="test",
        )
        harness.create_snapshot(
            snapshot_id="snapshot-no-exit",
            source_event_id="event-entry",
            seed_id=None,
            asset="DOG",
            decision_time_ms=1_000,
            horizon="6h",
            combined_score=0.5,
            policy_signal="NO_TRADE",
            shadow_signal="LONG_SMALL",
            market_state={"baseline": "zero"},
            event_clusters=[],
            versions={"config_version": "test-config"},
            risks=[],
        )

        settled = settle_harness_snapshots(harness=harness, tokens=tokens, horizon="6h", now_ms=22_700_000)
        snapshot = harness.snapshot_by_id("snapshot-no-exit")
    finally:
        conn.close()

    assert settled["snapshots_scanned"] == 1
    assert settled["outcomes_written"] == 0
    assert settled["skipped_insufficient_market_data"] == 1
    assert snapshot["outcome_status"] == "insufficient_market_data"


def test_harness_ops_materializes_market_ready_seed_after_entry_snapshot_arrives(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        evidence = EvidenceRepository(conn)
        tokens = TokenRepository(conn)
        harness = HarnessRepository(conn)
        event = make_event("event-delayed-entry", text=f"$DOG start {ADDRESS}", received_at_ms=1_000)
        evidence.insert_event(event, is_watched=True)
        tokens.upsert_snapshot(
            event_id=event.event_id,
            snapshot=_snapshot(price=1.0),
            received_at_ms=event.received_at_ms,
            source_channel="test",
        )
        harness.upsert_social_event_extraction(
            extraction_id="extract-delayed-entry",
            event_id=event.event_id,
            run_id="run-delayed-entry",
            author_handle="toly",
            received_at_ms=event.received_at_ms,
            schema_version="social-event-v2",
            model_version="test",
            event_type="meme_phrase_seed",
            source_action="posted",
            subject="DOG start",
            direction_hint="attention_positive",
            attention_mechanism="direct_token_mention",
            impact_hint=0.8,
            semantic_novelty_hint=0.8,
            confidence=0.9,
            is_signal_event=True,
            anchor_terms=[{"term": "$DOG", "role": "asset", "evidence": "$DOG"}],
            token_candidates=[
                {
                    "symbol": "DOG",
                    "project_name": None,
                    "chain": "eth",
                    "address": ADDRESS,
                    "evidence": ADDRESS,
                    "confidence": 0.9,
                }
            ],
            semantic_risks=[],
            summary_zh="DOG start.",
            raw_response={},
        )
        harness.upsert_attention_seed(
            seed_id="seed-delayed-entry",
            extraction_id="extract-delayed-entry",
            event_id=event.event_id,
            author_handle="toly",
            received_at_ms=event.received_at_ms,
            event_type="meme_phrase_seed",
            subject="DOG start",
            anchor_terms=[{"term": "$DOG", "role": "asset", "evidence": "$DOG"}],
            token_uptake_count=1,
            top_linked_symbols=["DOG"],
            seed_status="market_unavailable",
            risks=["missing_entry_market"],
        )

        result = materialize_market_ready_seeds(harness=harness, evidence=evidence, tokens=tokens, limit=10)
        snapshots = harness.snapshots_for_event(event.event_id)
    finally:
        conn.close()

    assert result["seeds_scanned"] == 1
    assert result["snapshots_written"] == 2
    assert {snapshot["horizon"] for snapshot in snapshots} == {"6h", "24h"}


def _snapshot(*, price: float) -> TokenSnapshot:
    return TokenSnapshot(
        address=ADDRESS,
        chain="eth",
        symbol="DOG",
        market_cap=1_000_000,
        price=price,
        previous_price=None,
        icon_url=None,
        trigger_type="ca",
        raw={"price": price},
    )
