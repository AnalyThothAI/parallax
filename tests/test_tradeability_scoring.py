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
    assert score["score_version"] == "tradeability_v2"
    assert score["market_fresh"] is True
    assert score["market_cap_present"] is True
    assert score["score"] >= 80
    assert "resolved_ca" in score["reasons"]
    assert score["data_health"]["market"] == "fresh"


def test_tradeability_scores_cex_without_chain_or_address():
    score = tradeability_score(
        {
            "target_type": "CexToken",
            "identity_status": "resolved_cex",
            "token_id": "cex-token:BTC",
            "pricefeed_id": "pricefeed:okx:BTC-USDT",
            "native_market_id": "BTC-USDT",
            "market_status": "fresh",
            "volume_24h": 120_000_000,
            "open_interest": 20_000_000,
        }
    )

    assert score["identity_tradeable"] is True
    assert "resolved_cex" in score["reasons"]
    assert "missing_market_cap" not in score["risks"]
    assert score["score"] >= 70


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


def test_tradeability_lookahead_risk_is_hard_risk():
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
            "lookahead_risk": True,
        }
    )

    assert "lookahead_risk" in score["hard_risks"]
    assert score["score"] <= 40
