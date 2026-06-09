from __future__ import annotations

import inspect

from parallax.domains.news_intel.repositories import news_repository


def test_news_page_filter_sql_has_no_retired_score_threshold() -> None:
    assert "min_score" not in inspect.signature(news_repository._news_page_row_filter_sql).parameters

    filter_sql, filter_params = news_repository._news_page_row_filter_sql(signal="bullish", q="btc")

    assert filter_params == ["bullish", "%btc%"]
    assert "display_signal' ->> 'score" not in filter_sql
    assert "signal_json -> 'display_signal' ->> 'score" not in filter_sql
