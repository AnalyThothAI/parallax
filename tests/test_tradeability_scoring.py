from gmgn_twitter_intel.retrieval.tradeability_scoring import tradeability_score


def test_tradeability_scores_resolved_fresh_market_with_mcap():
    score = tradeability_score(
        {
            "identity_status": "resolved_ca",
            "token_id": "token:eth:0xdog",
            "chain": "eth",
            "address": "0xdog",
            "market_status": "fresh",
            "market_cap": 2_100_000,
            "liquidity": 250_000,
            "pool_status": "ready",
        }
    )

    assert score["identity_tradeable"] is True
    assert score["market_fresh"] is True
    assert score["market_cap_present"] is True
    assert score["score"] >= 80
    assert "resolved_ca" in score["reasons"]


def test_tradeability_missing_market_sets_hard_risk():
    score = tradeability_score(
        {
            "identity_status": "resolved_ca",
            "token_id": "token:eth:0xdog",
            "chain": "eth",
            "address": "0xdog",
            "market_status": "missing",
            "market_cap": None,
            "liquidity": None,
            "pool_status": "missing",
        }
    )

    assert score["market_fresh"] is False
    assert "missing_market" in score["risks"]
    assert "missing_market_cap" in score["risks"]
    assert "missing_market" in score["hard_risks"]
    assert score["score"] <= 40
