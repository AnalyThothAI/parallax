from __future__ import annotations

import re
from typing import Any

import pytest

from parallax.domains.account_quality.repositories.account_quality_repository import (
    AccountQualityRepository,
)
from parallax.domains.asset_market.repositories.registry_repository import RegistryRepository
from parallax.domains.token_intel.queries.event_token_projection_query import (
    EventTokenProjectionQuery,
)
from parallax.domains.token_intel.repositories.token_target_repository import TokenTargetRepository


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
    assert "token_radar_publication_state" in sql
    assert "token_radar_projection_coverage" not in sql
    assert "current_generation_id" not in sql
    assert "rows.generation_id = latest_sets.current_generation_id" not in sql
    _assert_no_legacy_cex_preference_ordering(sql)


def test_registry_exact_cex_lookup_still_requires_a_matching_exchange_row() -> None:
    conn = RecordingConn(rows=[])

    row = RegistryRepository(conn).find_cex_pricefeed(exchange="okx", native_market_id="BTC-USDT")

    assert row is None
    assert conn.params_calls[-1] == ("okx", "BTC-USDT")


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


def test_token_target_repository_event_id_timeline_starts_from_event_id_unnest() -> None:
    conn = RecordingConn()

    TokenTargetRepository(conn).timeline_rows_for_event_ids(
        target_type="CexToken",
        target_id="cex_token:BTC",
        event_ids=["event-2", "event-1"],
        watched_only=True,
        limit=25,
    )

    sql = conn.sql_calls[-1]
    assert re.search(r"WITH\s+requested_events\s+AS\s*\(\s*SELECT", sql)
    assert "FROM unnest(%s::text[]) WITH ORDINALITY AS event_ids(event_id, ordinality)" in sql
    assert "JOIN events ON events.event_id = requested_events.event_id" in sql
    assert "JOIN token_intent_resolutions tir" in sql
    assert "tir.is_current = true" in sql
    assert "events.is_watched = true" in sql
    assert "events.received_at_ms >= %s" not in sql
    assert conn.params_calls[-1][0] == ["event-2", "event-1"]
    _assert_binance_usdt_swap_only(sql)
    _assert_no_legacy_cex_preference_ordering(sql)
    _assert_token_target_timeline_rejects_legacy_cex_event_tick(sql)


@pytest.mark.parametrize("limit", [-1, True, "25"])
def test_token_target_repository_timeline_rejects_malformed_limit_before_sql(limit: object) -> None:
    conn = RecordingConn()

    with pytest.raises(ValueError, match="token_target_repository_limit_required"):
        TokenTargetRepository(conn).timeline_rows(
            target_type="CexToken",
            target_id="cex_token:BTC",
            since_ms=1,
            watched_only=False,
            limit=limit,  # type: ignore[arg-type]
        )

    assert conn.sql_calls == []


def test_token_target_repository_event_id_timeline_allows_zero_limit_without_sql() -> None:
    conn = RecordingConn()

    rows = TokenTargetRepository(conn).timeline_rows_for_event_ids(
        target_type="CexToken",
        target_id="cex_token:BTC",
        event_ids=["event-1"],
        watched_only=False,
        limit=0,
    )

    assert rows == []
    assert conn.sql_calls == []


@pytest.mark.parametrize("limit", [-1, True, "25"])
def test_token_target_repository_event_id_timeline_rejects_malformed_limit_before_sql(limit: object) -> None:
    conn = RecordingConn()

    with pytest.raises(ValueError, match="token_target_repository_limit_required"):
        TokenTargetRepository(conn).timeline_rows_for_event_ids(
            target_type="CexToken",
            target_id="cex_token:BTC",
            event_ids=[],
            watched_only=False,
            limit=limit,  # type: ignore[arg-type]
        )

    assert conn.sql_calls == []


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
