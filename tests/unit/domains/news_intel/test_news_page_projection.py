from __future__ import annotations

from gmgn_twitter_intel.domains.news_intel._constants import NEWS_PAGE_PROJECTION_VERSION
from gmgn_twitter_intel.domains.news_intel.services.news_page_projection import build_news_page_row


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
        story={"story_id": "story-1", "item_count": 2, "source_count": 1},
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
    assert row["story"] == {"story_id": "story-1", "item_count": 2, "source_count": 1}
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
        story=None,
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
        story=None,
        token_mentions=[],
        fact_candidates=[],
        computed_at_ms=2000,
    )
    second = build_news_page_row(
        item=item,
        story={"story_id": "story-1"},
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
        story=None,
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
        story=None,
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
        story=None,
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
        story=None,
        token_mentions=[],
        fact_candidates=[],
        computed_at_ms=4000,
    )

    assert row["agent_status"] == "pending"
    assert row["agent_brief_status"] == "pending"
    assert row["agent_brief_computed_at_ms"] is None
    assert row["agent_brief_json"] == {"status": "pending"}
