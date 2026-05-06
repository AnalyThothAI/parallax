from gmgn_twitter_intel.retrieval.timing_scoring import timing_score


def test_timing_ready_market_is_neutral_not_alpha_boost():
    score = timing_score(
        {
            "social_signal_start_ms": 1_700_000_000_000,
            "price_change_since_social_pct": 0.02,
            "price_change_before_social_pct": 0.0,
            "market_observation_status": "ready",
            "social_heat_score": 82,
        }
    )

    assert score["status"] == "neutral"
    assert score["score_version"] == "timing_v4"
    assert score["score"] == 50
    assert score["chase_risk"] is False
    assert "social_before_price_move" not in score["reasons"]
    assert score["data_health"]["market_timing"] == "ready"


def test_timing_price_leads_social_sets_chase_risk():
    score = timing_score(
        {
            "social_signal_start_ms": 1_700_000_300_000,
            "price_change_since_social_pct": 0.08,
            "price_change_before_social_pct": 0.32,
            "market_observation_status": "ready",
            "social_heat_score": 80,
        }
    )

    assert score["status"] == "chase_risk"
    assert score["chase_risk"] is True
    assert "chase_risk" in score["risks"]
    assert score["score"] < 50


def test_timing_large_post_social_move_stays_neutral():
    score = timing_score(
        {
            "social_signal_start_ms": 1_700_000_000_000,
            "price_change_since_social_pct": 0.18,
            "price_change_before_social_pct": 0.0,
            "market_observation_status": "ready",
            "social_heat_score": 75,
        }
    )

    assert score["status"] == "neutral"
    assert "social_and_price_confirm" not in score["reasons"]


def test_timing_market_pending_uses_observation_status():
    score = timing_score(
        {
            "social_signal_start_ms": 1_700_000_000_000,
            "price_change_since_social_pct": None,
            "price_change_before_social_pct": None,
            "market_observation_status": "pending",
            "social_heat_score": 80,
        }
    )

    assert score["status"] == "market_pending"
    assert "market_observation_pending" in score["risks"]


def test_timing_provider_failure_is_market_unavailable():
    score = timing_score(
        {
            "social_signal_start_ms": 1_700_000_000_000,
            "price_change_since_social_pct": None,
            "price_change_before_social_pct": None,
            "market_observation_status": "dead",
            "social_heat_score": 80,
        }
    )

    assert score["status"] == "market_unavailable"
    assert "dead" in score["risks"]


def test_timing_accepts_string_social_signal_start_ms():
    score = timing_score(
        {
            "social_signal_start_ms": "1700000000000",
            "price_change_since_social_pct": None,
            "price_change_before_social_pct": None,
            "market_observation_status": "ready",
        }
    )

    assert score["social_signal_start_ms"] == 1_700_000_000_000
