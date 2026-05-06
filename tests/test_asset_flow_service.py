from __future__ import annotations

import pytest

from gmgn_twitter_intel.retrieval.asset_flow_service import AssetFlowService


def test_asset_flow_has_resolved_and_attention_lanes():
    service = AssetFlowService(
        assets=FakeAssets(
            rows=[
                resolved_row(symbol="BTC", asset_id="asset:cex:BTC", venue_id="venue:cex:okx:SPOT:BTC-USDT"),
                unresolved_row(symbol="MIRROR", asset_id="asset:unresolved:MIRROR"),
            ]
        )
    )

    result = service.asset_flow(window="1h", limit=20, scope="all", now_ms=1_700_000_060_000)

    assert result["resolved_assets"][0]["asset"]["symbol"] == "BTC"
    assert result["attention_candidates"][0]["asset"]["symbol"] == "MIRROR"
    assert result["projection"]["version"] == "asset-flow-v1"


def test_unresolved_mirror_appears_in_attention_lane():
    service = AssetFlowService(
        assets=FakeAssets(rows=[unresolved_row(symbol="MIRROR", asset_id="asset:unresolved:MIRROR")])
    )

    result = service.asset_flow(window="1h", limit=20, scope="all", now_ms=1_700_000_060_000)

    mirror = result["attention_candidates"][0]
    assert mirror["asset"]["identity_status"] == "unresolved"
    assert mirror["resolution"]["status"] == "unresolved"
    assert mirror["attention"]["mentions_1h"] == 1


def test_btc_cex_asset_does_not_require_chain_address():
    service = AssetFlowService(
        assets=FakeAssets(
            rows=[resolved_row(symbol="BTC", asset_id="asset:cex:BTC", venue_id="venue:cex:okx:SPOT:BTC-USDT")]
        )
    )

    result = service.asset_flow(window="1h", limit=20, scope="all", now_ms=1_700_000_060_000)

    btc = result["resolved_assets"][0]
    assert btc["asset"]["asset_type"] == "cex_asset"
    assert btc["primary_venue"]["venue_type"] == "cex"
    assert btc["primary_venue"]["inst_id"] == "BTC-USDT"
    assert btc["primary_venue"]["chain"] is None
    assert btc["primary_venue"]["address"] is None


def test_asset_flow_exposes_latest_market_snapshot_health():
    service = AssetFlowService(
        assets=FakeAssets(
            rows=[
                {
                    **resolved_row(symbol="BTC", asset_id="asset:cex:BTC", venue_id="venue:cex:okx:SPOT:BTC-USDT"),
                    "market_provider": "okx_cex",
                    "market_observed_at_ms": 1_700_000_000_000,
                    "market_price_usd": 69_000.0,
                    "market_volume_24h_usd": 123_000_000.0,
                }
            ]
        )
    )

    result = service.asset_flow(window="1h", limit=20, scope="all", now_ms=1_700_000_060_000)

    market = result["resolved_assets"][0]["market"]
    assert market["market_status"] == "fresh"
    assert market["provider"] == "okx_cex"
    assert market["price_usd"] == 69_000.0
    assert market["snapshot_age_ms"] == 60_000


def test_asset_flow_treats_empty_market_snapshot_as_missing():
    service = AssetFlowService(
        assets=FakeAssets(
            rows=[
                {
                    **resolved_row(symbol="TEST", asset_id="asset:dex:base:test", venue_id="venue:dex:base:test"),
                    "market_provider": "okx_dex",
                    "market_observed_at_ms": 1_700_000_000_000,
                    "market_price_usd": None,
                    "market_cap_usd": None,
                    "market_liquidity_usd": None,
                    "market_volume_24h_usd": None,
                    "market_open_interest_usd": None,
                    "market_holders": None,
                }
            ]
        )
    )

    result = service.asset_flow(window="1h", limit=20, scope="all", now_ms=1_700_000_060_000)

    market = result["resolved_assets"][0]["market"]
    assert market["market_status"] == "missing"
    assert market["provider"] is None
    assert market["snapshot_observed_at_ms"] is None


def test_asset_flow_uses_provider_symbol_alias_instead_of_contract_address_display():
    address = "CB9dDufT3ZuQXqqSfa1c5kY935TEreyBw9XJXxHKpump"
    row = {
        **resolved_row(
            symbol=address.upper(),
            asset_id=f"asset:dex:solana:{address.lower()}",
            venue_id=f"venue:dex:solana:{address.lower()}",
        ),
        "asset_type": "dex_asset",
        "venue_type": "dex",
        "exchange": None,
        "inst_id": None,
        "chain": "solana",
        "address": address,
        "display_symbol": "USDUC",
    }
    service = AssetFlowService(assets=FakeAssets(rows=[row]))

    result = service.asset_flow(window="1h", limit=20, scope="all", now_ms=1_700_000_060_000)

    assert result["resolved_assets"][0]["asset"]["symbol"] == "USDUC"


