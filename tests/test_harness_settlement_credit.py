from gmgn_twitter_intel.pipeline.harness_credit import assign_cluster_credits, update_weight_stat
from gmgn_twitter_intel.pipeline.harness_settlement import (
    abnormal_return,
    actual_return,
    expected_return,
    normalized_outcome,
)


def test_settlement_uses_abnormal_return_and_clipped_normalized_outcome():
    actual = actual_return(entry_price=100, exit_price=112)
    expected = expected_return({"group": 0.04}, momentum_return=0.02, weights={"group": 0.5, "momentum": 0.25})

    assert actual == 0.12
    assert expected == 0.025
    assert abnormal_return(actual, expected) == 0.095
    assert normalized_outcome(0.095, realized_vol=0.02) == 1.0
    assert normalized_outcome(0.015, realized_vol=0.01) == 0.5


def test_credit_assignment_splits_responsibility_by_abs_score():
    credits = assign_cluster_credits(
        [
            {"cluster_id": "a", "event_type": "meme_phrase_seed", "source": "cz_binance", "event_score": 0.3},
            {"cluster_id": "b", "event_type": "regulation_negative", "source": "heyibinance", "event_score": -0.1},
        ],
        normalized_outcome=0.5,
    )

    assert credits[0]["responsibility"] == 0.75
    assert credits[0]["credit"] == 0.375
    assert credits[1]["responsibility"] == 0.25
    assert credits[1]["credit"] == -0.125


def test_weight_update_is_slow_and_clipped():
    updated = update_weight_stat({"n": 0, "mean_credit": 0.0}, credit=1.0, n0=50, lambda_=0.5)
    assert updated["n"] == 1
    assert updated["mean_credit"] == 1.0
    assert updated["weight"] < 1.02

    clipped = update_weight_stat({"n": 1000, "mean_credit": 10.0}, credit=10.0, n0=50, lambda_=0.5)
    assert clipped["weight"] == 1.5
