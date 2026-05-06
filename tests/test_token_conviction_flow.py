import time
from dataclasses import replace

from gmgn_twitter_intel.collector.gmgn_token_payload import parse_gmgn_token_payload
from gmgn_twitter_intel.models import Source
from gmgn_twitter_intel.pipeline.ingest_service import IngestService
from gmgn_twitter_intel.retrieval.search_service import SearchService
from gmgn_twitter_intel.retrieval.token_flow_service import TokenFlowService
from gmgn_twitter_intel.storage.enrichment_repository import EnrichmentRepository
from gmgn_twitter_intel.storage.entity_repository import EntityRepository
from gmgn_twitter_intel.storage.evidence_repository import EvidenceRepository
from gmgn_twitter_intel.storage.signal_repository import SignalRepository
from gmgn_twitter_intel.storage.token_repository import TokenRepository
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate
from tests.test_postgres_repositories import make_event


def open_runtime(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    migrate(conn)
    evidence = EvidenceRepository(conn)
    entities = EntityRepository(conn)
    signals = SignalRepository(conn)
    enrichment = EnrichmentRepository(conn)
    tokens = TokenRepository(conn)
    ingest = IngestService(
        evidence=evidence,
        entities=entities,
        signals=signals,
        enrichment=enrichment,
        tokens=tokens,
    )
    return conn, ingest, evidence, entities, signals, tokens


def gmgn_token_event(
    event_id: str,
    *,
    received_at_ms: int,
    author_handle: str,
    text: str,
    price: str = "1.0",
    previous_price: str | None = None,
    market_cap: str = "60490.341996",
):
    snapshot = parse_gmgn_token_payload(
        {
            "tt": "ca",
            "t": {
                "a": "0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416",
                "c": "eth",
                "mc": market_cap,
                "p": price,
                "p1": previous_price,
                "s": "DOG",
                "liquidity": "250000",
                "holder_count": 10000,
                "pool": {"pool_address": "pool-dog"},
                "stat": {"volume_24h": "750000"},
            },
        }
    )
    return replace(
        make_event(event_id, author_handle=author_handle, text=text, received_at_ms=received_at_ms),
        source=Source(
            provider="gmgn",
            transport="direct_ws",
            coverage="public_stream",
            channel="twitter_monitor_token",
        ),
        token_snapshot=snapshot,
    )


def test_token_flow_returns_identity_aware_conviction_model(tmp_path):
    conn, ingest, _, _, signals, tokens = open_runtime(tmp_path)
    try:
        base_ms = 1_700_000_000_000
        snapshot = parse_gmgn_token_payload(
            {
                "tt": "ca",
                "t": {
                    "a": "0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416",
                    "c": "eth",
                    "mc": "60490.341996",
                    "p": "0.0000000001437884",
                    "p1": "0.00000000015514471",
                    "s": "DOG",
                    "liquidity": "250000",
                    "holder_count": 10000,
                    "pool": {"pool_address": "pool-dog"},
                    "stat": {"volume_24h": "750000"},
                },
            }
        )
        gmgn_event = replace(
            make_event("event-dog-1", author_handle="traderpow", text="$DOG launch", received_at_ms=base_ms),
            source=Source(
                provider="gmgn",
                transport="direct_ws",
                coverage="public_stream",
                channel="twitter_monitor_token",
            ),
            token_snapshot=snapshot,
        )
        symbol_event = make_event(
            "event-dog-2",
            author_handle="anon",
            text="$DOG follow through",
            received_at_ms=base_ms + 30_000,
            is_watched=False,
        )

        ingest.ingest_event(gmgn_event, is_watched=True)
        ingest.ingest_event(symbol_event, is_watched=False)

        item = TokenFlowService(signals=signals, tokens=tokens).token_flow(
            window="5m",
            limit=10,
            now_ms=base_ms + 5 * 60_000,
        )[0]
    finally:
        conn.close()

    assert item["identity"] == {
        "identity_key": "token:eth:0xd0667d0618Dc9B6d2a0A55f428b47C64Bcf00416",
        "identity_status": "resolved_ca",
        "token_id": "token:eth:0xd0667d0618Dc9B6d2a0A55f428b47C64Bcf00416",
        "chain": "eth",
        "address": "0xd0667d0618Dc9B6d2a0A55f428b47C64Bcf00416",
        "symbol": "DOG",
    }
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
            "score_versions",
            "data_health",
            "timeline",
            "watch",
            "evidence_total_count",
        "posts_query",
        "timeline_query",
    }
    assert item["flow"]["mentions"] == 2
    assert item["flow"]["direct_mentions"] == 1
    assert item["flow"]["symbol_mentions"] == 1
    assert item["flow"]["avg_attribution_confidence"] >= 0.70
    assert item["flow"]["watched_mentions"] == 1
    assert item["flow"]["previous_mentions"] == 0
    assert item["flow"]["baseline_status"] == "insufficient_history"
    assert "watched_source_present" in item["social_heat"]["reasons"]
    assert item["propagation"]["phase"] == "ignition"
    assert item["propagation"]["independent_authors"] == 2
    assert item["propagation"]["top_author_share"] == 0.5
    assert item["market"]["market_status"] == "fresh"
    assert item["market"]["price"] == 0.0000000001437884
    assert item["market"]["price_change_since_social_pct"] is None
    assert item["market"]["price_change_status"] == "insufficient_history"
    assert item["opportunity"]["decision"] in {"driver", "watch"}
    assert "resolved_ca" in item["opportunity"]["reasons"]
    assert item["evidence_total_count"] == 2
    assert item["posts_query"]["token_id"] == item["identity"]["token_id"]
    assert item["timeline_query"]["token_id"] == item["identity"]["token_id"]


