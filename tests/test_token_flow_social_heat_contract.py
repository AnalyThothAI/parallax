
from gmgn_twitter_intel.collector.gmgn_token_payload import parse_gmgn_token_payload
from gmgn_twitter_intel.pipeline.ingest_service import IngestService
from gmgn_twitter_intel.retrieval.token_flow_service import TokenFlowService
from gmgn_twitter_intel.storage.enrichment_repository import EnrichmentRepository
from gmgn_twitter_intel.storage.entity_repository import EntityRepository
from gmgn_twitter_intel.storage.evidence_repository import EvidenceRepository
from gmgn_twitter_intel.storage.market_observation_repository import MarketObservationRepository
from gmgn_twitter_intel.storage.signal_repository import SignalRepository
from gmgn_twitter_intel.storage.token_repository import TokenRepository
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate
from tests.test_postgres_repositories import make_event
from tests.test_token_rolling_flow import open_runtime, token_event


def test_token_flow_item_uses_social_heat_contract(tmp_path):
    conn, ingest, signals, tokens = open_runtime(tmp_path)
    try:
        now_ms = 1_700_000_123_456
        for index, handle in enumerate(["seed", "amp1", "amp2", "amp3"]):
            ingest.ingest_event(
                token_event(
                    f"event-dog-social-{index}",
                    received_at_ms=now_ms - (index + 1) * 10_000,
                    author_handle=handle,
                    text=f"$DOG 0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416 mcap liquidity breakout {index}",
                ),
                is_watched=index == 0,
            )

        item = TokenFlowService(signals=signals, tokens=tokens).token_flow(
            window="1h",
            limit=10,
            now_ms=now_ms,
        )[0]
    finally:
        conn.close()

    assert set(item) == {
        "identity",
        "market",
        "flow",
        "social_heat",
        "discussion_quality",
        "propagation",
        "tradeability",
        "timing",
        "opportunity",
        "watch",
        "timeline",
        "score_versions",
        "data_health",
        "evidence_total_count",
        "posts_query",
        "timeline_query",
    }
    assert item["social_heat"]["score_version"] == "social_heat_v2"
    assert item["discussion_quality"]["score_version"] == "discussion_quality_v2"
    assert item["propagation"]["score_version"] == "propagation_v2"
    assert item["tradeability"]["score_version"] == "tradeability_v2"
    assert item["timing"]["score_version"] == "timing_v4"
    assert item["opportunity"]["score_version"] == "social_opportunity_v3"
    assert item["social_heat"]["data_health"]
    assert item["opportunity"]["data_health"]
    assert item["score_versions"] == {
        "social_heat": "social_heat_v2",
        "discussion_quality": "discussion_quality_v2",
        "propagation": "propagation_v2",
        "tradeability": "tradeability_v2",
        "timing": "timing_v4",
        "opportunity": "social_opportunity_v3",
    }
    assert item["data_health"]["market"] in {"fresh", "stale", "missing"}
    assert item["market"]["snapshot_id"]
    assert item["market"]["lookahead_risk"] is False
    assert item["opportunity"]["decision"] in {"driver", "watch", "discard"}
    assert item["timeline_query"] == {
        "token_id": item["identity"]["token_id"],
        "chain": "eth",
        "address": item["identity"]["address"],
        "window": "1h",
        "scope": "all",
    }


def test_token_flow_propagation_uses_real_new_author_total(tmp_path):
    conn, ingest, signals, tokens = open_runtime(tmp_path)
    try:
        now_ms = 1_700_000_123_456
        for index, handle in enumerate(["seed", "seed", "amp"]):
            ingest.ingest_event(
                token_event(
                    f"event-dog-new-author-{index}",
                    received_at_ms=now_ms - (3 - index) * 20_000,
                    author_handle=handle,
                    text=f"$DOG new author {index}",
                ),
                is_watched=index == 0,
            )

        item = TokenFlowService(signals=signals, tokens=tokens).token_flow(
            window="5m",
            limit=10,
            now_ms=now_ms,
        )[0]
    finally:
        conn.close()

    assert item["timeline"]["summary"]["independent_authors"] == 2
    assert item["timeline"]["summary"]["new_authors_total"] == 2
    assert item["propagation"]["new_authors"] == 2


