from __future__ import annotations

from dataclasses import replace
from threading import RLock

import pytest

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


def token_event(
    event_id: str,
    *,
    symbol: str,
    address: str,
    chain: str = "sol",
    market_cap: str = "1000000",
    liquidity: str = "250000",
    holder_count: int = 10_000,
    received_at_ms: int,
    author_handle: str,
    text: str | None = None,
):
    snapshot = parse_gmgn_token_payload(
        {
            "tt": "ca",
            "t": {
                "a": address,
                "c": chain,
                "mc": market_cap,
                "p": "1.0",
                "p1": None,
                "s": symbol,
                "liquidity": liquidity,
                "holder_count": holder_count,
                "pool": {"pool_address": f"pool-{address[-6:]}"},
                "stat": {"volume_24h": str(float(liquidity) * 3)},
            },
        }
    )
    return replace(
        make_event(
            event_id,
            author_handle=author_handle,
            text=text or f"${symbol} structured token evidence",
            received_at_ms=received_at_ms,
        ),
        source=Source(
            provider="gmgn",
            transport="direct_ws",
            coverage="public_stream",
            channel="twitter_monitor_token",
        ),
        token_snapshot=snapshot,
    )


def test_symbol_mentions_before_ca_are_reattributed_to_explicit_token_candidate(tmp_path):
    conn, ingest, _, _, signals, tokens = open_runtime(tmp_path)
    try:
        base_ms = 1_700_000_000_000
        symbol_first = make_event(
            "event-dog-symbol-first",
            author_handle="watcher",
            text="$DOG early before payload",
            received_at_ms=base_ms + 1_000,
        )
        payload_later = token_event(
            "event-dog-payload-later",
            symbol="DOG",
            address="5UUH9RTDiSpq6HKS6bp4NdU9PNJpXRXuiw6ShBTBhgH2",
            market_cap="45000000",
            liquidity="2400000",
            received_at_ms=base_ms + 2_000,
            author_handle="gmgnfeed",
        )

        ingest.ingest_event(symbol_first, is_watched=True)
        ingest.ingest_event(payload_later, is_watched=False)

        item = TokenFlowService(signals=signals, tokens=tokens).token_flow(
            window="1h",
            limit=10,
            now_ms=base_ms + 60_000,
        )[0]
    finally:
        conn.close()

    assert item["identity"]["identity_key"] == "token:solana:5UUH9RTDiSpq6HKS6bp4NdU9PNJpXRXuiw6ShBTBhgH2"
    assert item["flow"]["mentions"] == 2
    assert item["flow"]["direct_mentions"] == 1
    assert item["flow"]["symbol_mentions"] == 1
    assert item["flow"]["weighted_mentions"] == pytest.approx(2.0, abs=0.3)
    assert item["attribution"]["avg_confidence"] >= 0.70
    assert item["attribution"]["selected_symbol_mentions"] == 1
    assert {event["event_id"] for event in item["evidence"]} == {
        "event-dog-symbol-first",
        "event-dog-payload-later",
    }


