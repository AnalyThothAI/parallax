from __future__ import annotations

from parallax.domains.news_intel._constants import NEWS_PAGE_PROJECTION_VERSION
from parallax.domains.news_intel.services.news_page_projection import build_news_page_row


def test_build_news_page_row_includes_token_and_fact_lanes() -> None:
    row = build_news_page_row(
        item={
            "news_item_id": "news-1",
            "title": "Coinbase lists NEWX",
            "summary": "Trading starts today",
            "source_id": "example-rss",
            "source_domain": "example.test",
            "canonical_url": "https://example.test/a",
            "published_at_ms": 1000,
            "lifecycle_status": "processed",
        },
        token_mentions=[
            {
                "resolution_status": "unknown_attention",
                "display_symbol": "NEWX",
                "target_id": None,
                "reason_codes_json": ["SYMBOL_NOT_IN_REGISTRY"],
            }
        ],
        fact_candidates=[
            {
                "event_type": "listing",
                "validation_status": "attention",
                "rejection_reasons_json": ["target_identity_not_production_eligible"],
            }
        ],
        computed_at_ms=2000,
    )

    assert row["lifecycle_status"] == "attention"
    assert row["token_lanes"][0]["lane"] == "attention"
    assert row["token_lanes"][0]["reason_codes"] == ["SYMBOL_NOT_IN_REGISTRY"]
    assert row["fact_lanes"][0]["status"] == "attention"
    assert "story" not in row
    assert "story_id" not in row
    assert row["source"] == {
        "source_id": "example-rss",
        "source_domain": "example.test",
        "coverage_tags": [],
    }
    assert row["projection_version"] == NEWS_PAGE_PROJECTION_VERSION


def test_build_news_page_row_includes_compact_source_classification() -> None:
    row = build_news_page_row(
        item={
            "news_item_id": "news-1",
            "title": "Coinbase lists NEWX",
            "summary": "Trading starts today",
            "source_id": "coinbase-announcements",
            "provider_type": "rss",
            "source_domain": "coinbase.com",
            "source_name": "Coinbase Announcements",
            "source_role": "official_exchange",
            "trust_tier": "official",
            "coverage_tags_json": ["crypto_exchange", "exchange_listing"],
            "source_quality_status": "healthy",
            "canonical_url": "https://coinbase.com/a",
            "published_at_ms": 1000,
        },
        token_mentions=[],
        fact_candidates=[],
        computed_at_ms=2000,
    )

    assert row["source"] == {
        "source_id": "coinbase-announcements",
        "provider_type": "rss",
        "source_domain": "coinbase.com",
        "source_name": "Coinbase Announcements",
        "source_role": "official_exchange",
        "trust_tier": "official",
        "coverage_tags": ["crypto_exchange", "exchange_listing"],
        "source_quality_status": "healthy",
    }


def test_build_news_page_row_copies_item_level_content_classification() -> None:
    row = build_news_page_row(
        item={
            "news_item_id": "news-1",
            "title": "SEC delays tokenized stock decision",
            "summary": "The filing remains open.",
            "source_domain": "example.test",
            "canonical_url": "https://example.test/sec",
            "published_at_ms": 1000,
            "content_class": "regulation",
            "content_tags_json": ("sec", "tokenized_stocks"),
            "content_classification_json": {
                "policy_version": "news_content_classification_v1",
                "matched_rules": ["regulatory_body"],
                "none_value": None,
            },
        },
        token_mentions=[],
        fact_candidates=[],
        computed_at_ms=2000,
    )

    assert row["content_class"] == "regulation"
    assert row["content_tags"] == ["sec", "tokenized_stocks"]
    assert row["content_tags_json"] == ["sec", "tokenized_stocks"]
    assert row["content_classification"] == {
        "policy_version": "news_content_classification_v1",
        "matched_rules": ["regulatory_body"],
    }
    assert row["content_classification_json"] == row["content_classification"]


