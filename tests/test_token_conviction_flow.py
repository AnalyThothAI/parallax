from dataclasses import replace
from threading import RLock

from gmgn_twitter_intel.collector.gmgn_token_payload import parse_gmgn_token_payload
from gmgn_twitter_intel.models import Source
from gmgn_twitter_intel.pipeline.ingest_service import IngestService
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
    return conn, ingest, signals, tokens


def test_token_flow_returns_identity_aware_conviction_model(tmp_path):
    conn, ingest, signals, tokens = open_runtime(tmp_path)
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
    assert item["social"]["mention_count"] == 2
    assert item["social"]["watched_mention_count"] == 1
    assert item["baseline"]["baseline_status"] == "insufficient_history"
    assert "watched_first_mention" in item["anomaly"]["reasons"]
    assert item["market"]["market_status"] == "fresh"
    assert item["market"]["price"] == 0.0000000001437884
    assert item["market"]["price_change_pct"] < 0
    assert item["confidence"]["coverage"] == "public_stream"
    assert item["confidence"]["score"] > 0
    assert item["evidence"][0]["event_id"] == "event-dog-1"
