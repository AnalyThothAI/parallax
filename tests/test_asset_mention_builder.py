from __future__ import annotations

from gmgn_twitter_intel.models import TokenSnapshot
from gmgn_twitter_intel.pipeline.asset_mention_builder import build_asset_mentions
from gmgn_twitter_intel.pipeline.entity_extractor import ExtractedEntity


def test_cashtag_creates_asset_mention():
    entity = ExtractedEntity(
        entity_type="symbol",
        raw_value="$mirror",
        normalized_value="mirror",
        chain=None,
        token_resolution_status="unresolved_symbol",
        confidence=0.8,
        source="cashtag",
    )

    mentions = build_asset_mentions(
        event_id="event-1",
        entities=[entity],
        token_snapshot=None,
        created_at_ms=1_700_000_000_000,
    )

    assert len(mentions) == 1
    assert mentions[0].mention_type == "cashtag"
    assert mentions[0].raw_value == "$mirror"
    assert mentions[0].normalized_symbol == "MIRROR"
    assert mentions[0].chain_hint is None
    assert mentions[0].address_hint is None


def test_ca_creates_asset_mention_without_converting_unknown_chain_to_tradeable_chain():
    entity = ExtractedEntity(
        entity_type="ca",
        raw_value="0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416",
        normalized_value="0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416",
        chain="evm_unknown",
        token_resolution_status="unresolved_chain_ca",
        confidence=1.0,
        source="regex",
    )

    mentions = build_asset_mentions(
        event_id="event-1",
        entities=[entity],
        token_snapshot=None,
        created_at_ms=1_700_000_000_000,
    )

    assert mentions[0].mention_type == "ca"
    assert mentions[0].chain_hint is None
    assert mentions[0].address_hint == "0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416"


def test_plain_word_without_entity_is_not_asset_mention():
    mentions = build_asset_mentions(
        event_id="event-1",
        entities=[],
        token_snapshot=None,
        created_at_ms=1_700_000_000_000,
    )

    assert mentions == []


def test_gmgn_payload_creates_direct_payload_mention():
    snapshot = TokenSnapshot(
        address="So11111111111111111111111111111111111111112",
        chain="solana",
        symbol="SOL",
        market_cap=1_000_000.0,
        price=150.0,
        previous_price=None,
        icon_url=None,
        trigger_type="ca",
        raw={"symbol": "SOL"},
    )

    mentions = build_asset_mentions(
        event_id="event-1",
        entities=[],
        token_snapshot=snapshot,
        created_at_ms=1_700_000_000_000,
    )

    assert mentions[0].mention_type == "gmgn_payload"
    assert mentions[0].normalized_symbol == "SOL"
    assert mentions[0].chain_hint == "solana"
    assert mentions[0].address_hint == "So11111111111111111111111111111111111111112"


def test_asset_mentions_are_deduped_by_structural_identity():
    entity = ExtractedEntity(
        entity_type="symbol",
        raw_value="$MIRROR",
        normalized_value="MIRROR",
        chain=None,
        token_resolution_status="unresolved_symbol",
        confidence=0.8,
        source="cashtag",
    )

    mentions = build_asset_mentions(
        event_id="event-1",
        entities=[entity, entity],
        token_snapshot=None,
        created_at_ms=1_700_000_000_000,
    )

    assert len(mentions) == 1
