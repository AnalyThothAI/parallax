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
                    "seed_family": "solana_scaling",
                    "trigger_terms": ["Solana", "XDP"],
                    "market_interpretation": "Market may look for Solana throughput and XDP related tokens.",
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
    assert parsed.narratives[0].seed_family == "solana_scaling"
    assert parsed.narratives[0].trigger_terms == ["solana", "xdp"]
    assert parsed.narratives[0].market_interpretation == "Market may look for Solana throughput and XDP related tokens."
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
                {
                    "label": "!!!",
                    "description": "bad",
                    "seed_family": "solana",
                    "trigger_terms": ["Solana"],
                    "market_interpretation": "bad",
                    "evidence": "Solana",
                    "confidence": 0.9,
                },
                {
                    "label": "Solana",
                    "description": "low",
                    "seed_family": "solana",
                    "trigger_terms": ["Solana"],
                    "market_interpretation": "low",
                    "evidence": "Solana",
                    "confidence": 0.4,
                },
                {
                    "label": "Missing Seed Fields",
                    "description": "Old shape is intentionally rejected",
                    "evidence": "Solana",
                    "confidence": 0.9,
                },
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


def test_parse_enrichment_response_rejects_ungrounded_trigger_terms():
    raw = json.dumps(
        {
            "summary": "Grok product progress.",
            "narratives": [
                {
                    "label": "AI Agent Grok",
                    "description": "Grok product progress as an AI-agent attention seed",
                    "seed_family": "ai_agent",
                    "trigger_terms": ["Grok", "AI", "xAI token"],
                    "market_interpretation": "Market may look for AI agent tokens.",
                    "evidence": "Grok is getting scary good",
                    "confidence": 0.9,
                },
                {
                    "label": "Inferred AI Agent",
                    "description": "Ungrounded expansion should not become a seed",
                    "seed_family": "ai_agent",
                    "trigger_terms": ["AI agent"],
                    "market_interpretation": "Market may look for AI agent tokens.",
                    "evidence": "Grok is getting scary good",
                    "confidence": 0.9,
                },
            ],
        }
    )

    parsed = parse_enrichment_response(raw, event_text="Grok is getting scary good, he said")

    assert len(parsed.narratives) == 1
    assert parsed.narratives[0].trigger_terms == ["grok"]


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
                    "seed_family": "solana_scaling",
                    "trigger_terms": ["Solana", "XDP"],
                    "market_interpretation": "Market may look for Solana scaling tokens.",
                    "evidence": "XDP scaling",
                    "confidence": 0.9,
                },
                {
                    "label": "Solana Scaling",
                    "description": "Duplicate",
                    "seed_family": "solana_scaling",
                    "trigger_terms": ["Solana"],
                    "market_interpretation": "Duplicate.",
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
