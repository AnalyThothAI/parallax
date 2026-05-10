from __future__ import annotations

import pytest

from gmgn_twitter_intel.domains.token_intel.scoring.token_radar_feature_builder import build_radar_features


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


def test_radar_feature_builder_materializes_baseline_contract():
    now_ms = 1_700_000_000_000
    window_ms = 5 * 60_000
    score_start_ms = now_ms - window_ms
    baseline_rows = [
        row(f"baseline-{index}", received_at_ms=score_start_ms - index * window_ms - 60_000, author=f"base{index}")
        for index in range(6)
    ]
    current_rows = [
        row(f"current-{index}", received_at_ms=now_ms - 60_000 - index * 1_000, author=f"voice{index}")
        for index in range(4)
    ]

    features = build_radar_features(
        window_rows=current_rows,
        context_rows=[*current_rows, *baseline_rows],
        previous_rows=[baseline_rows[0]],
        now_ms=now_ms,
        window_ms=window_ms,
        total_window_events=4,
    )

    assert features.attention["baseline_status"] == "ready"
    assert features.attention["baseline_sample_count"] == 6
    assert features.attention["baseline_nonzero_sample_count"] == 6
    assert features.attention["zero_slot_count"] == 0
    assert features.attention["previous_mentions"] == 1
    assert features.attention["mention_delta"] == 3
    assert features.heat["baseline_version"] == "token_baseline_v2"
    assert features.heat["robust_z"] == 3
    assert features.heat["z_score"] == features.heat["robust_z"]
    assert features.heat["new_burst_score"] == 0


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
    **kwargs,
) -> dict:
    followers = kwargs.pop("followers", None)
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
        "ws_author_followers": kwargs.pop("ws_author_followers", followers),
        "gmgn_platform_followers": kwargs.pop("gmgn_platform_followers", None),
        "gmgn_user_tags": kwargs.pop("gmgn_user_tags", []),
        "account_profile_first_seen_ms": kwargs.pop(
            "account_profile_first_seen_ms",
            received_at_ms - 365 * 86_400_000,
        ),
        "llm_direction_hint": kwargs.pop("llm_direction_hint", None),
        "llm_impact_hint": kwargs.pop("llm_impact_hint", None),
        "llm_semantic_novelty_hint": kwargs.pop("llm_semantic_novelty_hint", None),
        "llm_label_confidence": kwargs.pop("llm_label_confidence", None),
        **kwargs,
    }


def test_weighted_mentions_uses_quality_when_account_profiles_present():
    from gmgn_twitter_intel.domains.token_intel.scoring.token_radar_feature_builder import build_radar_features

    now_ms = 1_700_000_000_000
    base_row = {
        "event_id": "e1",
        "received_at_ms": now_ms - 60_000,
        "author_handle": "kol_alice",
        "intent_confidence": 1.0,
        "ws_author_followers": 100,
        "gmgn_platform_followers": 20000,
        "gmgn_user_tags": ["kol"],
        "account_profile_first_seen_ms": now_ms - 365 * 86_400_000,
        "is_watched": True,
        "text_clean": "alice talks about $TOKEN",
        "search_text": "alice talks about $TOKEN",
        "resolution_status": "EXACT",
        "llm_direction_hint": None,
        "llm_impact_hint": None,
        "llm_semantic_novelty_hint": None,
        "llm_label_confidence": None,
    }
    features = build_radar_features(
        window_rows=[base_row],
        context_rows=[base_row],
        previous_rows=[],
        now_ms=now_ms,
        window_ms=3_600_000,
        total_window_events=1,
    )
    assert features.heat["mentions"] == 1
    assert 0.5 < features.heat["weighted_mentions"] < 1.0  # < 1.0 falsifies old code
    # specific: log1p(20000)/log1p(100000) ≈ 0.86 for KOL, full age, 1.0 confidence
    assert features.heat["weighted_mentions"] == pytest.approx(0.864, abs=0.01)


