import time
from dataclasses import replace
from threading import RLock

from gmgn_twitter_intel.collector.gmgn_token_payload import parse_gmgn_token_payload
from gmgn_twitter_intel.models import Source
from gmgn_twitter_intel.pipeline.ingest_service import IngestService
from gmgn_twitter_intel.retrieval.search_service import SearchService
from gmgn_twitter_intel.retrieval.token_flow_service import TokenFlowService
from gmgn_twitter_intel.storage.enrichment_repository import EnrichmentRepository
from gmgn_twitter_intel.storage.entity_repository import EntityRepository
from gmgn_twitter_intel.storage.evidence_repository import EvidenceRepository
from gmgn_twitter_intel.storage.signal_repository import SignalRepository
from gmgn_twitter_intel.storage.sqlite_client import connect_sqlite
from gmgn_twitter_intel.storage.sqlite_schema import migrate
from gmgn_twitter_intel.storage.token_repository import TokenRepository
from tests.test_sqlite_repositories import make_event


def open_runtime(tmp_path):
    conn = connect_sqlite(tmp_path / "twitter_intel.sqlite3", read_only=False)
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
        write_lock=RLock(),
    )
    return conn, ingest, evidence, entities, signals, tokens


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

        item = TokenFlowService(signals=signals, tokens=tokens).token_flow(window="5m", limit=10)[0]
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
    assert set(item) == {"identity", "market", "flow", "sources", "fresh", "signal", "evidence_best", "evidence"}
    assert item["flow"]["mentions"] == 2
    assert item["flow"]["watched_mentions"] == 1
    assert item["flow"]["previous_mentions"] == 0
    assert item["flow"]["baseline_status"] == "insufficient_history"
    assert item["sources"]["unique_authors"] == 2
    assert item["sources"]["watched_authors"] == 1
    assert item["sources"]["top_author_share"] == 0.5
    assert item["market"]["market_status"] == "fresh"
    assert item["market"]["price"] == 0.0000000001437884
    assert item["market"]["price_change_window_pct"] == -0.073198177366
    assert item["market"]["price_change_status"] == "snapshot_previous"
    assert item["signal"]["decision"] == "watch"
    assert "watched_evidence" in item["signal"]["reasons"]
    assert item["evidence_best"]["event_id"] == "event-dog-1"
    assert item["evidence_best"]["score"] > 0
    assert item["evidence"][0]["event_id"] == "event-dog-1"


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
    assert items[0]["evidence_best"]["event_id"] == "event-dog-current"


def test_token_flow_merges_unique_symbol_mentions_after_token_resolution(tmp_path):
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
    assert items[0]["sources"]["unique_authors"] == 2
    assert items[0]["sources"]["watched_authors"] == 1


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

        item = TokenFlowService(signals=signals, tokens=tokens).token_flow(window="5m", limit=10)[0]
    finally:
        conn.close()

    assert item["market"]["price_at_window_start"] == 1.0
    assert item["market"]["price_at_window_end"] == 1.2
    assert item["market"]["price_change_status"] == "ready"
    assert item["market"]["price_change_window_pct"] == 0.2
    assert item["flow"]["previous_mentions"] == 1
    assert item["flow"]["mention_delta"] == 0


def test_token_flow_price_delta_falls_back_to_snapshot_previous_price(tmp_path):
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

    assert item["market"]["price_at_window_start"] == 1.0
    assert item["market"]["price_at_window_end"] == 1.2
    assert item["market"]["price_change_status"] == "snapshot_previous"
    assert item["market"]["price_change_window_pct"] == 0.2


def test_token_flow_missing_market_forces_discard_signal(tmp_path):
    conn, ingest, _, _, signals, tokens = open_runtime(tmp_path)
    try:
        event = make_event(
            "event-symbol-only",
            author_handle="traderpow",
            text="$UPEG",
            received_at_ms=1_700_000_000_000,
        )
        ingest.ingest_event(event, is_watched=True)
        item = TokenFlowService(signals=signals, tokens=tokens).token_flow(window="5m", limit=10)[0]
    finally:
        conn.close()

    assert item["identity"]["identity_status"] == "unresolved_symbol"
    assert item["market"]["market_status"] == "missing"
    assert item["signal"]["decision"] == "discard"
    assert "market_missing" in item["signal"]["risks"]
    assert "unresolved_symbol" in item["signal"]["risks"]


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
                    text="$DOG push",
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

        item = TokenFlowService(signals=signals, tokens=tokens).token_flow(window="5m", limit=10)[0]
    finally:
        conn.close()

    assert item["sources"]["top_author_share"] == 1.0
    assert "author_concentration_high" in item["sources"]["source_quality_reasons"]
    assert item["signal"]["decision"] != "driver"
    assert "author_concentration_high" in item["signal"]["risks"]


def test_search_resolves_gmgn_payload_token_mentions_without_text_ca(tmp_path):
    conn, ingest, evidence, entities, signals, _ = open_runtime(tmp_path)
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

        by_ca = SearchService(evidence=evidence, entities=entities, signals=signals).search(
            "0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416",
            limit=10,
        )
        by_symbol = SearchService(evidence=evidence, entities=entities, signals=signals).search("$DOG", limit=10)
    finally:
        conn.close()

    assert by_ca.items[0]["event"]["event_id"] == "event-dog-payload"
    assert by_ca.items[0]["match_type"] == "exact_ca"
    assert by_symbol.items[0]["event"]["event_id"] == "event-dog-payload"
    assert by_symbol.items[0]["match_type"] == "exact_symbol"