def test_token_flow_social_heat_reports_real_multi_window_mentions(tmp_path):
    conn, ingest, signals, tokens = open_runtime(tmp_path)
    try:
        now_ms = 1_700_000_000_000
        for event_id, age_ms in [
            ("event-dog-5m", 60_000),
            ("event-dog-1h", 50 * 60_000),
            ("event-dog-4h", 3 * 60 * 60_000),
        ]:
            ingest.ingest_event(
                token_event(
                    event_id,
                    received_at_ms=now_ms - age_ms,
                    author_handle=event_id,
                    text=f"$DOG multi-window {event_id}",
                ),
                is_watched=False,
            )

        item = TokenFlowService(signals=signals, tokens=tokens).token_flow(
            window="5m",
            limit=10,
            now_ms=now_ms,
        )[0]
    finally:
        conn.close()

    assert item["flow"]["window"] == "5m"
    assert item["social_heat"]["mentions"] == 1
    assert item["social_heat"]["mentions_5m"] == 1
    assert item["social_heat"]["mentions_1h"] == 2
    assert item["social_heat"]["mentions_4h"] == 3
    assert item["social_heat"]["mentions_24h"] == 3


def test_token_flow_supports_4h_window(tmp_path):
    conn, ingest, signals, tokens = open_runtime(tmp_path)
    try:
        now_ms = 1_700_000_000_000
        ingest.ingest_event(
            token_event("event-dog-4h-window", received_at_ms=now_ms - 3 * 60 * 60_000),
            is_watched=True,
        )

        item = TokenFlowService(signals=signals, tokens=tokens).token_flow(
            window="4h",
            limit=10,
            now_ms=now_ms,
        )[0]
    finally:
        conn.close()

    assert item["flow"]["window"] == "4h"
    assert item["flow"]["mentions"] == 1
    assert item["social_heat"]["mentions_4h"] == 1


def test_token_flow_timing_flags_price_move_before_social_start(tmp_path):
    conn, ingest, signals, tokens = open_runtime(tmp_path)
    try:
        now_ms = 1_700_000_600_000
        window_start_ms = now_ms - 3_600_000
        evidence = EvidenceRepository(conn)
        for event_id, received_at_ms, price in [
            ("market-start", window_start_ms - 1_000, "1.0"),
            ("market-before-social", window_start_ms + 300_000, "1.35"),
        ]:
            evidence.insert_event(make_event(event_id, received_at_ms=received_at_ms), is_watched=False)
            tokens.upsert_snapshot(
                event_id=event_id,
                snapshot=parse_gmgn_token_payload(
                    {
                        "tt": "ca",
                        "t": {
                            "a": "0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416",
                            "c": "eth",
                            "mc": "60490.341996",
                            "p": price,
                            "p1": None,
                            "s": "DOG",
                            "liquidity": "250000",
                            "pool": {"pool_address": "pool-dog"},
                        },
                    }
                ),
                received_at_ms=received_at_ms,
                source_channel="gmgn_openapi_token_info",
            )
        ingest.ingest_event(
            token_event(
                "event-dog-social-start",
                received_at_ms=window_start_ms + 900_000,
                author_handle="seed",
                text="$DOG 0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416 social arrives late",
            ),
            is_watched=True,
        )
        tokens.upsert_snapshot(
            event_id="event-dog-social-start",
            snapshot=parse_gmgn_token_payload(
                {
                    "tt": "ca",
                    "t": {
                        "a": "0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416",
                        "c": "eth",
                        "mc": "60490.341996",
                        "p": "1.35",
                        "p1": None,
                        "s": "DOG",
                        "liquidity": "250000",
                        "pool": {"pool_address": "pool-dog"},
                    },
                }
            ),
            received_at_ms=window_start_ms + 900_000,
            source_channel="gmgn_openapi_token_info",
        )

        item = TokenFlowService(signals=signals, tokens=tokens).token_flow(
            window="1h",
            limit=10,
            now_ms=now_ms,
        )[0]
    finally:
        conn.close()

    assert item["timing"]["status"] == "chase_risk"
    assert item["timing"]["chase_risk"] is True
    assert item["timing"]["price_change_before_social_pct"] >= 0.3


