from gmgn_twitter_intel.retrieval.propagation_scoring import propagation_score


def test_propagation_expansion_for_independent_author_growth():
    score = propagation_score(
        {
            "mentions": 12,
            "independent_authors": 8,
            "effective_authors": 5.4,
            "new_authors": 6,
            "top_author_share": 0.25,
            "duplicate_text_share": 0.08,
            "watched_author_count": 1,
            "seed_lag_ms": 180_000,
        }
    )

    assert score["phase"] == "expansion"
    assert score["score"] >= 75
    assert "independent_expansion" in score["reasons"]
    assert "low_concentration" in score["reasons"]


def test_propagation_caps_single_source_concentration():
    score = propagation_score(
        {
            "mentions": 8,
            "independent_authors": 2,
            "effective_authors": 1.4,
            "new_authors": 1,
            "top_author_share": 0.78,
            "duplicate_text_share": 0.1,
            "watched_author_count": 0,
            "seed_lag_ms": None,
        }
    )

    assert score["phase"] == "concentration"
    assert "author_concentration_high" in score["risks"]
    assert score["score"] <= 65
    assert any(cap["risk"] == "author_concentration_high" for cap in score["risk_caps"])
