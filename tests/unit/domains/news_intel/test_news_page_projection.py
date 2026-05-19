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
    assert row["source"] == {"source_id": "example-rss", "source_domain": "example.test"}
    assert row["projection_version"] == NEWS_PAGE_PROJECTION_VERSION


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
