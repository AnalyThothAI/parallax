from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from gmgn_twitter_intel.app.runtime.bootstrap import _PooledIngestStore
from gmgn_twitter_intel.app.runtime.providers_wiring import AssetMarketProviders
from gmgn_twitter_intel.app.runtime.repository_session import repositories_for_connection
from gmgn_twitter_intel.domains.asset_market.providers import DexTokenQuote
from tests.factories import make_event
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate


def test_ingest_chain_event_commits_enriched_event_and_market_tick_together(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    migrate(conn)
    event = make_event(
        "event-inline-market",
        text="https://gmgn.ai/eth/token/0x6982508145454ce325ddbe47a25d4ec3d2311933 is moving",
        received_at_ms=1_700_000_000_000,
    )
    provider = _DexQuoteProvider(
        [
            DexTokenQuote(
                chain_id="eip155:1",
                address="0x6982508145454ce325ddbe47a25d4ec3d2311933",
                observed_at_ms=event.received_at_ms + 250,
                price_usd=0.0123,
                liquidity_usd=123_000.0,
                market_cap_usd=1_000_000.0,
                volume_24h_usd=456_000.0,
                raw={"source": "fake"},
            )
        ]
    )
    store = _PooledIngestStore(
        _SingleConnectionDB(conn),
        providers=AssetMarketProviders(dex_quote_market=provider),
        now_ms=lambda: event.received_at_ms + 500,
    )
    try:
        result = store.ingest_event(event, is_watched=True)
        event_row = conn.execute("SELECT * FROM events WHERE event_id = %s", (event.event_id,)).fetchone()
        enriched_rows = conn.execute("SELECT * FROM enriched_events WHERE event_id = %s", (event.event_id,)).fetchall()
        market_rows = conn.execute("SELECT * FROM market_ticks").fetchall()
    finally:
        conn.close()

    assert result.inserted is True
    assert event_row is not None
    assert len(market_rows) == 1
    assert len(enriched_rows) == 1
    assert enriched_rows[0]["tick_id"] == market_rows[0]["tick_id"]
    assert enriched_rows[0]["capture_method"] == "tier3_inline"
    assert enriched_rows[0]["target_type"] == "chain_token"
    assert enriched_rows[0]["target_id"] == "eip155:1:0x6982508145454ce325ddbe47a25d4ec3d2311933"
    assert market_rows[0]["target_type"] == "chain_token"


def test_ingest_chain_event_with_null_price_writes_unavailable_capture_without_tick(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    migrate(conn)
    event = make_event(
        "event-unavailable-market",
        text="https://gmgn.ai/eth/token/0x6982508145454ce325ddbe47a25d4ec3d2311933 has no quote",
        received_at_ms=1_700_000_010_000,
    )
    provider = _DexQuoteProvider(
        [
            DexTokenQuote(
                chain_id="eip155:1",
                address="0x6982508145454ce325ddbe47a25d4ec3d2311933",
                observed_at_ms=event.received_at_ms,
                price_usd=None,
                raw={"source": "fake-null"},
            )
        ]
    )
    store = _PooledIngestStore(
        _SingleConnectionDB(conn),
        providers=AssetMarketProviders(dex_quote_market=provider),
        now_ms=lambda: event.received_at_ms + 500,
    )
    try:
        result = store.ingest_event(event, is_watched=True)
        enriched_rows = conn.execute("SELECT * FROM enriched_events WHERE event_id = %s", (event.event_id,)).fetchall()
        market_rows = conn.execute("SELECT * FROM market_ticks").fetchall()
    finally:
        conn.close()

    assert result.inserted is True
    assert len(market_rows) == 0
    assert len(enriched_rows) == 1
    assert enriched_rows[0]["capture_method"] == "unavailable"
    assert enriched_rows[0]["capture_reason"] == "no_market_data"
    assert enriched_rows[0]["tick_id"] is None


class _DexQuoteProvider:
    def __init__(self, quotes: list[DexTokenQuote]) -> None:
        self.calls = []
        self._quotes = quotes

    def token_quotes(self, tokens):
        self.calls.append(tokens)
        return self._quotes


class _SingleConnectionDB:
    def __init__(self, conn) -> None:
        self.conn = conn

    @contextmanager
    def worker_session(self, name: str) -> Iterator:
        yield repositories_for_connection(self.conn)
