from __future__ import annotations

from parallax.domains.news_intel.repositories import news_repository


def test_news_page_min_score_filter_uses_literal_threshold_for_partial_index() -> None:
    filter_sql, filter_params = news_repository._news_page_row_filter_sql(min_score=80)

    assert filter_params == []
    assert "COALESCE(NULLIF(signal_json -> 'display_signal' ->> 'score', '')::int, -1) >= 80" in filter_sql