def test_weighted_mentions_lower_for_no_tag_account():
    from gmgn_twitter_intel.domains.token_intel.scoring.token_radar_feature_builder import build_radar_features

    now_ms = 1_700_000_000_000

    def _row(handle, tags):
        return {
            "event_id": f"e_{handle}",
            "received_at_ms": now_ms - 60_000,
            "author_handle": handle,
            "intent_confidence": 1.0,
            "ws_author_followers": None,
            "gmgn_platform_followers": 20000,
            "gmgn_user_tags": tags,
            "account_profile_first_seen_ms": now_ms - 365 * 86_400_000,
            "is_watched": False,
            "text_clean": "talks about $TOKEN",
            "search_text": "talks about $TOKEN",
            "resolution_status": "EXACT",
            "llm_direction_hint": None,
            "llm_impact_hint": None,
            "llm_semantic_novelty_hint": None,
            "llm_label_confidence": None,
        }

    kol_features = build_radar_features(
        window_rows=[_row("kol", ["kol"])],
        context_rows=[_row("kol", ["kol"])],
        previous_rows=[],
        now_ms=now_ms,
        window_ms=3_600_000,
        total_window_events=1,
    )
    untagged_features = build_radar_features(
        window_rows=[_row("anon", [])],
        context_rows=[_row("anon", [])],
        previous_rows=[],
        now_ms=now_ms,
        window_ms=3_600_000,
        total_window_events=1,
    )
    assert kol_features.heat["weighted_mentions"] > untagged_features.heat["weighted_mentions"]


def test_quality_features_consume_llm_hints_when_present():
    from gmgn_twitter_intel.domains.token_intel.scoring.token_radar_feature_builder import build_radar_features

    now_ms = 1_700_000_000_000
    row_data = {
        "event_id": "e1",
        "received_at_ms": now_ms - 60_000,
        "author_handle": "alice",
        "intent_confidence": 1.0,
        "ws_author_followers": 5000,
        "gmgn_platform_followers": None,
        "gmgn_user_tags": [],
        "account_profile_first_seen_ms": now_ms - 365 * 86_400_000,
        "is_watched": False,
        "text_clean": "good things about $TOKEN",
        "search_text": "good things about $TOKEN",
        "resolution_status": "EXACT",
        "llm_direction_hint": "bullish",
        "llm_impact_hint": 0.8,
        "llm_semantic_novelty_hint": 0.7,
        "llm_label_confidence": 0.9,
    }
    features = build_radar_features(
        window_rows=[row_data],
        context_rows=[row_data],
        previous_rows=[],
        now_ms=now_ms,
        window_ms=3_600_000,
        total_window_events=1,
    )
    assert features.quality["llm_semantic_utility"] is not None
    assert features.quality["llm_label_confidence"] is not None
    assert 0.0 <= features.quality["llm_semantic_utility"] <= 1.0


def test_weighted_mentions_keeps_floor_signal_for_non_directory_account():
    """Account not in account_profiles (NULL first_seen_ms) should still
    contribute to weighted_mentions via the floor signal — NOT zero."""
    from gmgn_twitter_intel.domains.token_intel.scoring.token_radar_feature_builder import build_radar_features

    now_ms = 1_700_000_000_000
    row = {
        "event_id": "e1",
        "received_at_ms": now_ms - 60_000,
        "author_handle": "non_directory_account",
        "intent_confidence": 1.0,
        "ws_author_followers": 5000,  # has follower count but no directory profile
        "gmgn_platform_followers": None,
        "gmgn_user_tags": [],
        "account_profile_first_seen_ms": None,  # KEY: not in account_profiles
        "is_watched": False,
        "text_clean": "talks about $TOKEN",
        "search_text": "talks about $TOKEN",
        "resolution_status": "EXACT",
        "llm_direction_hint": None,
        "llm_impact_hint": None,
        "llm_semantic_novelty_hint": None,
        "llm_label_confidence": None,
    }
    features = build_radar_features(
        window_rows=[row],
        context_rows=[row],
        previous_rows=[],
        now_ms=now_ms,
        window_ms=3_600_000,
        total_window_events=1,
    )
    # Floor: log1p(5000)/log1p(100000) × 0.5 (no tag) × 1.0 (saturated age) ≈ 0.37
    assert features.heat["weighted_mentions"] > 0.0
    assert features.heat["weighted_mentions"] < 0.5