def test_build_news_page_row_uses_stable_row_id() -> None:
    item = {
        "news_item_id": "news-1",
        "title": "Coinbase lists NEWX",
        "summary": "",
        "source_domain": "example.test",
        "canonical_url": "https://example.test/a",
        "published_at_ms": 1000,
    }

    first = build_news_page_row(
        item=item,
        token_mentions=[],
        fact_candidates=[],
        computed_at_ms=2000,
    )
    second = build_news_page_row(
        item=item,
        token_mentions=[],
        fact_candidates=[],
        computed_at_ms=3000,
    )

    assert first["row_id"] == second["row_id"]
    assert first["row_id"] != "news-1"


def test_build_news_page_row_marks_attention_for_unknown_token_without_facts() -> None:
    row = build_news_page_row(
        item={
            "news_item_id": "news-1",
            "title": "NEWX rallies",
            "summary": "",
            "source_domain": "example.test",
            "canonical_url": "https://example.test/a",
            "published_at_ms": 1000,
            "lifecycle_status": "processed",
        },
        token_mentions=[
            {
                "resolution_status": "unknown_attention",
                "display_symbol": "NEWX",
                "target_id": None,
            }
        ],
        fact_candidates=[],
        computed_at_ms=2000,
    )

    assert row["lifecycle_status"] == "attention"


def test_build_news_page_row_marks_accepted_when_no_attention_lanes() -> None:
    row = build_news_page_row(
        item={
            "news_item_id": "news-1",
            "title": "BTC ETF accepted",
            "summary": "",
            "source_domain": "example.test",
            "canonical_url": "https://example.test/a",
            "published_at_ms": 1000,
            "lifecycle_status": "processed",
        },
        token_mentions=[
            {
                "resolution_status": "known_symbol",
                "display_symbol": "BTC",
                "target_type": "cex_token",
                "target_id": "BTC",
            }
        ],
        fact_candidates=[{"event_type": "listing", "validation_status": "accepted"}],
        computed_at_ms=2000,
    )

    assert row["lifecycle_status"] == "accepted"
    assert row["token_lanes"][0]["lane"] == "resolved"


def test_build_news_page_row_includes_ready_compact_agent_brief() -> None:
    row = build_news_page_row(
        item={
            "news_item_id": "news-1",
            "title": "SOL ETF filing",
            "summary": "",
            "source_domain": "example.test",
            "canonical_url": "https://example.test/a",
            "published_at_ms": 1000,
        },
        token_mentions=[],
        fact_candidates=[],
        agent_brief={
            "agent_run_id": "run-1",
            "status": "ready",
            "direction": "bullish",
            "decision_class": "driver",
            "brief_json": {
                "summary_zh": "SOL ETF 申请提升关注。",
                "market_read_zh": "叙事催化增强。",
                "bull_view": {"strength": "strong", "thesis_zh": "新增需求预期"},
                "bear_view": {"strength": "weak", "thesis_zh": "审批仍不确定"},
                "data_gaps": [{"kind": "price_reaction"}],
            },
            "input_hash": "input-1",
            "artifact_version_hash": "artifact-1",
            "prompt_version": "prompt-v1",
            "schema_version": "schema-v1",
            "computed_at_ms": 3000,
        },
        computed_at_ms=4000,
    )

    assert row["agent_status"] == "ready"
    assert row["agent_brief_status"] == "ready"
    assert row["agent_brief_computed_at_ms"] == 3000
    assert row["agent_brief"] == row["agent_brief_json"]
    assert row["agent_brief_json"] == {
        "status": "ready",
        "direction": "bullish",
        "decision_class": "driver",
        "summary_zh": "SOL ETF 申请提升关注。",
        "market_read_zh": "叙事催化增强。",
        "bull_strength": "strong",
        "bear_strength": "weak",
        "data_gap_count": 1,
        "computed_at_ms": 3000,
        "agent_run_id": "run-1",
        "schema_version": "schema-v1",
        "prompt_version": "prompt-v1",
        "artifact_version_hash": "artifact-1",
        "input_hash": "input-1",
        "bull_view": {"strength": "strong", "thesis_zh": "新增需求预期"},
        "bear_view": {"strength": "weak", "thesis_zh": "审批仍不确定"},
    }


