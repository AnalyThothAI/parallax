from __future__ import annotations

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


class FakeAssets:
    def __init__(self, *, rows):
        self.rows = rows

    def recent_asset_attributions(self, *, since_ms, watched_only, limit):
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
    }
