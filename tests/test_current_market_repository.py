from __future__ import annotations

from gmgn_twitter_intel.domains.asset_market.repositories.current_market_repository import CurrentMarketRepository
from gmgn_twitter_intel.domains.asset_market.repositories.price_observation_repository import PriceObservationRepository
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate

SUBJECT_TYPE = "Asset"
SUBJECT_ID = "asset:solana:token:TROLL"


def test_current_market_sql_bounds_field_reads_to_read_time():
    conn = _CaptureConnection()

    CurrentMarketRepository(conn).current_for_subjects(
        [{"target_type": SUBJECT_TYPE, "target_id": SUBJECT_ID}],
        now_ms=1_700_086_430_000,
    )

    assert conn.params == [SUBJECT_TYPE, SUBJECT_ID, 1_700_086_430_000]
    assert "clock(now_ms) AS (VALUES (%s))" in conn.sql
    assert conn.sql.count("observed_at_ms <= clock.now_ms") == 6


def test_current_market_keeps_price_fresh_while_market_cap_stale(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        observations = PriceObservationRepository(conn)
        observations.insert_observation(
            provider="okx_dex_search",
            pricefeed_id="feed-search",
            observed_at_ms=1_700_000_000_000,
            subject_type=SUBJECT_TYPE,
            subject_id=SUBJECT_ID,
            price_usd=0.051,
            price_basis="usd",
            market_cap_usd=51_000_000,
            liquidity_usd=3_000_000,
            holders=52_000,
        )
        observations.insert_observation(
            provider="okx_dex_price",
            pricefeed_id="feed-price",
            observed_at_ms=1_700_086_400_000,
            subject_type=SUBJECT_TYPE,
            subject_id=SUBJECT_ID,
            price_usd=0.104,
            price_basis="usd",
            market_cap_usd=51_000_000,
            liquidity_usd=3_000_000,
            holders=52_000,
        )
        snapshot = CurrentMarketRepository(conn).current_for_subjects(
            [{"target_type": SUBJECT_TYPE, "target_id": SUBJECT_ID}],
            now_ms=1_700_086_430_000,
        )[(SUBJECT_TYPE, SUBJECT_ID)]
    finally:
        conn.close()

    assert snapshot["fields"]["price_usd"]["value"] == 0.104
    assert snapshot["fields"]["price_usd"]["status"] == "fresh"
    assert snapshot["fields"]["market_cap_usd"]["value"] == 51_000_000
    assert snapshot["fields"]["market_cap_usd"]["status"] == "stale"
    assert snapshot["fields"]["market_cap_usd"]["observed_at_ms"] == 1_700_000_000_000
    assert snapshot["fields"]["market_cap_usd"]["provider"] == "okx_dex_search"
    assert snapshot["market_status"] == "partial"


def test_current_market_updates_market_cap_from_full_metadata_provider(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        observations = PriceObservationRepository(conn)
        observations.insert_observation(
            provider="okx_dex_search",
            pricefeed_id="feed-search",
            observed_at_ms=1_700_086_420_000,
            subject_type=SUBJECT_TYPE,
            subject_id=SUBJECT_ID,
            price_usd=0.104,
            price_basis="usd",
            market_cap_usd=100_000_000,
            liquidity_usd=4_100_000,
            holders=55_000,
        )
        snapshot = CurrentMarketRepository(conn).current_for_subjects(
            [{"target_type": SUBJECT_TYPE, "target_id": SUBJECT_ID}],
            now_ms=1_700_086_430_000,
        )[(SUBJECT_TYPE, SUBJECT_ID)]
    finally:
        conn.close()

    assert snapshot["fields"]["market_cap_usd"]["value"] == 100_000_000
    assert snapshot["fields"]["market_cap_usd"]["status"] == "fresh"
    assert snapshot["market_status"] == "fresh"


def test_current_market_reads_okx_dex_ws_price_info_as_metadata_provider(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        observations = PriceObservationRepository(conn)
        observations.insert_observation(
            provider="okx_dex_search",
            pricefeed_id="feed-search",
            observed_at_ms=1_700_000_000_000,
            subject_type=SUBJECT_TYPE,
            subject_id=SUBJECT_ID,
            price_usd=0.051,
            price_basis="usd",
            market_cap_usd=51_000_000,
            liquidity_usd=3_000_000,
            holders=52_000,
        )
        observations.insert_observation(
            provider="okx_dex_ws_price_info",
            pricefeed_id="feed-ws",
            observed_at_ms=1_700_086_420_000,
            subject_type=SUBJECT_TYPE,
            subject_id=SUBJECT_ID,
            price_usd=0.111,
            price_basis="usd",
            market_cap_usd=110_900_000,
            liquidity_usd=4_820_000,
            volume_24h_usd=27_400_000,
            holders=57_141,
        )
        snapshot = CurrentMarketRepository(conn).current_for_subjects(
            [{"target_type": SUBJECT_TYPE, "target_id": SUBJECT_ID}],
            now_ms=1_700_086_430_000,
        )[(SUBJECT_TYPE, SUBJECT_ID)]
    finally:
        conn.close()

    assert snapshot["fields"]["price_usd"]["value"] == 0.111
    assert snapshot["fields"]["market_cap_usd"]["value"] == 110_900_000
    assert snapshot["fields"]["liquidity_usd"]["value"] == 4_820_000
    assert snapshot["fields"]["volume_24h_usd"]["value"] == 27_400_000
    assert snapshot["fields"]["holders"]["value"] == 57_141
    assert snapshot["fields"]["market_cap_usd"]["provider"] == "okx_dex_ws_price_info"
    assert snapshot["market_status"] == "fresh"


def test_current_market_ignores_observations_after_read_time(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        observations = PriceObservationRepository(conn)
        observations.insert_observation(
            provider="okx_dex_search",
            pricefeed_id="feed-search-before",
            observed_at_ms=1_700_000_000_000,
            subject_type=SUBJECT_TYPE,
            subject_id=SUBJECT_ID,
            price_usd=0.051,
            price_basis="usd",
            market_cap_usd=51_000_000,
            liquidity_usd=3_000_000,
            holders=52_000,
        )
        observations.insert_observation(
            provider="okx_dex_search",
            pricefeed_id="feed-search-future",
            observed_at_ms=1_700_086_440_000,
            subject_type=SUBJECT_TYPE,
            subject_id=SUBJECT_ID,
            price_usd=0.104,
            price_basis="usd",
            market_cap_usd=100_000_000,
            liquidity_usd=4_100_000,
            holders=55_000,
        )
        snapshot = CurrentMarketRepository(conn).current_for_subjects(
            [{"target_type": SUBJECT_TYPE, "target_id": SUBJECT_ID}],
            now_ms=1_700_086_430_000,
        )[(SUBJECT_TYPE, SUBJECT_ID)]
    finally:
        conn.close()

    assert snapshot["fields"]["price_usd"]["value"] == 0.051
    assert snapshot["fields"]["market_cap_usd"]["value"] == 51_000_000
    assert snapshot["fields"]["market_cap_usd"]["observed_at_ms"] == 1_700_000_000_000
    assert snapshot["fields"]["market_cap_usd"]["status"] == "stale"


def test_current_market_reads_cex_ticker_fields(tmp_path):
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        observations = PriceObservationRepository(conn)
        observations.insert_observation(
            provider="okx_cex",
            pricefeed_id="feed-btc",
            observed_at_ms=1_700_086_420_000,
            subject_type="CexToken",
            subject_id="cex_token:BTC",
            price_usd=70_000,
            price_quote=70_000,
            quote_symbol="USDT",
            price_basis="quote_as_usd",
            volume_24h_usd=1_000_000,
            open_interest_usd=2_000_000,
        )
        snapshot = CurrentMarketRepository(conn).current_for_subjects(
            [{"target_type": "CexToken", "target_id": "cex_token:BTC"}],
            now_ms=1_700_086_430_000,
        )[("CexToken", "cex_token:BTC")]
    finally:
        conn.close()

    assert snapshot["fields"]["price_usd"]["status"] == "fresh"
    assert snapshot["fields"]["volume_24h_usd"]["value"] == 1_000_000
    assert snapshot["fields"]["open_interest_usd"]["value"] == 2_000_000
    assert snapshot["market_status"] == "fresh"


class _CaptureConnection:
    sql: str
    params: list[object]

    def execute(self, sql: str, params: list[object]) -> _CaptureConnection:
        self.sql = sql
        self.params = params
        return self

    def fetchall(self) -> list[dict[str, object]]:
        return []
