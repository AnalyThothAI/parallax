from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.domains.news_intel.repositories.news_repository import NewsRepository


def test_page_projection_candidate_query_compares_persisted_source_payload() -> None:
    conn = CapturingConnection()
    repo = NewsRepository(conn)

    rows = repo.list_items_for_page_projection(limit=10)

    assert rows == []
    assert "JOIN news_sources AS sources ON sources.source_id = items.source_id" in conn.sql
    assert "page.source_json ->> 'provider_type' IS DISTINCT FROM sources.provider_type" in conn.sql
    assert "page.source_json ->> 'source_quality_status' IS DISTINCT FROM sources.source_quality_status" in conn.sql
    assert "COALESCE(page.source_json -> 'coverage_tags', '[]'::jsonb) <> sources.coverage_tags_json" in conn.sql


class CapturingConnection:
    def __init__(self) -> None:
        self.sql = ""
        self.params: object = None

    def execute(self, sql: str, params: object = None) -> CapturingCursor:
        self.sql = sql
        self.params = params
        return CapturingCursor()


class CapturingCursor:
    def fetchall(self) -> list[dict[str, Any]]:
        return []