def test_signal_driver_uses_rolling_acceleration_healthy_diffusion_and_fresh_market(tmp_path):
    conn, ingest, _, _, signals, tokens = open_runtime(tmp_path)
    try:
        base_ms = 1_700_000_000_000
        now_ms = base_ms + 10 * 60_000
        ingest.ingest_event(
            gmgn_token_event(
                "event-dog-previous",
                received_at_ms=base_ms + 60_000,
                author_handle="early",
                text="$DOG early",
            ),
            is_watched=False,
        )
        for index, handle in enumerate(["watcher", "second", "third"]):
            ingest.ingest_event(
                gmgn_token_event(
                    f"event-dog-current-{index}",
                    received_at_ms=base_ms + 6 * 60_000 + index * 10_000,
                    author_handle=handle,
                    text=f"$DOG current acceleration {index}",
                    price=str(1.0 + index / 10),
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

    assert item["flow"]["mentions"] == 3
    assert item["flow"]["previous_mentions"] == 1
    assert item["propagation"]["phase"] == "ignition"
    assert "watched_source_present" in item["social_heat"]["reasons"]
    assert item["market"]["market_status"] == "fresh"
    assert item["opportunity"]["decision"] in {"driver", "watch"}
    assert "positive_mention_delta" in item["opportunity"]["reasons"]


def test_repeated_diffusion_discards_even_with_fresh_market(tmp_path):
    conn, ingest, _, _, signals, tokens = open_runtime(tmp_path)
    try:
        base_ms = 1_700_000_000_000
        now_ms = base_ms + 5 * 60_000
        for index, handle in enumerate(["a", "b", "c"]):
            ingest.ingest_event(
                gmgn_token_event(
                    f"event-dog-repeated-{index}",
                    received_at_ms=base_ms + 60_000 + index * 10_000,
                    author_handle=handle,
                    text="$DOG breakout now",
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

    assert item["market"]["market_status"] == "fresh"
    assert item["propagation"]["phase"] == "concentration"
    assert item["opportunity"]["decision"] == "discard"
    assert "repeated_text_cluster" in item["opportunity"]["risks"]


def test_public_only_watch_is_a_risk_not_a_discard_when_market_and_diffusion_are_healthy(tmp_path):
    conn, ingest, _, _, signals, tokens = open_runtime(tmp_path)
    try:
        base_ms = 1_700_000_000_000
        for index, handle in enumerate(["a", "b"]):
            ingest.ingest_event(
                gmgn_token_event(
                    f"event-dog-public-{index}",
                    received_at_ms=base_ms + 60_000 + index * 10_000,
                    author_handle=handle,
                    text=f"$DOG public organic {index}",
                ),
                is_watched=False,
            )

        item = TokenFlowService(signals=signals, tokens=tokens).token_flow(
            window="5m",
            limit=10,
            now_ms=base_ms + 5 * 60_000,
        )[0]
    finally:
        conn.close()

    assert item["propagation"]["phase"] == "ignition"
    assert item["market"]["market_status"] == "fresh"
    assert item["opportunity"]["decision"] != "discard"
    assert "public_stream_coverage" in item["opportunity"]["risks"]


def test_token_flow_returns_one_current_row_per_token_identity(tmp_path):
    conn, ingest, _, _, signals, tokens = open_runtime(tmp_path)
    try:
        now_ms = int(time.time() * 1000)
        snapshot_payload = {
            "tt": "ca",
            "t": {
                "a": "0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416",
                "c": "eth",
                "mc": "60490.341996",
                "p": "1.0",
                "p1": None,
                "s": "DOG",
            },
        }
        for event_id, received_at_ms in [
            ("event-dog-old", now_ms - 90 * 60_000),
            ("event-dog-current", now_ms - 10 * 60_000),
        ]:
            event = replace(
                make_event(event_id, author_handle="traderpow", text="$DOG", received_at_ms=received_at_ms),
                source=Source(
                    provider="gmgn",
                    transport="direct_ws",
                    coverage="public_stream",
                    channel="twitter_monitor_token",
                ),
                token_snapshot=parse_gmgn_token_payload(snapshot_payload),
            )
            ingest.ingest_event(event, is_watched=True)

        items = TokenFlowService(signals=signals, tokens=tokens).token_flow(window="1h", limit=10)
    finally:
        conn.close()

    assert len(items) == 1
    assert items[0]["identity"]["identity_key"] == "token:eth:0xd0667d0618Dc9B6d2a0A55f428b47C64Bcf00416"
    assert items[0]["flow"]["mentions"] == 1
    assert items[0]["flow"]["window_end_ms"] >= now_ms - 10 * 60_000


def test_token_flow_attributes_symbol_only_mentions_into_resolved_candidate(tmp_path):
    conn, ingest, _, _, signals, tokens = open_runtime(tmp_path)
    try:
        now_ms = int(time.time() * 1000)
        symbol_event = make_event(
            "event-dog-symbol",
            author_handle="traderpow",
            text="$DOG",
            received_at_ms=now_ms - 20_000,
        )
        snapshot = parse_gmgn_token_payload(
            {
                "tt": "ca",
                "t": {
                    "a": "0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416",
                    "c": "eth",
                    "mc": "60490.341996",
                    "p": "1.0",
                    "p1": None,
                    "s": "DOG",
                    "liquidity": "250000",
                    "holder_count": 10000,
                    "pool": {"pool_address": "pool-dog"},
                    "stat": {"volume_24h": "750000"},
                },
            }
        )
        gmgn_event = replace(
            make_event("event-dog-ca", author_handle="anon", text="$DOG launch", received_at_ms=now_ms - 10_000),
            source=Source(
                provider="gmgn",
                transport="direct_ws",
                coverage="public_stream",
                channel="twitter_monitor_token",
            ),
            token_snapshot=snapshot,
        )

        ingest.ingest_event(symbol_event, is_watched=True)
        ingest.ingest_event(gmgn_event, is_watched=False)
        items = TokenFlowService(signals=signals, tokens=tokens).token_flow(window="1h", limit=10)
    finally:
        conn.close()

    assert len(items) == 1
    assert items[0]["identity"]["identity_key"] == "token:eth:0xd0667d0618Dc9B6d2a0A55f428b47C64Bcf00416"
    assert items[0]["flow"]["mentions"] == 2
    assert items[0]["flow"]["direct_mentions"] == 1
    assert items[0]["flow"]["symbol_mentions"] == 1
    assert items[0]["propagation"]["independent_authors"] == 2
    assert sum(int(author["watched_count"]) for author in items[0]["propagation"]["top_authors"]) == 1


def test_token_flow_excludes_ambiguous_symbol_buckets_from_radar(tmp_path):
    conn, ingest, _, _, signals, tokens = open_runtime(tmp_path)
    try:
        base_ms = 1_700_000_000_000
        target_snapshot = parse_gmgn_token_payload(
            {
                "tt": "ca",
                "t": {
                    "a": "5UUH9RTDiSpq6HKS6bp4NdU9PNJpXRXuiw6ShBTBhgH2",
                    "c": "sol",
                    "mc": "45151685.6",
                    "p": "0.045",
                    "p1": "0.041",
                    "s": "TROLL",
                    "liquidity": "2442798.17",
                    "holder_count": 51064,
                    "pool": {"pool_address": "pool-target"},
                    "stat": {"volume_24h": "5000000"},
                },
            }
        )
        other_snapshot = parse_gmgn_token_payload(
            {
                "tt": "ca",
                "t": {
                    "a": "DkVsvbzz39yx8hawbxfWubJKpZ4cdc4SPtPf5TZQpump",
                    "c": "sol",
                    "mc": "12000",
                    "p": "0.001",
                    "p1": "0.001",
                    "s": "TROLL",
                    "liquidity": "800",
                    "holder_count": 45,
                    "pool": {"pool_address": "pool-weak"},
                    "stat": {"volume_24h": "1000"},
                },
            }
        )
        for event_id, snapshot, offset, handle in [
            ("event-troll-target-1", target_snapshot, 1_000, "voicea"),
            ("event-troll-target-2", target_snapshot, 2_000, "voiceb"),
            ("event-troll-other", other_snapshot, 3_000, "voicec"),
        ]:
            event = replace(
                make_event(
                    event_id,
                    author_handle=handle,
                    text="$TROLL structured token evidence",
                    received_at_ms=base_ms + offset,
                ),
                source=Source(
                    provider="gmgn",
                    transport="direct_ws",
                    coverage="public_stream",
                    channel="twitter_monitor_token",
                ),
                token_snapshot=snapshot,
            )
            ingest.ingest_event(event, is_watched=False)

        for index in range(8):
            event = make_event(
                f"event-troll-symbol-{index}",
                author_handle=f"symbolvoice{index}",
                text="$TROLL symbol-only chatter",
                received_at_ms=base_ms + 10_000 + index,
            )
            ingest.ingest_event(event, is_watched=False)

        items = TokenFlowService(signals=signals, tokens=tokens).token_flow(
            window="1h",
            limit=10,
            now_ms=base_ms + 60_000,
        )
    finally:
        conn.close()

    assert {item["identity"]["identity_status"] for item in items} == {"resolved_ca"}
    assert {item["identity"]["address"] for item in items} == {
        "5UUH9RTDiSpq6HKS6bp4NdU9PNJpXRXuiw6ShBTBhgH2",
        "DkVsvbzz39yx8hawbxfWubJKpZ4cdc4SPtPf5TZQpump",
    }
    target = next(
        item for item in items if item["identity"]["address"] == "5UUH9RTDiSpq6HKS6bp4NdU9PNJpXRXuiw6ShBTBhgH2"
    )
    assert target["flow"]["mentions"] == 10
    assert target["flow"]["direct_mentions"] == 2
    assert target["flow"]["symbol_mentions"] == 8


def test_token_flow_price_delta_uses_window_snapshots_not_payload_previous_price(tmp_path):
    conn, ingest, _, _, signals, tokens = open_runtime(tmp_path)
    try:
        window_ms = 300_000
        current_start_ms = (1_700_000_000_000 // window_ms) * window_ms + window_ms
        previous_ms = current_start_ms - 10_000
        current_ms = current_start_ms + 60_000
        for event_id, received_at_ms, price, previous_price in [
            ("event-dog-before", previous_ms, "1.0", "99.0"),
            ("event-dog-now", current_ms, "1.2", "0.01"),
        ]:
            snapshot = parse_gmgn_token_payload(
                {
                    "tt": "ca",
                    "t": {
                        "a": "0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416",
                        "c": "eth",
                        "mc": "60490.341996",
                        "p": price,
                        "p1": previous_price,
                        "s": "DOG",
                    },
                }
            )
            event = replace(
                make_event(event_id, author_handle="traderpow", text="$DOG launch", received_at_ms=received_at_ms),
                source=Source(
                    provider="gmgn",
                    transport="direct_ws",
                    coverage="public_stream",
                    channel="twitter_monitor_token",
                ),
                token_snapshot=snapshot,
            )
            ingest.ingest_event(event, is_watched=True)

        item = TokenFlowService(signals=signals, tokens=tokens).token_flow(
            window="5m",
            limit=10,
            now_ms=current_start_ms + window_ms,
        )[0]
    finally:
        conn.close()

    assert item["market"]["price_before_social_start"] == 1.0
    assert item["market"]["price_at_social_start"] == 1.2
    assert item["market"]["price_at_reference"] == 1.2
    assert item["market"]["price_change_status"] == "insufficient_history"
    assert item["market"]["price_change_since_social_pct"] is None
    assert item["market"]["price_change_before_social_pct"] == 0.2
    assert item["flow"]["previous_mentions"] == 1
    assert item["flow"]["mention_delta"] == 0


def test_token_flow_price_delta_requires_window_snapshots(tmp_path):
    conn, ingest, _, _, signals, tokens = open_runtime(tmp_path)
    try:
        current_ms = int(time.time() * 1000) - 10_000
        snapshot = parse_gmgn_token_payload(
            {
                "tt": "ca",
                "t": {
                    "a": "0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416",
                    "c": "eth",
                    "mc": "60490.341996",
                    "p": "1.2",
                    "p1": "1.0",
                    "s": "DOG",
                },
            }
        )
        event = replace(
            make_event("event-dog-single-snapshot", author_handle="traderpow", text="$DOG", received_at_ms=current_ms),
            source=Source(
                provider="gmgn",
                transport="direct_ws",
                coverage="public_stream",
                channel="twitter_monitor_token",
            ),
            token_snapshot=snapshot,
        )
        ingest.ingest_event(event, is_watched=True)

        item = TokenFlowService(signals=signals, tokens=tokens).token_flow(window="1h", limit=10)[0]
    finally:
        conn.close()

    assert item["market"]["price_at_social_start"] == 1.2
    assert item["market"]["price_at_reference"] == 1.2
    assert item["market"]["price_change_status"] == "insufficient_history"
    assert item["market"]["price_change_since_social_pct"] is None


def test_token_flow_excludes_symbol_only_mentions_but_keeps_alert_evidence(tmp_path):
    conn, ingest, _, _, signals, tokens = open_runtime(tmp_path)
    try:
        event = make_event(
            "event-symbol-only",
            author_handle="traderpow",
            text="$UPEG",
            received_at_ms=1_700_000_000_000,
        )
        ingest.ingest_event(event, is_watched=True)
        items = TokenFlowService(signals=signals, tokens=tokens).token_flow(
            window="5m",
            limit=10,
            now_ms=1_700_000_000_000 + 5 * 60_000,
        )
        alerts = signals.account_alerts(
            window_ms=86_400_000,
            now_ms=1_700_000_000_000 + 5 * 60_000,
            limit=10,
        )
    finally:
        conn.close()

    assert items == []
    assert alerts[0]["event_id"] == "event-symbol-only"
    assert alerts[0]["entity_key"] == "symbol:UPEG"
    assert alerts[0]["token_resolution_status"] == "unresolved_symbol"


def test_token_flow_penalizes_single_author_concentration(tmp_path):
    conn, ingest, _, _, signals, tokens = open_runtime(tmp_path)
    try:
        base_ms = 1_700_000_000_000
        for index in range(3):
            snapshot = parse_gmgn_token_payload(
                {
                    "tt": "ca",
                    "t": {
                        "a": "0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416",
                        "c": "eth",
                        "mc": "60490.341996",
                        "p": "1.0",
                        "p1": None,
                        "s": "DOG",
                    },
                }
            )
            event = replace(
                make_event(
                    f"event-dog-concentrated-{index}",
                    author_handle="singlevoice",
                    text=f"$DOG push {index}",
                    received_at_ms=base_ms + index * 1_000,
                    is_watched=False,
                ),
                source=Source(
                    provider="gmgn",
                    transport="direct_ws",
                    coverage="public_stream",
                    channel="twitter_monitor_token",
                ),
                token_snapshot=snapshot,
            )
            ingest.ingest_event(event, is_watched=False)

        item = TokenFlowService(signals=signals, tokens=tokens).token_flow(
            window="5m",
            limit=10,
            now_ms=base_ms + 5 * 60_000,
        )[0]
    finally:
        conn.close()

    assert item["propagation"]["top_author_share"] == 1.0
    assert item["propagation"]["phase"] == "concentration"
    assert "author_concentration_high" in item["propagation"]["risks"]
    assert item["opportunity"]["decision"] != "driver"
    assert "author_concentration_high" in item["opportunity"]["risks"]


def test_search_resolves_gmgn_payload_token_mentions_without_text_ca(tmp_path):
    conn, ingest, evidence, _entities, signals, tokens = open_runtime(tmp_path)
    try:
        snapshot = parse_gmgn_token_payload(
            {
                "tt": "ca",
                "t": {
                    "a": "0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416",
                    "c": "eth",
                    "mc": "60490.341996",
                    "p": "0.0000000001437884",
                    "p1": "0.00000000015514471",
                    "s": "DOG",
                },
            }
        )
        event = replace(
            make_event("event-dog-payload", text="fresh launch", received_at_ms=1_700_000_000_000),
            source=Source(
                provider="gmgn",
                transport="direct_ws",
                coverage="public_stream",
                channel="twitter_monitor_token",
            ),
            token_snapshot=snapshot,
        )
        ingest.ingest_event(event, is_watched=False)

        by_ca = SearchService(evidence=evidence, signals=signals, tokens=tokens).search(
            "0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416",
            limit=10,
        )
        by_symbol = SearchService(evidence=evidence, signals=signals, tokens=tokens).search("$DOG", limit=10)
    finally:
        conn.close()

    assert by_ca.items[0]["event"]["event_id"] == "event-dog-payload"
    assert by_ca.items[0]["match_type"] == "token_attribution"
    assert by_symbol.items[0]["event"]["event_id"] == "event-dog-payload"
    assert by_symbol.items[0]["match_type"] == "token_attribution"
