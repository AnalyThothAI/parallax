from gmgn_twitter_intel.models import TokenSnapshot
from gmgn_twitter_intel.pipeline.harness_ops import (
    attribute_harness_credits,
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
    finally:
        conn.close()

    assert settled["snapshots_scanned"] == 1
    assert settled["outcomes_written"] == 0
    assert settled["skipped_missing_market"] == 1
    assert outcomes == []


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
