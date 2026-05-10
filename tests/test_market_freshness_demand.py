from gmgn_twitter_intel.domains.asset_market.services.market_freshness_demand import (
    classify_market_refresh_candidate,
    prioritize_market_refresh_candidates,
)


def test_hot_target_without_price_is_top_priority():
    rows = [
        {
            "asset_id": "warm-old",
            "latest_candidate_received_at_ms": 1_777_999_000_000,
            "candidate_event_count": 1,
            "latest_price_observed_at_ms": 1_777_990_000_000,
        },
        {
            "asset_id": "hot-missing",
            "latest_candidate_received_at_ms": 1_778_000_000_000,
            "candidate_event_count": 3,
            "latest_price_observed_at_ms": None,
        },
    ]

    ordered = prioritize_market_refresh_candidates(
        rows,
        now_ms=1_778_000_060_000,
        hot_since_ms=1_778_000_000_000 - 60 * 60 * 1000,
        hot_stale_after_ms=90_000,
        warm_stale_after_ms=300_000,
    )

    assert ordered[0]["asset_id"] == "hot-missing"
    assert ordered[0]["market_freshness_class"] == "hot"
    assert ordered[0]["market_freshness_status"] == "missing"


def test_hot_target_over_alert_slo_beats_older_warm_target():
    rows = [
        {
            "asset_id": "warm-older",
            "latest_candidate_received_at_ms": 1_777_990_000_000,
            "candidate_event_count": 9,
            "latest_price_observed_at_ms": 1_777_990_000_000,
        },
        {
            "asset_id": "hot-stale",
            "latest_candidate_received_at_ms": 1_778_000_050_000,
            "candidate_event_count": 2,
            "latest_price_observed_at_ms": 1_777_999_900_000,
        },
    ]

    ordered = prioritize_market_refresh_candidates(
        rows,
        now_ms=1_778_000_060_000,
        hot_since_ms=1_778_000_000_000,
        hot_stale_after_ms=90_000,
        warm_stale_after_ms=300_000,
    )

    assert ordered[0]["asset_id"] == "hot-stale"
    assert ordered[0]["market_freshness_status"] == "stale"
    assert ordered[0]["market_freshness_lag_ms"] == 160_000


def test_fresh_hot_target_is_not_selected_when_budget_is_needed_elsewhere():
    candidate = classify_market_refresh_candidate(
        {
            "asset_id": "fresh-hot",
            "latest_candidate_received_at_ms": 1_778_000_050_000,
            "candidate_event_count": 3,
            "latest_price_observed_at_ms": 1_778_000_040_000,
        },
        now_ms=1_778_000_060_000,
        hot_since_ms=1_778_000_000_000,
        hot_stale_after_ms=90_000,
        warm_stale_after_ms=300_000,
    )

    assert candidate["market_freshness_class"] == "hot"
    assert candidate["market_freshness_status"] == "fresh"
    assert candidate["market_refresh_required"] is False
