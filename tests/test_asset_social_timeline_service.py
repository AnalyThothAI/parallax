from __future__ import annotations

from gmgn_twitter_intel.retrieval.asset_social_timeline_service import AssetSocialTimelineService


def test_unresolved_asset_timeline_returns_posts_without_market_overlay():
    service = AssetSocialTimelineService(
        assets=FakeAssets(
            rows=[
                timeline_row(
                    asset_id="asset:unresolved:MIRROR",
                    symbol="MIRROR",
                    identity_status="unresolved",
                    venue_type=None,
                )
            ]
        )
    )

    result = service.timeline(
        asset_id="asset:unresolved:MIRROR",
        window="1h",
        scope="all",
        limit=50,
        now_ms=1_700_000_060_000,
    )

    assert result["summary"]["posts"] == 1
    assert result["summary"]["authors"] == 1
    assert result["market_overlay"] is None
    assert result["posts"][0]["event_id"] == "event-1"


def test_cex_asset_timeline_uses_cex_market_overlay():
    service = AssetSocialTimelineService(
        assets=FakeAssets(
            rows=[
                timeline_row(
                    asset_id="asset:cex:BTC",
                    symbol="BTC",
                    identity_status="resolved",
                    venue_type="cex",
                    venue_id="venue:cex:okx:SPOT:BTC-USDT",
                    inst_id="BTC-USDT",
                )
            ]
        )
    )

    result = service.timeline(
        asset_id="asset:cex:BTC",
        window="1h",
        scope="all",
        limit=50,
        now_ms=1_700_000_060_000,
    )

    assert result["market_overlay"]["venue_type"] == "cex"
    assert result["market_overlay"]["inst_id"] == "BTC-USDT"


class FakeAssets:
    def __init__(self, *, rows):
        self.rows = rows

    def asset_timeline_rows(self, *, asset_id, since_ms, watched_only, limit, cursor_ms=None):
        return [row for row in self.rows if row["asset_id"] == asset_id and row["received_at_ms"] >= since_ms][:limit]


def timeline_row(*, asset_id, symbol, identity_status, venue_type, venue_id=None, inst_id=None):
    return {
        "event_id": "event-1",
        "asset_id": asset_id,
        "canonical_symbol": symbol,
        "identity_status": identity_status,
        "asset_type": "cex_asset" if venue_type == "cex" else "unresolved_symbol",
        "venue_id": venue_id,
        "venue_type": venue_type,
        "exchange": "okx" if venue_type == "cex" else None,
        "chain": None,
        "address": None,
        "inst_id": inst_id,
        "author_handle": "alice",
        "text": "$BTC looks strong" if symbol == "BTC" else "$MIRROR is moving",
        "url": None,
        "is_watched": True,
        "received_at_ms": 1_700_000_000_000,
        "attribution_status": "selected" if identity_status == "resolved" else "unresolved",
        "confidence": 0.9,
    }
