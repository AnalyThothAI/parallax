from __future__ import annotations

import time
from dataclasses import replace

from gmgn_twitter_intel.domains.asset_market.repositories.asset_repository import AssetRepository
from gmgn_twitter_intel.domains.evidence.interfaces import Author, Content, Source, TwitterEvent
from gmgn_twitter_intel.domains.evidence.repositories.entity_repository import EntityRepository
from gmgn_twitter_intel.domains.evidence.repositories.evidence_repository import EvidenceRepository
from gmgn_twitter_intel.domains.evidence.services.ingest_service import IngestService
from gmgn_twitter_intel.domains.ingestion.types.gmgn_token_payload import parse_gmgn_token_payload
from gmgn_twitter_intel.domains.social_enrichment.repositories.enrichment_repository import EnrichmentRepository
from gmgn_twitter_intel.storage.signal_repository import SignalRepository
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate

TOKEN_ADDRESS = "0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416"


def make_event(
    event_id: str = "event-1",
    *,
    author_handle: str = "toly",
    text: str = "$PEPE mainnet 0x6982508145454ce325ddbe47a25d4ec3d2311933",
    received_at_ms: int | None = None,
    is_watched: bool = True,
) -> TwitterEvent:
    received_at_ms = received_at_ms if received_at_ms is not None else int(time.time() * 1000)
    return TwitterEvent(
        event_id=event_id,
        source=Source(
            provider="gmgn",
            transport="direct_ws",
            coverage="public_stream",
            channel="twitter_monitor_basic",
        ),
        action="tweet",
        original_action=None,
        tweet_id=event_id,
        internal_id=event_id,
        timestamp=received_at_ms // 1000,
        received_at_ms=received_at_ms,
        author=Author(handle=author_handle, name=author_handle, avatar=None, followers=100, tags=[]),
        content=Content(text=text, media=[]),
        reference=None,
        unfollow_target=None,
        avatar_change=None,
        bio_change=None,
        matched_handles=[author_handle] if is_watched else [],
        raw={"id": event_id},
    )


def make_token_event(
    event_id: str,
    *,
    symbol: str,
    address: str,
    received_at_ms: int,
    author_handle: str = "toly",
    is_watched: bool = True,
) -> TwitterEvent:
    snapshot = parse_gmgn_token_payload(
        {
            "tt": "ca",
            "t": {
                "a": address,
                "c": "eth",
                "mc": "60490.341996",
                "p": "1.0",
                "s": symbol,
                "liquidity": "250000",
                "holder_count": 10000,
                "pool": {"pool_address": f"pool-{symbol.lower()}"},
                "stat": {"volume_24h": "750000"},
            },
        }
    )
    return replace(
        make_event(
            event_id,
            author_handle=author_handle,
            text=f"${symbol} rotation",
            received_at_ms=received_at_ms,
            is_watched=is_watched,
        ),
        source=Source(
            provider="gmgn",
            transport="direct_ws",
            coverage="public_stream",
            channel="twitter_monitor_token",
        ),
        token_snapshot=snapshot,
    )


def open_runtime(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    migrate(conn)
    evidence = EvidenceRepository(conn)
    entities = EntityRepository(conn)
    signals = SignalRepository(conn)
    enrichment = EnrichmentRepository(conn)
    assets = AssetRepository(conn)
    ingest = IngestService(
        evidence=evidence,
        entities=entities,
        signals=signals,
        enrichment=enrichment,
    )
    return conn, ingest, signals, assets


def token_event(
    event_id: str,
    *,
    received_at_ms: int,
    author_handle: str = "traderpow",
    text: str = "$DOG",
) -> TwitterEvent:
    snapshot = parse_gmgn_token_payload(
        {
            "tt": "ca",
            "t": {
                "a": TOKEN_ADDRESS,
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