def test_asset_flow_omits_address_like_symbol_when_provider_symbol_is_unknown():
    address = "CTc4y2eHbTApoCAo2rNJFHkvPFHMnNygqEcBMyNcpump"
    row = {
        **resolved_row(
            symbol=address.upper(),
            asset_id=f"asset:dex:solana:{address.lower()}",
            venue_id=f"venue:dex:solana:{address.lower()}",
        ),
        "asset_type": "dex_asset",
        "venue_type": "dex",
        "exchange": None,
        "inst_id": None,
        "chain": "solana",
        "address": address,
    }
    service = AssetFlowService(assets=FakeAssets(rows=[row]))

    result = service.asset_flow(window="1h", limit=20, scope="all", now_ms=1_700_000_060_000)

    assert result["resolved_assets"][0]["asset"]["symbol"] is None


def test_asset_flow_exposes_market_timing_changes_from_snapshot_baselines():
    service = AssetFlowService(
        assets=FakeAssets(
            rows=[
                {
                    **resolved_row(symbol="BTC", asset_id="asset:cex:BTC", venue_id="venue:cex:okx:SPOT:BTC-USDT"),
                    "market_provider": "okx_cex",
                    "market_observed_at_ms": 1_700_000_000_000,
                    "market_price_usd": 100.0,
                    "market_volume_24h_usd": 123_000_000.0,
                    "market_price_5m_ago": 80.0,
                    "market_price_1h_ago": 50.0,
                    "market_price_24h_ago": 40.0,
                    "market_price_at_social_start": 90.0,
                    "market_price_before_social_start": 75.0,
                }
            ]
        )
    )

    result = service.asset_flow(window="1h", limit=20, scope="all", now_ms=1_700_000_060_000)

    market = result["resolved_assets"][0]["market"]
    assert market["price_change_status"] == "ready"
    assert market["price_change_5m_pct"] == pytest.approx(0.25)
    assert market["price_change_1h_pct"] == pytest.approx(1.0)
    assert market["price_change_24h_pct"] == pytest.approx(1.5)
    assert market["price_at_social_start"] == 90.0
    assert market["price_change_since_social_pct"] == pytest.approx(1 / 9)
    assert market["price_change_before_social_pct"] == pytest.approx(0.2)


class FakeAssets:
    def __init__(self, *, rows):
        self.rows = rows

    def asset_flow_rows(self, *, since_ms, watched_only, limit, now_ms):
        return [row for row in self.rows if row["decision_time_ms"] >= since_ms][:limit]


def resolved_row(*, symbol, asset_id, venue_id):
    return {
        "event_id": f"event-{symbol.lower()}",
        "asset_id": asset_id,
        "asset_type": "cex_asset",
        "canonical_symbol": symbol,
        "identity_status": "resolved",
        "attribution_status": "selected",
        "venue_id": venue_id,
        "venue_type": "cex",
        "exchange": "okx",
        "inst_id": f"{symbol}-USDT",
        "chain": None,
        "address": None,
        "author_handle": "alice",
        "is_watched": True,
        "decision_time_ms": 1_700_000_000_000,
        "mentions_5m": 1,
        "mentions_1h": 1,
        "mentions_window": 1,
        "unique_authors": 1,
        "watched_mentions": 1,
        "latest_seen_ms": 1_700_000_000_000,
        "source_max_received_at_ms": 1_700_000_000_000,
    }


def unresolved_row(*, symbol, asset_id):
    return {
        "event_id": f"event-{symbol.lower()}",
        "asset_id": asset_id,
        "asset_type": "unresolved_symbol",
        "canonical_symbol": symbol,
        "identity_status": "unresolved",
        "attribution_status": "unresolved",
        "venue_id": None,
        "venue_type": None,
        "exchange": None,
        "inst_id": None,
        "chain": None,
        "address": None,
        "author_handle": "bob",
        "is_watched": False,
        "decision_time_ms": 1_700_000_000_000,
        "mentions_5m": 1,
        "mentions_1h": 1,
        "mentions_window": 1,
        "unique_authors": 1,
        "watched_mentions": 0,
        "latest_seen_ms": 1_700_000_000_000,
        "source_max_received_at_ms": 1_700_000_000_000,
    }
