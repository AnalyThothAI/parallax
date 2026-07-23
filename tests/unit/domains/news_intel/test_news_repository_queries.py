from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from parallax.domains.news_intel._constants import NEWS_PAGE_PROJECTION_VERSION
from parallax.domains.news_intel.repositories.news_item_repository import NewsItemRepository
from parallax.domains.news_intel.repositories.news_page_repository import NewsPageRepository
from parallax.domains.news_intel.repositories.news_repository_support import (
    _NEWS_ITEM_WORKER_COLUMNS_SQL,
    _page_row_payload,
)
from parallax.domains.news_intel.types.news_market_scope import NewsMarketScope
from parallax.domains.news_intel.types.news_story_identity import NewsStoryIdentity


class _Cursor:
    def __init__(self, rows: list[Mapping[str, Any]] | None = None, *, rowcount: int = 0) -> None:
        self.rows = [dict(row) for row in (rows or [])]
        self.rowcount = rowcount

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self.rows)

    def fetchone(self) -> dict[str, Any] | None:
        return self.rows[0] if self.rows else None


class _Connection:
    def __init__(self, cursors: list[_Cursor] | None = None) -> None:
        self.cursors = list(cursors or [])
        self.statements: list[tuple[str, Any]] = []

    def execute(self, sql: str, params: Any = None) -> _Cursor:
        self.statements.append((sql, params))
        return self.cursors.pop(0) if self.cursors else _Cursor()


def _page_row() -> dict[str, Any]:
    return {
        "row_id": "news-page:1",
        "news_item_id": "news-1",
        "representative_news_item_id": "news-1",
        "story_key": "story:1",
        "story": {
            "story_key": "story:1",
            "representative_news_item_id": "news-1",
            "member_news_item_ids": ["news-1"],
            "member_count": 1,
            "source_domains": ["example.test"],
        },
        "latest_at_ms": 1_000,
        "lifecycle_status": "accepted",
        "headline": "Coinbase lists NEWX",
        "summary": "Trading starts today",
        "source_domain": "example.test",
        "canonical_url": "https://example.test/newx",
        "canonical_item_key": "canonical-url:https://example.test/newx",
        "token_lanes": [],
        "fact_lanes": [{"event_type": "listing", "claim": "Coinbase lists NEWX"}],
        "provider_rating": {},
        "content_class": "market_moving",
        "content_tags": ["listing"],
        "content_classification": {"method": "deterministic"},
        "source": {"source_id": "source-1", "source_quality_status": "healthy"},
        "market_scope": {
            "scope": ["crypto"],
            "primary": "crypto",
            "status": "classified",
            "reason": "crypto_subject",
            "basis": {},
            "version": "test-market-scope-v1",
        },
        "duplicate_count": 1,
        "source_ids_json": ["source-1"],
        "source_domains_json": ["example.test"],
        "provider_article_keys_json": ["article-1"],
        "computed_at_ms": 2_000,
        "projection_version": NEWS_PAGE_PROJECTION_VERSION,
    }


def test_page_row_payload_contains_only_fact_projection_sections() -> None:
    payload = _page_row_payload(_page_row())

    assert payload["story_json"].obj["story_key"] == "story:1"
    assert payload["fact_lanes_json"].obj[0]["event_type"] == "listing"
    assert payload["market_scope_json"].obj["primary"] == "crypto"
    assert "agent_brief_json" not in payload
    assert "signal_json" not in payload


@pytest.mark.parametrize("field_name", ["signal", "agent_brief", "agent_admission", "macro_event_flow"])
def test_page_row_payload_rejects_retired_product_ai_fields(field_name: str) -> None:
    row = _page_row()
    row[field_name] = {}

    with pytest.raises(ValueError, match=f"news_page_row_payload_retired:{field_name}"):
        _page_row_payload(row)


def test_news_page_list_query_reads_fact_only_columns() -> None:
    conn = _Connection([_Cursor([])])

    assert NewsPageRepository(conn).list_news_page_rows(limit=10) == []

    sql, params = conn.statements[0]
    assert "fact_lanes_json AS fact_lanes" in sql
    assert "market_scope_json AS market_scope" in sql
    assert "agent_brief" not in sql
    assert "signal_json" not in sql
    assert params[-1] == 10


def test_story_projection_scope_has_no_model_admission_join() -> None:
    conn = _Connection([_Cursor([])])

    assert NewsPageRepository(conn).load_story_projection_payloads_for_items(news_item_ids=["news-1"]) == []

    sql, _params = conn.statements[0]
    assert "story_identity_version" in sql
    assert "agent_admission" not in sql
    assert "news_story_agent" not in sql


def test_news_item_worker_columns_have_no_model_state() -> None:
    assert "market_scope_json" in _NEWS_ITEM_WORKER_COLUMNS_SQL
    assert "agent_admission" not in _NEWS_ITEM_WORKER_COLUMNS_SQL


def test_update_market_scope_and_story_identity_is_fact_only() -> None:
    conn = _Connection([_Cursor(rowcount=1)])
    repo = NewsItemRepository(conn)

    repo.update_item_market_scope_and_story_identity(
        news_item_id="news-1",
        market_scope=NewsMarketScope(
            scope=("crypto",),
            primary="crypto",
            status="classified",
            reason="crypto_subject",
            basis={},
            version="market-v1",
        ),
        story_identity=NewsStoryIdentity(
            story_key="story:1",
            confidence="high",
            basis={},
            version="story-v1",
        ),
        now_ms=2_000,
    )

    sql, _params = conn.statements[0]
    assert "story_identity_json" in sql
    assert "market_scope_json" in sql
    assert "agent_admission" not in sql
