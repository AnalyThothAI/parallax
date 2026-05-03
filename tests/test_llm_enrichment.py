import json

from gmgn_twitter_intel.pipeline.llm_enrichment import build_enrichment_prompt, parse_enrichment_response


def test_parse_enrichment_response_keeps_only_evidence_bound_items():
    raw = json.dumps(
        {
            "summary": "Toly says Solana XDP scaling is nearly ready.",
            "token_candidates": [
                {
                    "symbol": "SOL",
                    "project_name": "Solana",
                    "evidence": "Solana XDP scaling",
                    "confidence": 0.92,
                },
                {
                    "symbol": "FAKE",
                    "project_name": "Fake",
                    "evidence": "not in the tweet",
                    "confidence": 0.99,
                },
            ],
            "narratives": [
                {
                    "label": "Solana Scaling / XDP",
                    "description": "Solana throughput and XDP readiness",
                    "evidence": "XDP scaling is nearly ready",
                    "confidence": 0.88,
                }
            ],
            "stance": "informational",
            "intent": "technical_commentary",
            "confidence": 0.9,
        }
    )

    parsed = parse_enrichment_response(
        raw,
        event_text="Solana XDP scaling is nearly ready. 100m CU and 4kb txs are going live this year.",
    )

    assert parsed.summary == "Toly says Solana XDP scaling is nearly ready."
    assert [candidate.symbol for candidate in parsed.token_candidates] == ["SOL"]
    assert parsed.narratives[0].label == "solana_scaling_xdp"
    assert parsed.narratives[0].evidence == "XDP scaling is nearly ready"
    assert parsed.stance == "informational"
    assert parsed.intent == "technical_commentary"


def test_parse_enrichment_response_drops_low_confidence_and_invalid_labels():
    raw = json.dumps(
        {
            "summary": "Low confidence items should not become signals.",
            "token_candidates": [
                {"symbol": "SOL", "evidence": "Solana", "confidence": 0.2},
            ],
            "narratives": [
                {"label": "!!!", "description": "bad", "evidence": "Solana", "confidence": 0.9},
                {"label": "Solana", "description": "low", "evidence": "Solana", "confidence": 0.4},
            ],
            "stance": "wildly_bullish",
            "intent": "unknown_mode",
            "confidence": 0.5,
        }
    )

    parsed = parse_enrichment_response(raw, event_text="Solana")

    assert parsed.token_candidates == []
    assert parsed.narratives == []
    assert parsed.stance == "neutral"
    assert parsed.intent == "informational"


def test_enrichment_prompt_uses_search_text_and_parser_deduplicates_labels():
    messages = build_enrichment_prompt(
        event={
            "event_id": "reply-1",
            "author_handle": "toly",
            "text_clean": "@reply",
            "search_text": "@reply\nSolana XDP scaling is nearly ready",
        },
        entities=[],
    )
    prompt_payload = json.loads(messages[1]["content"])
    raw = json.dumps(
        {
            "summary": "Solana XDP scaling.",
            "token_candidates": [
                {"symbol": "SOL", "project_name": "Solana", "evidence": "Solana XDP", "confidence": 0.9},
                {"symbol": "SOL", "project_name": "Solana", "evidence": "Solana XDP", "confidence": 0.9},
            ],
            "narratives": [
                {
                    "label": "Solana Scaling",
                    "description": "Solana scaling",
                    "evidence": "XDP scaling",
                    "confidence": 0.9,
                },
                {
                    "label": "Solana Scaling",
                    "description": "Duplicate",
                    "evidence": "XDP scaling",
                    "confidence": 0.9,
                },
            ],
        }
    )

    parsed = parse_enrichment_response(raw, event_text=prompt_payload["text"])

    assert prompt_payload["text"] == "@reply\nSolana XDP scaling is nearly ready"
    assert len(parsed.token_candidates) == 1
    assert len(parsed.narratives) == 1
