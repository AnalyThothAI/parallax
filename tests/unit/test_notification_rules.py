from __future__ import annotations

from dataclasses import replace

import pytest

from parallax.domains.news_intel.interfaces import NewsNotificationCandidate
from parallax.domains.notifications.services.notification_rules import NotificationRuleEngine
from parallax.platform.config.settings import NotificationsConfig, Settings

NOW_MS = 1_700_000_300_000


class FakeEvidence:
    def __init__(self, events: list[dict[str, object]] | None = None) -> None:
        self.events = events or []
        self.calls: list[dict[str, object]] = []

    def recent_events(self, **kwargs: object) -> list[dict[str, object]]:
        self.calls.append(kwargs)
        return self.events


class FakeAccountAlerts:
    def __init__(self, alerts: list[dict[str, object]] | None = None) -> None:
        self.alerts = alerts or []
        self.calls: list[dict[str, object]] = []

    def account_alerts(self, **kwargs: object) -> list[dict[str, object]]:
        self.calls.append(kwargs)
        return self.alerts


class FakeNews:
    def __init__(self, rows: list[NewsNotificationCandidate]) -> None:
        self.rows = rows
        self.calls: list[dict[str, int]] = []

    def list_news_high_signal_notification_candidates(self, **kwargs: int) -> list[NewsNotificationCandidate]:
        self.calls.append(kwargs)
        return self.rows


def _news_candidate(**overrides: object) -> NewsNotificationCandidate:
    values: dict[str, object] = {
        "row_id": "news-page-row:news-1",
        "news_item_id": "news-1",
        "representative_news_item_id": "news-1",
        "story_key": "news-story:unit:one",
        "latest_at_ms": NOW_MS - 5_000,
        "headline": "Major listing catalyst",
        "source_domain": "example.test",
        "canonical_url": "https://example.test/news-1",
        "direction": "bullish",
        "decision_class": "driver",
        "title_zh": "重大上所催化",
        "projected_title_zh": "投影标题",
        "summary_zh": "新闻 Agent 已归纳关键催化。",
        "affected_symbols": ("BOV",),
        "token_symbols": ("XYZ-BOV",),
        "external_push_ready": True,
        "external_push_basis": "agent_brief",
        "external_push_block_reason": None,
    }
    values.update(overrides)
    return NewsNotificationCandidate(**values)  # type: ignore[arg-type]


def _engine(
    *,
    events: list[dict[str, object]] | None = None,
    alerts: list[dict[str, object]] | None = None,
    news: FakeNews | None = None,
    notifications: NotificationsConfig | None = None,
) -> NotificationRuleEngine:
    return NotificationRuleEngine(
        settings=Settings(
            ws_token="secret",
            handles=("toly",),
            notifications=notifications or NotificationsConfig(),
        ),
        evidence=FakeEvidence(events),
        account_alerts=FakeAccountAlerts(alerts),
        news=news,
    )


def _news_candidates(rule_engine: NotificationRuleEngine) -> list[object]:
    return [candidate for candidate in rule_engine.evaluate(now_ms=NOW_MS) if candidate.rule_id == "news_high_signal"]


def test_account_activity_uses_material_event_identity_and_cooldown_bucket() -> None:
    rule_engine = _engine(
        events=[
            {
                "event_id": "event-1",
                "author_handle": "toly",
                "action": "tweet",
                "received_at_ms": NOW_MS - 10_000,
                "text_clean": "building on base",
            }
        ]
    )

    candidate = next(item for item in rule_engine.evaluate(now_ms=NOW_MS) if item.rule_id == "watched_account_activity")

    assert candidate.dedup_key == f"watched_account_activity:account:toly:tweet:{(NOW_MS - 10_000) // 300_000}"
    assert candidate.source_table == "events"
    assert candidate.source_id == "event-1"
    assert candidate.payload == {
        "event_id": "event-1",
        "author_handle": "toly",
        "action": "tweet",
        "received_at_ms": NOW_MS - 10_000,
    }


@pytest.mark.parametrize("received_at_ms", (None, 0, True, "1700000000000"))
def test_account_activity_rejects_invalid_material_timestamp(received_at_ms: object) -> None:
    with pytest.raises(ValueError, match="notification_source_timestamp_required"):
        _engine(
            events=[
                {
                    "event_id": "event-1",
                    "author_handle": "toly",
                    "action": "tweet",
                    "received_at_ms": received_at_ms,
                }
            ]
        ).evaluate(now_ms=NOW_MS)


def test_account_token_alert_preserves_source_identity_and_first_seen_flags() -> None:
    rule_engine = _engine(
        alerts=[
            {
                "alert_id": "alert-1",
                "event_id": "event-1",
                "author_handle": "toly",
                "normalized_value": "PEPE",
                "entity_key": "symbol:PEPE",
                "received_at_ms": NOW_MS - 10_000,
                "is_first_seen_global": True,
                "is_first_seen_by_author": True,
            }
        ]
    )

    candidate = next(
        item for item in rule_engine.evaluate(now_ms=NOW_MS) if item.rule_id == "watched_account_token_alert"
    )

    assert candidate.dedup_key == (
        f"watched_account_token_alert:symbol:PEPE:author:toly:{(NOW_MS - 10_000) // 900_000}"
    )
    assert candidate.severity == "warning"
    assert candidate.source_id == "alert-1"
    assert candidate.payload["is_first_seen_global"] is True