def test_token_flow_market_delta_uses_social_start_not_window_start(tmp_path):
    conn, ingest, signals, tokens = open_runtime(tmp_path)
    try:
        now_ms = 1_700_000_600_000
        window_start_ms = now_ms - 3_600_000
        evidence = EvidenceRepository(conn)
        evidence.insert_event(make_event("market-window-start", received_at_ms=window_start_ms), is_watched=False)
        tokens.upsert_snapshot(
            event_id="market-window-start",
            snapshot=parse_gmgn_token_payload(
                {
                    "tt": "ca",
                    "t": {
                        "a": "0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416",
                        "c": "eth",
                        "mc": "60490.341996",
                        "p": "0.5",
                        "p1": None,
                        "s": "DOG",
                    },
                }
            ),
            received_at_ms=window_start_ms,
            source_channel="gmgn_openapi_token_info",
        )
        social_start_ms = window_start_ms + 900_000
        ingest.ingest_event(
            token_event(
                "event-dog-social-start-v2",
                received_at_ms=social_start_ms,
                author_handle="seed",
                text="$DOG social starts here",
            ),
            is_watched=True,
        )
        ingest.ingest_event(
            token_event(
                "event-dog-reference-v2",
                received_at_ms=social_start_ms + 120_000,
                author_handle="amp",
                text="$DOG reference price",
            ),
            is_watched=False,
        )
        tokens.upsert_snapshot(
            event_id="event-dog-reference-v2",
            snapshot=parse_gmgn_token_payload(
                {
                    "tt": "ca",
                    "t": {
                        "a": "0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416",
                        "c": "eth",
                        "mc": "60490.341996",
                        "p": "1.2",
                        "p1": None,
                        "s": "DOG",
                    },
                }
            ),
            received_at_ms=social_start_ms + 120_000,
            source_channel="gmgn_openapi_token_info",
        )

        item = TokenFlowService(signals=signals, tokens=tokens).token_flow(
            window="1h",
            limit=10,
            now_ms=now_ms,
        )[0]
    finally:
        conn.close()

    assert item["market"]["social_signal_start_ms"] == social_start_ms
    assert item["market"]["price_at_social_start"] == 1.0
    assert item["market"]["price_at_reference"] == 1.2
    assert item["market"]["price_change_since_social_pct"] == 0.2
    assert item["market"]["price_change_status"] == "ready"


