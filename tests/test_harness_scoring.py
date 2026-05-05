from gmgn_twitter_intel.pipeline.harness_scoring import (
    base_event_score,
    combined_score,
    event_score,
    policy_signal,
    price_move_penalty,
    shadow_signal,
)


def test_base_event_score_respects_direction_and_pricedness():
    positive = base_event_score(direction=1, impact=0.8, confidence=0.9, novelty=0.7, pricedness=0.25)
    negative = base_event_score(direction=-1, impact=0.8, confidence=0.9, novelty=0.7, pricedness=0.25)
    stale = base_event_score(direction=1, impact=0.8, confidence=0.9, novelty=0.7, pricedness=0.9)

    assert positive > 0
    assert negative == -positive
    assert stale < positive


def test_price_move_penalty_caps_chase_risk():
    assert price_move_penalty(pre_move=0.001, recent_vol=0.02) == 1.0
    assert price_move_penalty(pre_move=0.08, recent_vol=0.02) == 0.2


def test_combined_score_and_policy_layers_are_separate():
    score = combined_score([
        event_score(
            0.5,
            source_weight=1.0,
            event_type_weight=1.0,
            horizon_weight=1.0,
            time_decay=1.0,
            price_penalty=1.0,
        ),
        -0.1,
    ])

    assert score == 0.4
    assert policy_signal(score, long_threshold=0.7, short_threshold=-0.7) == "NO_TRADE"
    assert shadow_signal(score, long_threshold=0.25, short_threshold=-0.25) == "LONG_SMALL"
