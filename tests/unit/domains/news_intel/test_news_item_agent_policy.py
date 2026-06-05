from __future__ import annotations

from parallax.domains.news_intel.services.news_item_agent_policy import (
    NEWS_ITEM_AGENT_BRIEF_MAX_PUBLISHED_AGE_MS,
    NEWS_ITEM_AGENT_BRIEF_MIN_PROVIDER_SCORE,
    decide_news_item_agent_requirement,
    news_item_agent_brief_priority,
)

NOW_MS = 2_000_000_000_000


def _item(**overrides):
    item = {
        "news_item_id": "news-1",
        "published_at_ms": NOW_MS - 60_000,
        "lifecycle_status": "processed",
        "content_class": "exchange_listing",
        "content_classification_json": {"policy_version": "news_content_classification_v1"},
        "analysis_admission_status": "admitted",
        "analysis_admission_json": {
            "status": "admitted",
            "basis": {"crypto_evidence": ["resolved_crypto_target:cex:BTC"]},
        },
        "provider_signal_json": {
            "source": "provider",
            "status": "ready",
            "score": NEWS_ITEM_AGENT_BRIEF_MIN_PROVIDER_SCORE,
        },
    }
    item.update(overrides)
    return item


def test_news_item_agent_brief_requires_processed_item_state() -> None:
    result = decide_news_item_agent_requirement(
        item=_item(lifecycle_status="raw"),
        now_ms=NOW_MS,
    )

    assert result.required is False
    assert result.status == "not_required"
    assert result.reason == "item_not_processed"


def test_news_item_agent_brief_rejects_provider_score_without_analysis_admission() -> None:
    result = decide_news_item_agent_requirement(
        item=_item(
            analysis_admission_status="page_only",
            analysis_admission_json={
                "status": "page_only",
                "basis": {"provider_evidence": ["provider_score:95"]},
            },
            provider_signal_json={"source": "provider", "status": "ready", "score": 95},
        ),
        now_ms=NOW_MS,
    )

    assert result.required is False
    assert result.status == "not_required"
    assert result.reason == "analysis_not_admitted"


def test_news_item_agent_brief_requires_classification() -> None:
    result = decide_news_item_agent_requirement(
        item=_item(content_classification_json={}),
        now_ms=NOW_MS,
    )

    assert result.required is False
    assert result.reason == "classification_missing"


def test_news_item_agent_brief_requires_provider_score_at_or_above_analysis_floor() -> None:
    assert NEWS_ITEM_AGENT_BRIEF_MIN_PROVIDER_SCORE == 80
    result = decide_news_item_agent_requirement(
        item=_item(),
        now_ms=NOW_MS,
    )

    assert result.required is True
    assert result.status == "required"
    assert result.reason == "eligible"


def test_news_item_agent_brief_rejects_below_threshold_provider_scores() -> None:
    result = decide_news_item_agent_requirement(
        item=_item(provider_signal_json={"source": "provider", "status": "ready", "score": 64}),
        now_ms=NOW_MS,
    )

    assert result.required is False
    assert result.reason == "below_score_threshold"


def test_news_item_agent_brief_rejects_non_provider_or_missing_score() -> None:
    non_provider = decide_news_item_agent_requirement(
        item=_item(provider_signal_json={"source": "manual", "status": "ready", "score": 100}),
        now_ms=NOW_MS,
    )
    missing_score = decide_news_item_agent_requirement(
        item=_item(provider_signal_json={"source": "provider", "status": "ready"}),
        now_ms=NOW_MS,
    )

    assert non_provider.required is False
    assert non_provider.reason == "source_not_provider_signal"
    assert missing_score.required is False
    assert missing_score.reason == "missing_provider_score"


def test_news_item_agent_brief_rejects_admitted_low_provider_score_even_with_explicit_crypto_evidence() -> None:
    result = decide_news_item_agent_requirement(
        item=_item(
            provider_signal_json={"source": "provider", "status": "ready", "score": 72},
            analysis_admission_json={
                "status": "admitted",
                "basis": {"crypto_evidence": ["text:crypto_subject"]},
            },
        ),
        now_ms=NOW_MS,
    )

    assert result.required is False
    assert result.reason == "below_score_threshold"
    assert news_item_agent_brief_priority(
        item=_item(provider_signal_json={"source": "provider", "score": 95}),
    ) < news_item_agent_brief_priority(
        item=_item(provider_signal_json={"source": "provider", "score": 72}),
    )


def test_decide_news_item_agent_requirement_returns_persistable_contract() -> None:
    result = decide_news_item_agent_requirement(
        item=_item(provider_signal_json={"source": "provider", "status": "ready", "score": 90}),
        now_ms=NOW_MS,
    )

    assert result.status == "required"
    assert result.reason == "eligible"
    assert result.priority == 10
    assert result.basis["provider_score"] == 90
    assert result.basis["analysis_admission_status"] == "admitted"


def test_news_item_agent_brief_requires_fresh_published_at() -> None:
    assert NEWS_ITEM_AGENT_BRIEF_MAX_PUBLISHED_AGE_MS == 8 * 3_600_000
    missing_published = decide_news_item_agent_requirement(
        item=_item(published_at_ms=None),
        now_ms=NOW_MS,
    )
    too_old = decide_news_item_agent_requirement(
        item=_item(published_at_ms=NOW_MS - NEWS_ITEM_AGENT_BRIEF_MAX_PUBLISHED_AGE_MS - 1),
        now_ms=NOW_MS,
    )
    future = decide_news_item_agent_requirement(
        item=_item(published_at_ms=NOW_MS + 1),
        now_ms=NOW_MS,
    )

    assert missing_published.required is False
    assert missing_published.reason == "published_at_missing"
    assert too_old.required is False
    assert too_old.reason == "published_too_old"
    assert future.required is False
    assert future.reason == "published_in_future"


def test_news_item_agent_brief_priority_keeps_higher_provider_scores_first() -> None:
    assert news_item_agent_brief_priority(
        item=_item(provider_signal_json={"source": "provider", "score": 95}),
    ) < news_item_agent_brief_priority(
        item=_item(provider_signal_json={"source": "provider", "score": 72}),
    )