def test_build_news_page_row_preserves_provider_signal_without_masking_ready_agent_brief() -> None:
    row = build_news_page_row(
        item={
            "news_item_id": "news-1",
            "title": "SOL ETF filing",
            "summary": "",
            "source_domain": "example.test",
            "canonical_url": "https://example.test/a",
            "published_at_ms": 1000,
            "provider_signal_json": {
                "source": "provider",
                "provider": "opennews",
                "status": "ready",
                "direction": "bullish",
                "signal": "long",
                "score": 92,
                "grade": "A",
                "summary_en": "Provider summary",
                "method": "opennews.aiRating",
            },
        },
        token_mentions=[],
        fact_candidates=[],
        agent_brief={
            "agent_run_id": "run-1",
            "status": "ready",
            "direction": "bearish",
            "decision_class": "watch",
            "brief_json": {
                "summary_zh": "Agent sees event risk.",
                "market_read_zh": "风险仍待确认。",
                "bull_view": {"strength": "weak"},
                "bear_view": {"strength": "moderate"},
            },
            "computed_at_ms": 3000,
        },
        computed_at_ms=4000,
    )

    assert row["agent_status"] == "ready"
    assert row["agent_brief_status"] == "ready"
    assert row["signal"]["source"] == "agent"
    assert row["signal"]["direction"] == "bearish"
    assert row["signal"]["score"] == 92
    assert row["signal"]["provider_signal"] == {
        "source": "provider",
        "provider": "opennews",
        "status": "ready",
        "direction": "bullish",
        "label_zh": "利好",
        "signal": "long",
        "score": 92,
        "grade": "A",
        "summary_en": "Provider summary",
        "method": "opennews.aiRating",
    }
    assert row["signal"]["alert_eligibility"] == {
        "agent_status": "ready",
        "decision_class": "watch",
        "provider_status": "ready",
        "provider_score": 92,
        "in_app_eligible": True,
        "external_push_ready": True,
        "external_push_basis": "agent_brief",
    }


def test_build_news_page_row_keeps_provider_candidate_separate_from_external_push_ready() -> None:
    row = build_news_page_row(
        item={
            "news_item_id": "news-1",
            "title": "High score provider alert",
            "summary": "",
            "source_domain": "example.test",
            "canonical_url": "https://example.test/a",
            "published_at_ms": 1000,
            "provider_signal_json": {
                "source": "provider",
                "provider": "opennews",
                "status": "ready",
                "direction": "bullish",
                "signal": "long",
                "score": 90,
                "grade": "A",
                "summary_zh": "Provider summary.",
                "method": "opennews.aiRating",
            },
        },
        token_mentions=[],
        fact_candidates=[],
        agent_brief={
            "agent_run_id": "run-1",
            "status": "insufficient",
            "direction": "neutral",
            "decision_class": "context",
            "brief_json": {
                "summary_zh": "证据不足，不能形成 agent brief。",
                "data_gaps": [{"kind": "missing_context"}],
            },
            "computed_at_ms": 3000,
        },
        computed_at_ms=4000,
    )

    eligibility = row["signal"]["alert_eligibility"]
    assert eligibility["in_app_eligible"] is True
    assert eligibility["external_push_ready"] is False
    assert eligibility["external_push_block_reason"] == "agent_brief_not_ready"


def test_build_news_page_row_uses_pending_agent_brief_when_missing() -> None:
    row = build_news_page_row(
        item={
            "news_item_id": "news-1",
            "title": "SOL ETF filing",
            "summary": "",
            "source_domain": "example.test",
            "canonical_url": "https://example.test/a",
            "published_at_ms": 1000,
        },
        token_mentions=[],
        fact_candidates=[],
        computed_at_ms=4000,
    )

    assert row["agent_status"] == "pending"
    assert row["agent_brief_status"] == "pending"
    assert row["agent_brief_computed_at_ms"] is None
    assert row["agent_brief_json"] == {"status": "pending"}
