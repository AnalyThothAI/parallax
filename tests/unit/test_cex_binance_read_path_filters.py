from __future__ import annotations

import re
from typing import Any

from gmgn_twitter_intel.domains.account_quality.repositories.account_quality_repository import (
    AccountQualityRepository,
)
from gmgn_twitter_intel.domains.asset_market.repositories.registry_repository import RegistryRepository
from gmgn_twitter_intel.domains.token_intel.queries.event_token_projection_query import (
    EventTokenProjectionQuery,
)
from gmgn_twitter_intel.domains.token_intel.queries.token_radar_target_feature_query import (
    TokenRadarSourceRequest,
    TokenRadarTargetFeatureBatchQuery,
)
from gmgn_twitter_intel.domains.token_intel.repositories.token_target_repository import TokenTargetRepository


def test_registry_preferred_cex_reads_are_binance_usdt_swap_only() -> None:
    conn = RecordingConn()
    repo = RegistryRepository(conn)

    repo.cex_pricefeed_for_token(cex_token_id="cex_token:BTC", pricefeed_id="pricefeed:old-okx")
    repo.find_preferred_cex_pricefeed("BTC")

    assert len(conn.sql_calls) == 3
    for sql in conn.sql_calls:
        _assert_binance_usdt_swap_only(sql)
        _assert_no_legacy_cex_preference_ordering(sql)


def test_registry_ranked_live_market_targets_cex_payloads_are_binance_usdt_swap_only() -> None:
    conn = RecordingConn()

    RegistryRepository(conn).ranked_live_market_targets(
        projection_version="token-radar-v13-social-attention",
        since_ms=1_700_000_000_000,
        limit=25,
    )

    sql = conn.sql_calls[-1]
    _assert_binance_usdt_swap_only(sql)
    assert re.search(r"selected_pricefeed\.provider\s*=\s*'binance'", sql)
    assert "COALESCE(selected_pricefeed.provider, preferred_pricefeed.provider, 'okx')" not in sql
    _assert_no_legacy_cex_preference_ordering(sql)


def test_registry_exact_cex_lookup_still_requires_a_matching_exchange_row() -> None:
    conn = RecordingConn(rows=[])

    row = RegistryRepository(conn).find_cex_pricefeed(exchange="okx", native_market_id="BTC-USDT")

    assert row is None
    assert conn.params_calls[-1] == ("okx", "BTC-USDT")


def test_token_radar_target_feature_preferred_cex_read_is_binance_usdt_swap_only() -> None:
    conn = RecordingConn()

    TokenRadarTargetFeatureBatchQuery(conn).source_rows_for_requests(
        [
            TokenRadarSourceRequest(
                request_key="request-1",
                target_type_key="CexToken",
                identity_id="cex_token:BTC",
                window="1h",
                scope="all",
                analysis_since_ms=1,
                score_since_ms=1,
                now_ms=2,
            )
        ]
    )

    _assert_binance_usdt_swap_only(conn.sql_calls[-1])
    _assert_no_legacy_cex_preference_ordering(conn.sql_calls[-1])
    _assert_legacy_cex_event_tick_is_rejected(conn.sql_calls[-1], tick_alias="event_price_tick")


def test_event_token_projection_preferred_cex_read_is_binance_usdt_swap_only() -> None:
    conn = RecordingConn()

    EventTokenProjectionQuery(conn).for_events(("event-1",))

    _assert_binance_usdt_swap_only(conn.sql_calls[-1])
    _assert_no_legacy_cex_preference_ordering(conn.sql_calls[-1])
    _assert_legacy_cex_event_tick_is_rejected(conn.sql_calls[-1], tick_alias="event_tick")


def test_token_target_repository_cex_reads_are_binance_usdt_swap_only() -> None:
    conn = RecordingConn()
    repo = TokenTargetRepository(conn)

    repo.target_identity(target_type="CexToken", target_id="cex_token:BTC")
    repo.latest_market_tick(target_type="CexToken", target_id="cex_token:BTC")
    repo.timeline_rows(
        target_type="CexToken",
        target_id="cex_token:BTC",
        since_ms=1,
        watched_only=False,
        limit=25,
    )

    assert len(conn.sql_calls) == 3
    for sql in conn.sql_calls:
        _assert_binance_usdt_swap_only(sql)
        _assert_no_legacy_cex_preference_ordering(sql)
    _assert_token_target_timeline_rejects_legacy_cex_event_tick(conn.sql_calls[-1])


def test_account_quality_cex_market_target_read_is_binance_usdt_swap_only() -> None:
    conn = RecordingConn()

    AccountQualityRepository(conn).account_token_rows(resolver_policy_version="resolver-v1", limit=25)

    _assert_binance_usdt_swap_only(conn.sql_calls[-1])
    _assert_no_legacy_cex_preference_ordering(conn.sql_calls[-1])


class RecordingConn:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.rows = rows or []
        self.sql_calls: list[str] = []
        self.params_calls: list[Any] = []

    def execute(self, sql: str, params: Any = None) -> RecordingConn:
        self.sql_calls.append(str(sql))
        self.params_calls.append(params)
        return self

    def fetchone(self) -> dict[str, Any] | None:
        return self.rows[0] if self.rows else None

    def fetchall(self) -> list[dict[str, Any]]:
        return self.rows


def _assert_binance_usdt_swap_only(sql: str) -> None:
    assert re.search(r"(?:price_feeds|selected_pricefeed|preferred_pricefeed)?\.?provider\s*=\s*'binance'", sql)
    assert re.search(r"(?:price_feeds|selected_pricefeed|preferred_pricefeed)?\.?feed_type\s*=\s*'cex_swap'", sql)
    assert re.search(r"(?:price_feeds|selected_pricefeed|preferred_pricefeed)?\.?quote_symbol\s*=\s*'USDT'", sql)
    assert re.search(r"(?:price_feeds|selected_pricefeed|preferred_pricefeed)?\.?status\s*=\s*'canonical'", sql)


def _assert_no_legacy_cex_preference_ordering(sql: str) -> None:
    assert "feed_type LIKE 'cex_%%'" not in sql
    assert "COALESCE(tir.pricefeed_id, preferred_price_feed.pricefeed_id)" not in sql
    assert "COALESCE(token_intent_resolutions.pricefeed_id, preferred_price_feed.pricefeed_id)" not in sql
    assert "feed_type = 'cex_spot'" not in sql
    assert "quote_symbol = 'USD'" not in sql
    assert "quote_symbol = 'USDC'" not in sql
    assert "price_feeds.status IN ('candidate', 'canonical')" not in sql
    assert "selected_pricefeed.status IN ('candidate', 'canonical')" not in sql


def _assert_legacy_cex_event_tick_is_rejected(sql: str, *, tick_alias: str) -> None:
    assert f"{tick_alias}.target_type = market_target.target_type" in sql
    assert f"{tick_alias}.target_id = market_target.target_id" in sql
    assert f"{tick_alias}.source_provider = CASE" in sql
    assert "THEN 'binance_cex_rest'" in sql


def _assert_token_target_timeline_rejects_legacy_cex_event_tick(sql: str) -> None:
    assert "WHEN tir.target_type = 'CexToken' THEN 'cex_symbol'" in sql
    assert "WHEN tir.target_type = 'CexToken' THEN price_feeds.provider || ':' || price_feeds.native_market_id" in sql
    assert "WHEN tir.target_type = 'CexToken' THEN 'binance_cex_rest'" in sql