def test_token_flow_ready_price_history_is_not_masked_by_later_pending_observations(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        evidence = EvidenceRepository(conn)
        entities = EntityRepository(conn)
        signals = SignalRepository(conn)
        tokens = TokenRepository(conn)
        observations = MarketObservationRepository(conn)
        ingest = IngestService(
            evidence=evidence,
            entities=entities,
            signals=signals,
            enrichment=EnrichmentRepository(conn),
            tokens=tokens,
            market_observations=observations,
        )
        now_ms = 1_700_000_600_000
        social_start_ms = now_ms - 180_000
        reference_ms = now_ms - 60_000
        ingest.ingest_event(
            token_event(
                "event-dog-ready-start",
                received_at_ms=social_start_ms,
                author_handle="seed",
                text="$DOG ready start",
            ),
            is_watched=True,
        )
        ingest.ingest_event(
            token_event(
                "event-dog-ready-reference",
                received_at_ms=reference_ms,
                author_handle="amp",
                text="$DOG ready reference",
            ),
            is_watched=False,
        )
        tokens.upsert_snapshot(
            event_id="event-dog-ready-reference",
            snapshot=parse_gmgn_token_payload(
                {
                    "tt": "ca",
                    "t": {
                        "a": "0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416",
                        "c": "eth",
                        "mc": "60490.341996",
                        "p": "1.2",
                        "p1": None,
                        "s": "DOG",
                    },
                }
            ),
            received_at_ms=reference_ms,
            source_channel="gmgn_openapi_token_info",
        )

        pending_count = conn.execute(
            "SELECT COUNT(*) AS count FROM token_market_observations WHERE status = 'pending'"
        ).fetchone()
        item = TokenFlowService(signals=signals, tokens=tokens).token_flow(
            window="1h",
            limit=10,
            now_ms=now_ms,
        )[0]
    finally:
        conn.close()

    assert pending_count["count"] == 2
    assert item["market"]["price_change_since_social_pct"] == 0.2
    assert item["market"]["market_observation_status"] == "ready"
    assert item["market"]["price_change_status"] == "ready"
    assert item["timing"]["status"] == "neutral"


def test_token_flow_pending_observation_surfaces_market_status(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        evidence = EvidenceRepository(conn)
        entities = EntityRepository(conn)
        signals = SignalRepository(conn)
        tokens = TokenRepository(conn)
        observations = MarketObservationRepository(conn)
        ingest = IngestService(
            evidence=evidence,
            entities=entities,
            signals=signals,
            enrichment=EnrichmentRepository(conn),
            tokens=tokens,
            market_observations=observations,
        )
        now_ms = 1_700_000_600_000
        ingest.ingest_event(
            make_event(
                "event-sol-pending",
                text="$SOL 5UUH9RTDiSpq6HKS6bp4NdU9PNJpXRXuiw6ShBTBhgH2",
                received_at_ms=now_ms - 60_000,
            ),
            is_watched=True,
        )

        item = TokenFlowService(signals=signals, tokens=tokens).token_flow(
            window="1h",
            limit=10,
            now_ms=now_ms,
        )[0]
    finally:
        conn.close()

    assert item["market"]["market_observation_status"] == "pending"
    assert item["market"]["price_change_status"] == "pending_observation"
    assert item["timing"]["status"] == "market_pending"


def test_token_flow_provider_failure_status_is_visible(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        evidence = EvidenceRepository(conn)
        entities = EntityRepository(conn)
        signals = SignalRepository(conn)
        tokens = TokenRepository(conn)
        observations = MarketObservationRepository(conn)
        ingest = IngestService(
            evidence=evidence,
            entities=entities,
            signals=signals,
            enrichment=EnrichmentRepository(conn),
            tokens=tokens,
            market_observations=observations,
        )
        now_ms = 1_700_000_600_000
        ingest.ingest_event(
            make_event(
                "event-sol-provider-error",
                text="$SOL 5UUH9RTDiSpq6HKS6bp4NdU9PNJpXRXuiw6ShBTBhgH2",
                received_at_ms=now_ms - 60_000,
            ),
            is_watched=True,
        )
        row = conn.execute("SELECT * FROM token_market_observations").fetchone()
        observations.complete(
            dict(row),
            snapshot_id=None,
            status="provider_not_configured",
            provider=None,
            now_ms=now_ms - 30_000,
        )

        item = TokenFlowService(signals=signals, tokens=tokens).token_flow(
            window="1h",
            limit=10,
            now_ms=now_ms,
        )[0]
    finally:
        conn.close()

    assert item["market"]["market_observation_status"] == "provider_not_configured"
    assert item["market"]["price_change_status"] == "provider_not_configured"
    assert item["timing"]["status"] == "market_unavailable"