def test_ambiguous_symbol_flow_selects_best_market_candidate_without_symbol_bucket(tmp_path):
    conn, ingest, _, _, signals, tokens = open_runtime(tmp_path)
    try:
        base_ms = 1_700_000_000_000
        target_address = "5UUH9RTDiSpq6HKS6bp4NdU9PNJpXRXuiw6ShBTBhgH2"
        weak_address = "DkVsvbzz39yx8hawbxfWubJKpZ4cdc4SPtPf5TZQpump"
        ingest.ingest_event(
            token_event(
                "event-troll-target-payload",
                symbol="TROLL",
                address=target_address,
                market_cap="45151685.6",
                liquidity="2442798.17",
                holder_count=51_064,
                received_at_ms=base_ms + 1_000,
                author_handle="voicea",
            ),
            is_watched=False,
        )
        ingest.ingest_event(
            token_event(
                "event-troll-weak-payload",
                symbol="TROLL",
                address=weak_address,
                market_cap="12000",
                liquidity="800",
                holder_count=45,
                received_at_ms=base_ms + 2_000,
                author_handle="voiceb",
            ),
            is_watched=False,
        )
        for index in range(6):
            ingest.ingest_event(
                make_event(
                    f"event-troll-symbol-{index}",
                    author_handle=f"symbolvoice{index}",
                    text=f"$TROLL symbol-only chatter {index}",
                    received_at_ms=base_ms + 10_000 + index,
                ),
                is_watched=index == 0,
            )

        items = TokenFlowService(signals=signals, tokens=tokens).token_flow(
            window="1h",
            limit=10,
            now_ms=base_ms + 60_000,
        )
    finally:
        conn.close()

    assert all(not item["identity"]["identity_key"].startswith("symbol:") for item in items)
    target = next(item for item in items if item["identity"]["address"] == target_address)
    weak = next(item for item in items if item["identity"]["address"] == weak_address)
    assert target["flow"]["direct_mentions"] == 1
    assert target["flow"]["symbol_mentions"] == 6
    assert target["flow"]["mentions"] == 7
    assert target["attribution"]["candidate_count"] == 2
    assert "market_quality_lead" in target["attribution"]["reasons"]
    assert weak["flow"]["mentions"] == 1
    assert weak["flow"]["symbol_mentions"] == 0


def test_close_ambiguous_symbol_candidates_are_not_counted_as_flow(tmp_path):
    conn, ingest, _, _, signals, tokens = open_runtime(tmp_path)
    try:
        base_ms = 1_700_000_000_000
        for index, address in enumerate(
            [
                "5UUH9RTDiSpq6HKS6bp4NdU9PNJpXRXuiw6ShBTBhgH2",
                "DkVsvbzz39yx8hawbxfWubJKpZ4cdc4SPtPf5TZQpump",
            ]
        ):
            ingest.ingest_event(
                token_event(
                    f"event-dupe-payload-{index}",
                    symbol="DUPE",
                    address=address,
                    market_cap="1000000",
                    liquidity="100000",
                    holder_count=1_000,
                    received_at_ms=base_ms + index,
                    author_handle=f"voice{index}",
                ),
                is_watched=False,
            )
        ingest.ingest_event(
            make_event(
                "event-dupe-symbol",
                author_handle="symbolvoice",
                text="$DUPE unresolved close race",
                received_at_ms=base_ms + 10_000,
            ),
            is_watched=True,
        )

        items = TokenFlowService(signals=signals, tokens=tokens).token_flow(
            window="1h",
            limit=10,
            now_ms=base_ms + 60_000,
        )
        attribution_rows = conn.execute(
            """
            SELECT attribution_status, attribution_weight
            FROM event_token_attributions
            WHERE event_id = 'event-dupe-symbol'
            ORDER BY attribution_rank
            """
        ).fetchall()
    finally:
        conn.close()

    assert sorted(item["flow"]["mentions"] for item in items) == [1, 1]
    assert {row["attribution_status"] for row in attribution_rows} == {"ambiguous"}
    assert {row["attribution_weight"] for row in attribution_rows} == {0.0}


def test_search_reports_total_returned_and_has_more_for_limited_results(tmp_path):
    conn, ingest, evidence, entities, signals, _ = open_runtime(tmp_path)
    try:
        base_ms = 1_700_000_000_000
        for index in range(6):
            ingest.ingest_event(
                make_event(
                    f"event-dog-search-{index}",
                    author_handle=f"voice{index}",
                    text=f"$DOG search evidence {index}",
                    received_at_ms=base_ms + index,
                ),
                is_watched=index % 2 == 0,
            )

        results = SearchService(evidence=evidence, entities=entities, signals=signals).search("$DOG", limit=3)
    finally:
        conn.close()

    assert len(results.items) == 3
    assert results.total_count == 6
    assert results.returned_count == 3
    assert results.has_more is True
