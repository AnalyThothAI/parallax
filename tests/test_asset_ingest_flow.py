from __future__ import annotations

from dataclasses import replace

from gmgn_twitter_intel.collector.gmgn_token_payload import parse_gmgn_token_payload
from gmgn_twitter_intel.pipeline.ingest_service import IngestService
from gmgn_twitter_intel.storage.asset_repository import AssetRepository
from gmgn_twitter_intel.storage.enrichment_repository import EnrichmentRepository
from gmgn_twitter_intel.storage.entity_repository import EntityRepository
from gmgn_twitter_intel.storage.evidence_repository import EvidenceRepository
from gmgn_twitter_intel.storage.signal_repository import SignalRepository
from tests.factories import make_event
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate


def open_ingest(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    migrate(conn)
    assets = AssetRepository(conn)
    ingest = IngestService(
        evidence=EvidenceRepository(conn),
        entities=EntityRepository(conn),
        signals=SignalRepository(conn),
        enrichment=EnrichmentRepository(conn),
        assets=assets,
    )
    return conn, assets, ingest


def test_ingest_mirror_writes_unresolved_token_intent(tmp_path):
    conn, assets, ingest = open_ingest(tmp_path)
    try:
        result = ingest.ingest_event(make_event("event-1", text="$mirror is moving"), is_watched=True)
    finally:
        conn.close()

    assert result.inserted is True
    assert result.token_intents[0]["display_symbol"] == "MIRROR"
    assert result.token_resolutions[0]["identity_status"] == "unresolved"
    assert result.token_resolutions[0]["asset_id"] is None


def test_ingest_gmgn_payload_writes_direct_dex_asset(tmp_path):
    conn, assets, ingest = open_ingest(tmp_path)
    try:
        snapshot = parse_gmgn_token_payload(
            {
                "tt": "ca",
                "t": {
                    "a": "So11111111111111111111111111111111111111112",
                    "c": "sol",
                    "s": "SOL",
                    "mc": "1000000",
                    "p": "150",
                },
            }
        )
        event = replace(
            make_event("event-1", text="$SOL rotation"),
            token_snapshot=snapshot,
        )
        result = ingest.ingest_event(event, is_watched=True)
        resolution = result.token_resolutions[0]
        market = assets.market_snapshot_at_or_before(resolution["asset_id"], event.received_at_ms)
    finally:
        conn.close()

    assert resolution["resolution_status"] == "direct"
    assert resolution["identity_status"] == "resolved"
    assert resolution["asset_id"] == "asset:dex:solana:So11111111111111111111111111111111111111112"
    assert market is not None
    assert market["provider"] == "gmgn_payload"
    assert market["price_usd"] == 150.0
    assert market["market_cap_usd"] == 1_000_000.0


def test_ingest_unknown_chain_ca_is_retained_as_unresolved_asset(tmp_path):
    conn, assets, ingest = open_ingest(tmp_path)
    try:
        result = ingest.ingest_event(
            make_event("event-1", text="watch 0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416"),
            is_watched=True,
        )
    finally:
        conn.close()

    assert result.token_intents[0]["address_hint"] == "0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416"
    assert result.token_resolutions[0]["identity_status"] == "unresolved"
    assert result.token_resolutions[0]["asset_id"] is None
