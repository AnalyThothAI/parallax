from gmgn_twitter_intel.pipeline.social_event_extraction import (
    parse_social_event_response,
    social_event_response_format,
)


def test_parse_social_event_response_filters_to_evidence_bound_signal():
    result = parse_social_event_response(
        {
            "is_signal_event": True,
            "event_type": "meme_phrase_seed",
            "source_action": "posted",
            "subject": "BNB attention seed",
            "direction_hint": "attention_positive",
            "attention_mechanism": "meme_phrase",
            "impact_hint": 1.3,
            "semantic_novelty_hint": -0.2,
            "confidence": 0.86,
            "anchor_terms": [
                {"term": "build on BNB", "role": "meme_phrase", "evidence": "build on BNB"},
                {"term": "missing", "role": "meme_phrase", "evidence": "not in text"},
            ],
            "token_candidates": [
                {"symbol": "BNB", "evidence": "BNB", "confidence": 0.8},
                {"symbol": "NOPE", "evidence": "not in text", "confidence": 0.99},
            ],
            "semantic_risks": ["public_stream_coverage", "unknown_risk"],
            "summary_zh": "CZ 提到 build on BNB，形成注意力种子。",
        },
        event_text="CZ says build on BNB today",
    )

    assert result.is_signal_event is True
    assert result.impact_hint == 1.0
    assert result.semantic_novelty_hint == 0.0
    assert [anchor.term for anchor in result.anchor_terms] == ["build on BNB"]
    assert [candidate.symbol for candidate in result.token_candidates] == ["BNB"]
    assert result.semantic_risks == ["public_stream_coverage"]
    assert result.raw_response["subject"] == "BNB attention seed"


def test_parse_social_event_response_downgrades_signal_without_valid_anchor():
    result = parse_social_event_response(
        {
            "is_signal_event": True,
            "event_type": "meme_phrase_seed",
            "source_action": "posted",
            "subject": "BNB attention seed",
            "direction_hint": "attention_positive",
            "attention_mechanism": "meme_phrase",
            "impact_hint": 0.7,
            "semantic_novelty_hint": 0.7,
            "confidence": 0.9,
            "anchor_terms": [{"term": "missing", "role": "meme_phrase", "evidence": "not in text"}],
            "token_candidates": [],
            "semantic_risks": [],
            "summary_zh": "",
        },
        event_text="hello BNB",
    )

    assert result.is_signal_event is False
    assert result.anchor_terms == []


def test_social_event_response_format_is_strict_json_schema():
    response_format = social_event_response_format()

    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["name"] == "social_event_v2"
    assert response_format["json_schema"]["strict"] is True


def test_parse_social_event_response_rejects_low_confidence_signal():
    result = parse_social_event_response(
        {
            "is_signal_event": True,
            "event_type": "meme_phrase_seed",
            "source_action": "posted",
            "subject": "BNB attention seed",
            "direction_hint": "attention_positive",
            "attention_mechanism": "meme_phrase",
            "impact_hint": 0.7,
            "semantic_novelty_hint": 0.7,
            "confidence": 0.4,
            "anchor_terms": [{"term": "BNB", "role": "asset", "evidence": "BNB"}],
            "token_candidates": [{"symbol": "BNB", "evidence": "BNB", "confidence": 0.4}],
            "semantic_risks": [],
            "summary_zh": "BNB 注意力。",
        },
        event_text="BNB attention",
    )

    assert result.is_signal_event is False
    assert result.token_candidates == []
