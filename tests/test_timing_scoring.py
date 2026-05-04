from gmgn_twitter_intel.retrieval.timing_scoring import timing_score


def test_timing_social_leads_price_before_move():
    score = timing_score(
        {
            "social_start_ms": 1_700_000_000_000,
            "burst_ms": 1_700_000_060_000,
            "first_price_move_ms": 1_700_000_300_000,
            "price_change_window_pct": 0.02,
            "price_change_before_social_pct": 0.0,
            "social_heat_score": 82,
        }
    )

    assert score["status"] == "social_leads_price"
    assert score["score"] >= 75
    assert score["chase_risk"] is False


def test_timing_price_leads_social_sets_chase_risk():
    score = timing_score(
        {
            "social_start_ms": 1_700_000_300_000,
            "burst_ms": 1_700_000_360_000,
            "first_price_move_ms": 1_700_000_000_000,
            "price_change_window_pct": 0.42,
            "price_change_before_social_pct": 0.32,
            "social_heat_score": 80,
        }
    )

    assert score["status"] == "price_leads_social"
    assert score["chase_risk"] is True
    assert "chase_risk" in score["risks"]
    assert score["score"] <= 45
