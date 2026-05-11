from __future__ import annotations

from decimal import Decimal

from gmgn_twitter_intel.domains.token_intel.read_models.token_target_social_timeline_service import (
    TokenTargetSocialTimelineService,
)


def test_token_target_timeline_reads_rows_by_target_identity():
    service = TokenTargetSocialTimelineService(
        targets=FakeTargets(
            rows=[
                timeline_row(
                    target_type="Asset",
                    target_id="asset:eip155:1:erc20:0x44b28991b167582f18ba0259e0173176ca125505",
                    symbol="UPIC",
                    chain_id="eip155:1",
                    address="0x44b28991b167582f18ba0259e0173176ca125505",
                )
            ]
        )
    )

    result = service.timeline(
        target_type="Asset",
        target_id="asset:eip155:1:erc20:0x44b28991b167582f18ba0259e0173176ca125505",
        window="1h",
        scope="all",
        limit=50,
        now_ms=1_700_000_060_000,
    )

    assert result["query"]["target_type"] == "Asset"
    assert result["query"]["target_id"] == "asset:eip155:1:erc20:0x44b28991b167582f18ba0259e0173176ca125505"
    assert result["summary"]["posts"] == 1
    assert result["summary"]["authors"] == 1
    assert result["market_overlay"]["target_type"] == "Asset"
    assert result["market_overlay"]["chain_id"] == "eip155:1"
    assert result["stages"][0]["phase"] == "seed"
    assert result["stages"][0]["representative_event_ids"] == ["event-1"]
    assert result["posts"][0]["target_id"] == "asset:eip155:1:erc20:0x44b28991b167582f18ba0259e0173176ca125505"
    assert isinstance(result["posts"][0]["attribution_confidence"], float)
    assert "confidence" not in result["posts"][0]
    assert result["posts"][0]["stage_phase"] == "seed"
    assert result["posts"][0]["is_stage_representative"] is True
    assert result["posts"][0]["price"]["status"] == "ready"
    assert result["posts"][0]["price"]["price_usd"] == 1.23
    assert result["buckets"][0]["price"]["price_usd"] == 1.23


def test_cex_target_timeline_uses_pricefeed_market_overlay():
    service = TokenTargetSocialTimelineService(
        targets=FakeTargets(
            rows=[
                timeline_row(
                    target_type="CexToken",
                    target_id="cex_token:BTC",
                    symbol="BTC",
                    provider="okx",
                    native_market_id="BTC-USDT",
                    quote_symbol="USDT",
                    feed_type="cex_spot",
                )
            ]
        )
    )

    result = service.timeline(
        target_type="CexToken",
        target_id="cex_token:BTC",
        window="1h",
        scope="all",
        limit=50,
        now_ms=1_700_000_060_000,
    )

    assert result["market_overlay"]["target_type"] == "CexToken"
    assert result["market_overlay"]["provider"] == "okx"
    assert result["market_overlay"]["native_market_id"] == "BTC-USDT"


def test_social_timeline_cursor_is_timestamp_and_event_id():
    targets = FakeTargets(
        rows=[
            timeline_row("event-3", target_type="CexToken", target_id="cex_token:BTC", symbol="BTC"),
            timeline_row("event-2", target_type="CexToken", target_id="cex_token:BTC", symbol="BTC"),
            timeline_row("event-1", target_type="CexToken", target_id="cex_token:BTC", symbol="BTC"),
        ]
    )
    service = TokenTargetSocialTimelineService(targets=targets)

    first = service.timeline(
        target_type="CexToken",
        target_id="cex_token:BTC",
        window="1h",
        scope="all",
        limit=2,
        now_ms=1_700_000_060_000,
    )
    second = service.timeline(
        target_type="CexToken",
        target_id="cex_token:BTC",
        window="1h",
        scope="all",
        limit=2,
        cursor=first["next_cursor"],
        now_ms=1_700_000_060_000,
    )

    assert first["next_cursor"] == "1700000000000:event-2"
    assert targets.seen_cursors[-1] == (1_700_000_000_000, "event-2")
    assert [post["event_id"] for post in second["posts"]] == ["event-1"]


class FakeTargets:
    def __init__(self, *, rows):
        self.rows = rows
        self.seen_cursors = []

    def timeline_rows(self, *, target_type, target_id, since_ms, watched_only, limit, cursor=None):
        self.seen_cursors.append(cursor)
        rows = [
            row
            for row in self.rows
            if row["target_type"] == target_type and row["target_id"] == target_id and row["received_at_ms"] >= since_ms
        ]
        if cursor is not None:
            cursor_ms, cursor_event_id = cursor
            rows = [
                row for row in rows if (int(row["received_at_ms"]), str(row["event_id"])) < (cursor_ms, cursor_event_id)
            ]
        return rows[:limit]


def timeline_row(
    event_id="event-1",
    *,
    target_type,
    target_id,
    symbol,
    chain_id=None,
    address=None,
    provider=None,
    native_market_id=None,
    quote_symbol=None,
    feed_type=None,
):
    return {
        "event_id": event_id,
        "tweet_id": event_id,
        "target_type": target_type,
        "target_id": target_id,
        "symbol": symbol,
        "chain_id": chain_id,
        "address": address,
        "provider": provider,
        "native_market_id": native_market_id,
        "quote_symbol": quote_symbol,
        "feed_type": feed_type,
        "author_handle": "alice",
        "text": f"${symbol} looks strong",
        "canonical_url": None,
        "is_watched": True,
        "received_at_ms": 1_700_000_000_000,
        "attribution_status": "EXACT",
        "confidence": Decimal("0.95"),
        "price_observation_id": f"price:{event_id}",
        "price_provider": "gmgn_payload",
        "price_usd": Decimal("1.23"),
        "price_quote": None,
        "price_quote_symbol": None,
        "price_observed_at_ms": 1_700_000_000_000,
        "price_observation_lag_ms": 0,
        "price_observation_kind": "message_payload",
    }
