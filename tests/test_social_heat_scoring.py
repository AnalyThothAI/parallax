from gmgn_twitter_intel.retrieval.social_heat_scoring import social_heat_score


def test_social_heat_burst_scores_abnormal_acceleration():
    score = social_heat_score(
        {
            "mentions": 9,
            "weighted_mentions": 8.5,
            "previous_mentions": 1,
            "mention_delta": 8,
            "mention_delta_pct": 8.0,
            "z_ewma": 2.8,
            "robust_z": 3.4,
            "new_burst_score": None,
            "stream_share": 0.18,
            "watched_share": 0.25,
            "is_new_local_evidence": True,
            "is_first_seen_by_watched": True,
        }
    )

    assert score["status"] == "burst"
    assert score["score_version"] == "social_heat_v2"
    assert score["score"] >= 75
    assert "robust_z_above_3" in score["reasons"]
    assert "positive_mention_delta" in score["reasons"]
    assert score["data_health"]["baseline_ready"] is True
    assert score["contributions"]


def test_social_heat_marks_single_mention_as_thin():
    score = social_heat_score(
        {
            "mentions": 1,
            "weighted_mentions": 1.0,
            "previous_mentions": 0,
            "mention_delta": 1,
            "z_ewma": None,
            "robust_z": None,
            "new_burst_score": None,
            "stream_share": 0.01,
            "watched_share": 0.0,
            "is_new_local_evidence": True,
            "is_first_seen_by_watched": False,
        }
    )

    assert score["status"] == "insufficient_history"
    assert "thin_mentions" in score["risks"]
    assert score["score"] <= 45
    assert any(cap["risk"] == "thin_mentions" for cap in score["risk_caps"])
    assert any(cap["risk"] == "thin_public_only" for cap in score["risk_caps"])
