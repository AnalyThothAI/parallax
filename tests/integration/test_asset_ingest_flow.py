from __future__ import annotations

from dataclasses import replace

from gmgn_twitter_intel.app.runtime.repository_session import repositories_for_connection
from gmgn_twitter_intel.domains.evidence.services.ingest_service import IngestService
from gmgn_twitter_intel.domains.ingestion.types.gmgn_token_payload import parse_gmgn_token_payload
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
        identity_evidence=repos.identity_evidence,
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


def test_ingest_gmgn_payload_writes_identity_without_market_observation(tmp_path):
    conn, repos, ingest = open_ingest(tmp_path)
    address = "0x6982508145454ce325ddbe47a25d4ec3d2311933"
    try:
        snapshot = parse_gmgn_token_payload(
            {
                "tt": "ca",
                "t": {
                    "a": address,
                    "c": "eth",
                    "s": "PEPE",
                    "mc": "1000000",
                    "p": "0.01",
                },
            }
        )
        event = replace(
            make_event("event-gmgn-payload-no-market", text="$PEPE payload identity"),
            token_snapshot=snapshot,
        )
        result = ingest.ingest_event(event, is_watched=True)
        resolution = next(item for item in result.token_resolutions if item["resolution_status"] == "EXACT")
        asset = repos.registry.find_assets_by_address(chain_id="eth", address=address)[0]
        identity_evidence = repos.identity_evidence.list_identity_evidence(asset["asset_id"])
        enriched_events = repos.enriched_events.list_by_event_id(event.event_id)
        market_tick = repos.market_ticks.latest_at_or_before(
            target_type="chain_token",
            target_id=f"eip155:1:{address}",
            at_ms=event.received_at_ms,
            max_lag_ms=60_000,
        )
    finally:
        conn.close()

    assert resolution["resolution_status"] == "EXACT"
    assert resolution["target_type"] == "Asset"
    assert resolution["target_id"] == f"asset:eip155:1:erc20:{address}"
    assert any(item["evidence_kind"] == "gmgn_payload_exact" for item in identity_evidence)
    assert market_tick is None
    assert enriched_events[0]["target_type"] == "chain_token"
    assert enriched_events[0]["target_id"] == f"eip155:1:{address}"
    assert enriched_events[0]["capture_method"] == "unavailable"


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
        identity_evidence = repos.identity_evidence.list_identity_evidence(asset["asset_id"])
    finally:
        conn.close()

    assert resolution["resolution_status"] == "EXACT"
    assert resolution["target_type"] == "Asset"
    assert resolution["target_id"] == f"asset:eip155:1:erc20:{address}"
    assert asset["asset_id"] == resolution["target_id"]
    assert identity_evidence[0]["evidence_kind"] == "tweet_contract_mention"
    assert identity_evidence[0]["confidence"] == "mention_only"


def test_ingest_unknown_chain_ca_is_retained_as_unresolved_asset(tmp_path):
    conn, _, ingest = open_ingest(tmp_path)
    try:
        result = ingest.ingest_event(
            make_event("event-1", text="watch 0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416"),
            is_watched=True,
        )
    finally:
        conn.close()

    # address_hint is EIP-55 checksummed by entity_extractor.to_checksum_address (intentional canonicalisation).
    assert result.token_intents[0]["address_hint"] == "0xd0667d0618Dc9B6d2a0A55f428b47C64Bcf00416"
    assert result.token_resolutions[0]["resolution_status"] == "NIL"
    assert result.token_resolutions[0]["target_id"] is None
