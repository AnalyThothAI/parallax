from gmgn_twitter_intel.retrieval.opportunity_scoring import opportunity_score


def _component(score: int, *, risks: list[str] | None = None, hard_risks: list[str] | None = None):
    return {
        "score": score,
        "reasons": ["reason"],
        "risks": risks or [],
        "hard_risks": hard_risks or [],
        "risk_caps": [],
    }


def test_opportunity_driver_for_balanced_high_quality_setup():
    score = opportunity_score(
        {
            "heat": _component(88),
            "quality": _component(82),
            "propagation": _component(78),
            "tradeability": _component(86),
            "timing": _component(74),
        }
    )

    assert score["decision"] == "driver"
    assert score["score"] >= 80
    assert score["components"] == {
        "heat": 88,
        "quality": 82,
        "propagation": 78,
        "tradeability": 86,
        "timing": 74,
    }


def test_opportunity_hard_risk_prevents_driver():
    score = opportunity_score(
        {
            "heat": _component(95),
            "quality": _component(90),
            "propagation": _component(88),
            "tradeability": _component(20, risks=["missing_market"], hard_risks=["missing_market"]),
            "timing": _component(75),
        }
    )

    assert score["decision"] == "discard"
    assert "missing_market" in score["risks"]
    assert score["score"] <= 40
