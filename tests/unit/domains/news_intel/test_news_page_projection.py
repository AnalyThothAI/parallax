from __future__ import annotations

import pytest

from parallax.domains.news_intel._constants import NEWS_PAGE_PROJECTION_VERSION
from parallax.domains.news_intel.services.news_page_projection import build_news_page_row


def _item(**overrides: object) -> dict[str, object]:
    item: dict[str, object] = {
        "news_item_id": "news-1",
        "title": "Coinbase lists NEWX",
        "summary": "Trading starts today",
        "source_id": "source-1",
        "source_domain": "example.test",
        "source_quality_status": "healthy",
        "published_at_ms": 1_000,
        "canonical_url": "https://example.test/newx",
        "canonical_item_key": "canonical-url:https://example.test/newx",
        "lifecycle_status": "processed",
        "content_class": "market_moving",
        "content_tags_json": ["listing"],
        "content_classification_json": {"method": "deterministic"},
        "market_scope_json": {
            "scope": ["crypto"],
            "primary": "crypto",
            "status": "classified",
            "reason": "crypto_subject",
            "basis": {"subject": "exchange_listing"},
            "version": "test-market-scope-v1",
        },
    }
    item.update(overrides)
    return item


def _story(**overrides: object) -> dict[str, object]:
    story: dict[str, object] = {
        "story_key": "story:newx",
        "representative_news_item_id": "news-1",
        "member_news_item_ids": ["news-1"],
        "member_count": 1,
        "source_domains": ["example.test"],
        "source_ids": ["source-1"],
        "provider_article_keys": ["article-1"],
    }
    story.update(overrides)
    return story


def _row(**item_overrides: object) -> dict[str, object]:
    return build_news_page_row(
        item=_item(**item_overrides),
        token_mentions=[
            {
                "resolution_status": "known_symbol",
                "display_symbol": "NEWX",
                "target_type": "CexToken",
                "target_id": "cex_token:newx",
            }
        ],
        fact_candidates=[
            {
                "fact_candidate_id": "fact-1",
                "event_type": "listing",
                "claim": "Coinbase lists NEWX",
                "realis": "actual",
                "validation_status": "accepted",
            }
        ],
        story=_story(),
        computed_at_ms=5_000,
    )


def test_build_news_page_row_is_fact_only() -> None:
    row = _row()

    assert row["projection_version"] == NEWS_PAGE_PROJECTION_VERSION
    assert row["latest_at_ms"] == 1_000
    assert row["lifecycle_status"] == "accepted"
    assert row["token_lanes"][0]["target_id"] == "cex_token:newx"
    assert row["fact_lanes"][0]["claim"] == "Coinbase lists NEWX"
    assert row["market_scope"]["primary"] == "crypto"
    assert not ({"signal", "agent_brief", "agent_status", "agent_admission", "macro_event_flow"} & row.keys())


def test_build_news_page_row_has_stable_story_identity() -> None:
    first = _row(title="First headline")
    second = _row(title="Updated headline")

    assert first["row_id"] == second["row_id"]


@pytest.mark.parametrize("published_at_ms", [True, "1000", 0])
def test_build_news_page_row_requires_canonical_publication_time(published_at_ms: object) -> None:
    with pytest.raises(ValueError, match="news_page_projection_published_at_required:news-1"):
        _row(published_at_ms=published_at_ms)


def test_build_news_page_row_requires_story() -> None:
    with pytest.raises(ValueError, match="news_page_projection_story_required:news-1"):
        build_news_page_row(
            item=_item(),
            token_mentions=[],
            fact_candidates=[],
            story=None,
            computed_at_ms=5_000,
        )


def test_build_news_page_row_search_text_uses_fact_lanes() -> None:
    row = _row()

    assert "NEWX" in str(row["search_text"])
    assert "Coinbase lists NEWX" in str(row["search_text"])
