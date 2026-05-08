from __future__ import annotations

from gmgn_twitter_intel.pipeline.token_radar_feature_builder import build_radar_features


def test_radar_feature_builder_counts_windows_and_stream_share():
    now_ms = 1_700_000_000_000
    rows = [
        row("event-1", received_at_ms=now_ms - 60_000, author="alice", text="$ABC new pool live, liquidity growing"),
        row("event-2", received_at_ms=now_ms - 10 * 60_000, author="bob", text="$ABC chart breakout"),
        row("event-3", received_at_ms=now_ms - 2 * 60 * 60_000, author="carol", text="$ABC mcap still low"),
    ]

    features = build_radar_features(
        window_rows=[rows[0]],
        context_rows=rows,
        previous_rows=[rows[1]],
        now_ms=now_ms,
        window_ms=5 * 60_000,
        total_window_events=4,
    )

    assert features.attention["mentions_5m"] == 1
    assert features.attention["mentions_1h"] == 2
    assert features.attention["mentions_4h"] == 3
    assert features.heat["mentions"] == 1
    assert features.heat["previous_mentions"] == 1
    assert features.heat["stream_share"] == 0.25
    assert features.quality["informative_post_count"] == 1
    assert features.propagation["independent_authors"] == 1


def test_radar_feature_builder_sets_cex_tradeability_features():
    now_ms = 1_700_000_000_000
    features = build_radar_features(
        window_rows=[
            row(
                "event-1",
                received_at_ms=now_ms - 60_000,
                target_type="CexToken",
                target_id="cex-token:BTC",
                pricefeed_id="pricefeed:okx:BTC-USDT",
                native_market_id="BTC-USDT",
                market_observed_at_ms=now_ms - 10_000,
                market_volume_24h_usd=100_000_000,
                market_open_interest_usd=25_000_000,
            )
        ],
        context_rows=[],
        previous_rows=[],
        now_ms=now_ms,
        window_ms=5 * 60_000,
        total_window_events=1,
    )

    assert features.tradeability["target_type"] == "CexToken"
    assert features.tradeability["identity_status"] == "resolved_cex"
    assert features.tradeability["native_market_id"] == "BTC-USDT"
    assert features.tradeability["volume_24h"] == 100_000_000


def row(
    event_id: str,
    *,
    received_at_ms: int,
    author: str = "alice",
    text: str = "$ABC",
    target_type: str = "Asset",
    target_id: str | None = "asset:eip155:1:erc20:0xabc",
    pricefeed_id: str | None = "pricefeed:dex:ABC",
    native_market_id: str | None = None,
    market_observed_at_ms: int | None = None,
    market_volume_24h_usd: float | None = None,
    market_open_interest_usd: float | None = None,
) -> dict:
    return {
        "event_id": event_id,
        "intent_id": f"intent-{event_id}",
        "received_at_ms": received_at_ms,
        "author_handle": author,
        "is_watched": author == "alice",
        "text": text,
        "text_clean": text.lower(),
        "intent_confidence": 0.9,
        "resolution_status": "EXACT" if target_id else "NIL",
        "target_type": target_type if target_id else None,
        "target_id": target_id,
        "pricefeed_id": pricefeed_id,
        "native_market_id": native_market_id,
        "asset_chain_id": "eip155:1",
        "asset_address": "0xabc",
        "market_observed_at_ms": market_observed_at_ms,
        "market_market_cap_usd": 1_000_000,
        "market_liquidity_usd": 250_000,
        "market_volume_24h_usd": market_volume_24h_usd,
        "market_open_interest_usd": market_open_interest_usd,
    }