def test_formal_query_windows_and_news_overscan_are_forwarded() -> None:
    notifications = NotificationsConfig(
        candidate_limit=4,
        watched_activity_window_ms=2 * 60 * 60_000,
        news_high_signal_recency_window_ms=10_000,
        news_high_signal_query_min_limit=7,
        news_high_signal_query_multiplier=3,
    )
    news = FakeNews([])
    rule_engine = _engine(news=news, notifications=notifications)

    rule_engine.evaluate(now_ms=NOW_MS)

    assert rule_engine.evidence.calls == [
        {
            "limit": 4,
            "since_ms": NOW_MS - 2 * 60 * 60_000,
            "watched_only": True,
        }
    ]
    assert news.calls == [{"limit": 12, "since_ms": NOW_MS - 10_000}]


def test_news_candidate_uses_agent_display_and_writes_only_delivery_contract() -> None:
    candidate = _news_candidates(_engine(news=FakeNews([_news_candidate()])))[0]

    assert candidate.title == "重大上所催化"
    assert candidate.body == "Source: example.test\n新闻 Agent 已归纳关键催化。\nhttps://example.test/news-1"
    assert candidate.entity_key == "news_story:news-story:unit:one"
    assert candidate.symbol == "BOV"
    assert candidate.channels == ("in_app", "pushdeer")
    assert candidate.dedup_key == f"news_high_signal:{candidate.payload['semantic_signature']}"
    assert set(candidate.payload) == {
        "news_item_id",
        "representative_news_item_id",
        "story_key",
        "decision_class",
        "direction",
        "symbols",
        "semantic_signature",
        "display_title",
        "summary",
        "canonical_url",
        "source_domain",
        "external_push_signature",
        "external_push_eligible",
        "external_push_suppression_reason",
    }
    assert candidate.payload["symbols"] == ["BOV"]
    assert candidate.payload["external_push_eligible"] is True
    assert candidate.payload["external_push_suppression_reason"] is None


def test_news_candidate_stays_in_app_when_delivery_readiness_is_incomplete() -> None:
    candidate = _news_candidates(
        _engine(
            news=FakeNews(
                [
                    _news_candidate(
                        summary_zh=None,
                        external_push_ready=False,
                        external_push_block_reason="agent_brief_missing_summary",
                    )
                ]
            )
        )
    )[0]

    assert candidate.channels == ("in_app",)
    assert candidate.payload["external_push_eligible"] is False
    assert candidate.payload["external_push_signature"] is None
    assert candidate.payload["external_push_suppression_reason"] == "agent_brief_missing_summary"


def test_news_candidate_does_not_fabricate_external_delivery_without_external_channel() -> None:
    notifications = NotificationsConfig(
        rules={"news_high_signal": {"enabled": True, "channels": ["in_app"], "cooldown_seconds": 3600}}
    )

    candidate = _news_candidates(_engine(news=FakeNews([_news_candidate()]), notifications=notifications))[0]

    assert candidate.channels == ("in_app",)
    assert candidate.payload["external_push_eligible"] is False
    assert candidate.payload["external_push_suppression_reason"] == "external_channel_unavailable"


@pytest.mark.parametrize(
    ("candidate", "expected"),
    [
        (_news_candidate(title_zh=None), "投影标题"),
        (_news_candidate(title_zh=None, projected_title_zh=None), "Major listing catalyst"),
        (_news_candidate(title_zh=None, projected_title_zh=None, headline=None), "News high signal"),
    ],
)
def test_news_display_title_has_one_explicit_fallback_chain(
    candidate: NewsNotificationCandidate,
    expected: str,
) -> None:
    emitted = _news_candidates(_engine(news=FakeNews([candidate])))[0]
    assert emitted.title == expected


def test_news_rule_defensively_skips_stale_projected_rows() -> None:
    notifications = NotificationsConfig(news_high_signal_recency_window_ms=10_000)
    stale = _news_candidate(latest_at_ms=NOW_MS - 10_001)

    assert _news_candidates(_engine(news=FakeNews([stale]), notifications=notifications)) == []


def test_news_semantic_dedup_ignores_title_summary_and_projection_row_churn() -> None:
    first = _news_candidate()
    refreshed = replace(
        first,
        row_id="news-page-row:news-1-refreshed",
        title_zh="改写标题",
        summary_zh="改写摘要",
    )

    candidates = _news_candidates(_engine(news=FakeNews([first, refreshed])))

    assert len(candidates) == 1
    assert candidates[0].source_id == first.row_id


def test_distinct_stories_keep_distinct_external_delivery_identity() -> None:
    first = _news_candidate()
    second = replace(
        first,
        row_id="news-page-row:news-2",
        news_item_id="news-2",
        representative_news_item_id="news-2",
        story_key="news-story:unit:two",
    )

    candidates = _news_candidates(_engine(news=FakeNews([first, second])))

    assert len(candidates) == 2
    assert candidates[0].payload["external_push_signature"] != candidates[1].payload["external_push_signature"]


def test_market_wide_news_has_no_fabricated_asset_identity() -> None:
    candidate = _news_candidates(_engine(news=FakeNews([_news_candidate(affected_symbols=(), token_symbols=())])))[0]

    assert candidate.symbol is None
    assert candidate.payload["symbols"] == []
    assert candidate.payload["external_push_eligible"] is True
