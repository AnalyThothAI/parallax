from __future__ import annotations

from dataclasses import replace

from gmgn_twitter_intel.collector.gmgn_token_payload import parse_gmgn_token_payload
from gmgn_twitter_intel.models import Source
from gmgn_twitter_intel.pipeline.ingest_service import IngestService
from gmgn_twitter_intel.retrieval.token_flow_service import TokenFlowService
from gmgn_twitter_intel.storage.enrichment_repository import EnrichmentRepository
from gmgn_twitter_intel.storage.entity_repository import EntityRepository
from gmgn_twitter_intel.storage.evidence_repository import EvidenceRepository
from gmgn_twitter_intel.storage.market_observation_repository import MarketObservationRepository
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
    observations = MarketObservationRepository(conn)
    ingest = IngestService(
        evidence=evidence,
        entities=entities,
        signals=signals,
        enrichment=enrichment,
        tokens=tokens,
        market_observations=observations,
    )
    return conn, ingest


def token_payload_event(
    event_id: str,
    *,
    symbol: str = "DOG",
    address: str = "0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416",
    chain: str = "eth",
    received_at_ms: int = 1_700_000_000_000,
):
    snapshot = parse_gmgn_token_payload(
        {
            "tt": "ca",
            "t": {
                "a": address,
                "c": chain,
                "mc": "60490.341996",
                "p": "1.0",
                "p1": None,
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
            author_handle="gmgnfeed",
            text=f"${symbol} payload",
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


def observation_rows(conn):
    return [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM token_market_observations ORDER BY target_received_at_ms, event_id"
        ).fetchall()
    ]


def test_ingest_enqueues_pending_observation_for_direct_token_payload_without_market_http(tmp_path):
    conn, ingest = open_runtime(tmp_path)
    try:
        result = ingest.ingest_event(
            token_payload_event("event-direct", received_at_ms=1_700_000_000_000),
            is_watched=True,
        )
        rows = observation_rows(conn)
    finally:
        conn.close()

    assert result.inserted is True
    assert len(rows) == 1
    assert rows[0]["event_id"] == "event-direct"
    assert rows[0]["status"] == "pending"
    assert rows[0]["target_received_at_ms"] == 1_700_000_000_000


def test_basic_stream_evm_ca_with_chain_hint_enqueues_pending_observation(tmp_path):
    conn, ingest = open_runtime(tmp_path)
    try:
        result = ingest.ingest_event(
            make_event(
                "event-basic-bsc-ca",
                text=(
                    "币安好友 $EDGE achieved 5.77x CA: "
                    "0x5aec6340fc1e27893a4c966fae624fc6d3f9ffff Get more: BSC"
                ),
                received_at_ms=1_700_000_000_000,
            ),
            is_watched=False,
        )
        rows = observation_rows(conn)
        attribution = conn.execute(
            "SELECT * FROM event_token_attributions WHERE event_id = %s",
            ("event-basic-bsc-ca",),
        ).fetchone()
        flow = TokenFlowService(signals=ingest.signals, tokens=ingest.tokens).token_flow(
            window="5m",
            limit=10,
            scope="all",
            now_ms=1_700_000_300_000,
        )
    finally:
        conn.close()

    assert result.inserted is True
    assert len(rows) == 1
    assert rows[0]["event_id"] == "event-basic-bsc-ca"
    assert rows[0]["chain"] == "bsc"
    assert rows[0]["symbol"] == "EDGE"
    assert attribution["chain"] == "bsc"
    assert attribution["attribution_status"] == "direct"
    assert flow[0]["identity"]["chain"] == "bsc"
    assert flow[0]["identity"]["symbol"] == "EDGE"


def test_symbol_only_event_gets_observation_after_later_selected_attribution(tmp_path):
    conn, ingest = open_runtime(tmp_path)
    try:
        ingest.ingest_event(
            make_event("event-symbol-first", text="$DOG early", received_at_ms=1_700_000_000_000),
            is_watched=True,
        )
        assert observation_rows(conn) == []

        ingest.ingest_event(
            token_payload_event("event-token-later", received_at_ms=1_700_000_060_000),
            is_watched=True,
        )
        rows = observation_rows(conn)
    finally:
        conn.close()

    assert [row["event_id"] for row in rows] == ["event-symbol-first", "event-token-later"]
    assert {row["status"] for row in rows} == {"pending"}


def test_unresolved_symbol_only_event_does_not_enqueue_observation(tmp_path):
    conn, ingest = open_runtime(tmp_path)
    try:
        ingest.ingest_event(
            make_event("event-unknown-symbol", text="$UNKNOWN ticker only", received_at_ms=1_700_000_000_000),
            is_watched=True,
        )
        rows = observation_rows(conn)
    finally:
        conn.close()

    assert rows == []


def test_ambiguous_symbol_event_does_not_enqueue_observation(tmp_path):
    conn, ingest = open_runtime(tmp_path)
    try:
        ingest.ingest_event(
            token_payload_event(
                "event-dog-eth",
                address="0xd0667d0618dc9b6d2a0a55f428b47c64bcf00416",
                received_at_ms=1_700_000_000_000,
            ),
            is_watched=True,
        )
        ingest.ingest_event(
            token_payload_event(
                "event-dog-base",
                address="0x4200000000000000000000000000000000000006",
                chain="base",
                received_at_ms=1_700_000_060_000,
            ),
            is_watched=True,
        )
        direct_observation_count = len(observation_rows(conn))

        ingest.ingest_event(
            make_event("event-dog-ambiguous", text="$DOG ambiguous", received_at_ms=1_700_000_120_000),
            is_watched=True,
        )
        rows = observation_rows(conn)
    finally:
        conn.close()

    assert len(rows) == direct_observation_count
    assert "event-dog-ambiguous" not in {row["event_id"] for row in rows}
