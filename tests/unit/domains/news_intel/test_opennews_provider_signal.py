from __future__ import annotations

from gmgn_twitter_intel.domains.news_intel.services.opennews_provider_signal import (
    provider_signal_from_opennews_payload,
    provider_token_impacts_from_opennews_payload,
)


def test_opennews_provider_signal_reads_ai_rating() -> None:
    payload = {
        "id": 2367422,
        "newsType": "6551News",
        "engineType": "news",
        "aiRating": {
            "status": "done",
            "signal": "short",
            "score": 75,
            "grade": "A",
            "summary": "中文摘要",
            "enSummary": "English summary",
        },
    }

    assert provider_signal_from_opennews_payload(payload) == {
        "source": "provider",
        "provider": "opennews",
        "status": "ready",
        "direction": "bearish",
        "label_zh": "利空",
        "signal": "short",
        "score": 75,
        "grade": "A",
        "summary_zh": "中文摘要",
        "summary_en": "English summary",
        "method": "opennews.aiRating",
    }


def test_opennews_provider_token_impacts_preserve_coin_scores() -> None:
    payload = {
        "coins": [
            {"symbol": "BTC", "market_type": "cex", "score": 75, "signal": "short", "grade": "A"},
            {"symbol": "ETH", "market_type": "cex", "score": 70, "signal": "long", "grade": "B+"},
        ]
    }

    assert provider_token_impacts_from_opennews_payload(payload) == [
        {"symbol": "BTC", "market_type": "cex", "score": 75, "signal": "short", "grade": "A"},
        {"symbol": "ETH", "market_type": "cex", "score": 70, "signal": "long", "grade": "B+"},
    ]


def test_opennews_provider_signal_marks_missing_ai_rating_as_partial() -> None:
    payload = {"newsType": "6551News", "engineType": "news", "coins": [{"symbol": "EX"}]}

    assert provider_signal_from_opennews_payload(payload) == {
        "source": "provider",
        "provider": "opennews",
        "status": "partial",
        "direction": "neutral",
        "label_zh": "中性",
        "signal": None,
        "score": None,
        "grade": None,
        "summary_zh": None,
        "summary_en": None,
        "method": "opennews.partial",
    }


def test_opennews_provider_signal_marks_done_without_score_as_ready() -> None:
    payload = {"aiRating": {"status": "done"}}

    assert provider_signal_from_opennews_payload(payload) == {
        "source": "provider",
        "provider": "opennews",
        "status": "ready",
        "direction": "neutral",
        "label_zh": "中性",
        "signal": None,
        "score": None,
        "grade": None,
        "summary_zh": None,
        "summary_en": None,
        "method": "opennews.aiRating",
    }
