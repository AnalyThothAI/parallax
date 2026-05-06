from __future__ import annotations

from dataclasses import replace

from gmgn_twitter_intel.collector.gmgn_token_payload import parse_gmgn_token_payload
from gmgn_twitter_intel.pipeline.ingest_service import IngestService
from gmgn_twitter_intel.storage.asset_repository import AssetRepository
from gmgn_twitter_intel.storage.enrichment_repository import EnrichmentRepository
from gmgn_twitter_intel.storage.entity_repository import EntityRepository
from gmgn_twitter_intel.storage.evidence_repository import EvidenceRepository
from gmgn_twitter_intel.storage.signal_repository import SignalRepository
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate
from tests.test_postgres_repositories import make_event


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


def test_ingest_mirror_writes_unresolved_asset_attribution(tmp_path):
    conn, assets, ingest = open_ingest(tmp_path)
    try:
        result = ingest.ingest_event(make_event("event-1", text="$mirror is moving"), is_watched=True)
        rows = assets.events_for_symbol_mentions("MIRROR", limit=10)
    finally:
        conn.close()

    assert result.inserted is True
    assert result.asset_attributions[0]["attribution_status"] == "unresolved"
    assert result.asset_attributions[0]["asset_id"] == "asset:unresolved:MIRROR"
    assert rows[0]["event_id"] == "event-1"
    assert rows[0]["attribution_status"] == "unresolved"


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
        rows = assets.asset_attributions_for_symbol("SOL", limit=10)
    finally:
        conn.close()

    assert result.asset_attributions[0]["attribution_status"] == "direct"
    assert rows[0]["venue_type"] == "dex"
    assert rows[0]["chain"] == "solana"


def test_ingest_unknown_chain_ca_is_retained_as_unresolved_asset(tmp_path):
    conn, assets, ingest = open_ingest(tmp_path)
    try:
        result = ingest.ingest_event(
            make_event("event-1", text="watch 0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416"),
            is_watched=True,
        )
        rows = assets.asset_attributions_for_asset(
            "asset:unresolved_ca:0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416",
            limit=10,
        )
    finally:
        conn.close()

    assert result.asset_attributions[0]["attribution_status"] == "unresolved"
    assert rows[0]["asset_id"] == "asset:unresolved_ca:0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416"
