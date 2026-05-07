from __future__ import annotations

from dataclasses import replace

from gmgn_twitter_intel.collector.gmgn_token_payload import parse_gmgn_token_payload
from gmgn_twitter_intel.pipeline.ingest_service import IngestService
from gmgn_twitter_intel.storage.repository_session import repositories_for_connection
from tests.factories import make_event
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate


def open_ingest(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    migrate(conn)
    repos = repositories_for_connection(conn)
    ingest = IngestService(
        evidence=repos.evidence,
        entities=repos.entities,
        signals=repos.signals,
        enrichment=repos.enrichment,
        registry=repos.registry,
        price_observations=repos.price_observations,
        token_intent_lookup=repos.token_intent_lookup,
    )
    return conn, repos, ingest


def test_ingest_mirror_writes_unresolved_token_intent(tmp_path):
    conn, _, ingest = open_ingest(tmp_path)
    try:
        result = ingest.ingest_event(make_event("event-1", text="$mirror is moving"), is_watched=True)
    finally:
        conn.close()

    assert result.inserted is True
    assert result.token_intents[0]["display_symbol"] == "MIRROR"
    assert result.token_resolutions[0]["resolution_status"] == "NIL"
    assert result.token_resolutions[0]["target_id"] is None


def test_ingest_gmgn_payload_writes_direct_dex_asset(tmp_path):
    conn, repos, ingest = open_ingest(tmp_path)
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
        market = repos.price_observations.latest_for_subject(
            subject_type="Asset",
            subject_id=resolution["target_id"],
            at_or_before_ms=event.received_at_ms,
        )
    finally:
        conn.close()

    assert resolution["resolution_status"] == "EXACT"
    assert resolution["target_type"] == "Asset"
    assert resolution["target_id"] == "asset:solana:token:So11111111111111111111111111111111111111112"
    assert market is not None
    assert market["provider"] == "gmgn_payload"
    assert market["price_usd"] == 150.0
    assert market["market_cap_usd"] == 1_000_000.0


def test_ingest_chain_ca_from_gmgn_url_writes_exact_registry_asset(tmp_path):
    conn, repos, ingest = open_ingest(tmp_path)
    address = "0x44b28991b167582f18ba0259e0173176ca125505"
    try:
        result = ingest.ingest_event(
            make_event("event-upic", text=f"https://gmgn.ai/eth/token/{address}"),
            is_watched=True,
        )
        resolution = result.token_resolutions[0]
        asset = repos.registry.find_assets_by_address(chain_id="eth", address=address)[0]
    finally:
        conn.close()

    assert resolution["resolution_status"] == "EXACT"
    assert resolution["target_type"] == "Asset"
    assert resolution["target_id"] == f"asset:eip155:1:erc20:{address}"
    assert asset["asset_id"] == resolution["target_id"]
    assert asset["primary_source"] == "tweet_ca"


def test_ingest_unknown_chain_ca_is_retained_as_unresolved_asset(tmp_path):
    conn, _, ingest = open_ingest(tmp_path)
    try:
        result = ingest.ingest_event(
            make_event("event-1", text="watch 0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416"),
            is_watched=True,
        )
    finally:
        conn.close()

    assert result.token_intents[0]["address_hint"] == "0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416"
    assert result.token_resolutions[0]["resolution_status"] == "NIL"
    assert result.token_resolutions[0]["target_id"] is None
