from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.domains.news_intel.repositories.news_repository import NewsRepository


def test_page_projection_loader_reads_source_payload_for_claimed_targets() -> None:
    conn = CapturingConnection()
    repo = NewsRepository(conn)

    rows = repo.load_items_for_page_projection(news_item_ids=["news-1"])

    assert rows == []
    assert "WHERE items.news_item_id = ANY(%s::text[])" in conn.sql
    assert "JOIN news_sources AS sources ON sources.source_id = items.source_id" in conn.sql
    assert "'provider_type', sources.provider_type" in conn.sql
    assert "'source_quality_status', sources.source_quality_status" in conn.sql
    assert "'coverage_tags_json', sources.coverage_tags_json" in conn.sql


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
