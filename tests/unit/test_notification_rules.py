import pytest

from parallax.domains.notifications.services.notification_rules import (
    NotificationRuleEngine,
    _news_display_title,
    _news_external_push_signature,
)
from parallax.platform.config.settings import NotificationRuleConfig, NotificationsConfig, Settings

NOW_MS = 1_700_000_300_000


class FakeEvidence:
    def __init__(self, events):
        self.events = events

    def recent_events(self, **kwargs):
        self.kwargs = kwargs
        return self.events


class FakeAccountAlerts:
    def __init__(self, alerts):
        self.alerts = alerts

    def account_alerts(self, **kwargs):
        self.kwargs = kwargs
        return self.alerts


class FakePulse:
    def __init__(self, items, *, page_size: int | None = None):
        self.items = items
        self.page_size = page_size
        self.calls = []

    def list_signal_pulse_notification_candidates(self, **kwargs):
        self.calls.append(kwargs)
        rows: list[dict] = []
        scopes = tuple(kwargs.get("scopes") or ())
        statuses = tuple(kwargs.get("statuses") or ())
        per_scope_status_limit = int(kwargs.get("per_scope_status_limit") or 0)
        for scope in scopes:
            for status in statuses:
                bucket = [
                    item
                    for item in self.items
                    if item.get("window") == kwargs.get("window")
                    and item.get("scope") == scope
                    and item.get("pulse_status") == status
                    and item.get("pulse_status") in {"trade_candidate", "token_watch", "risk_rejected_high_info"}
                    and item.get("verdict") != "blocked_low_information"
                ]
                rows.extend(bucket[:per_scope_status_limit])
        return rows

    def list_candidates(self, **kwargs):
        self.calls.append(kwargs)
        rows = [
            item
            for item in self.items
            if item.get("window") == kwargs.get("window") and item.get("scope") == kwargs.get("scope")
        ]
        if kwargs.get("status") is not None:
            rows = [item for item in rows if item.get("pulse_status") == kwargs.get("status")]
        if kwargs.get("displayable_only"):
            rows = [
                item
                for item in rows
                if item.get("pulse_status") in {"trade_candidate", "token_watch", "risk_rejected_high_info"}
                and item.get("verdict") != "blocked_low_information"
            ]
        limit = int(kwargs.get("limit") or len(rows))
        page_size = min(limit, self.page_size) if self.page_size else limit
        cursor = int(kwargs.get("cursor") or 0)
        page_rows = rows[cursor : cursor + page_size]
        next_cursor = str(cursor + page_size) if cursor + page_size < len(rows) else None
        return {"items": page_rows, "next_cursor": next_cursor}


class FakeNews:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def list_news_high_signal_notification_candidates(self, **kwargs):
        self.calls.append(kwargs)
        return self.rows


def _market_scoped_news_row(row: dict) -> dict:
    representative_news_item_id = row.get("representative_news_item_id") or row.get("news_item_id") or ""
    news_item_id = str(row.get("news_item_id") or "")
    story_key = str(row.get("story_key") or f"news-story:unit:{news_item_id}")
    return {
        "row_id": f"news-page-row:{news_item_id}",
        "representative_news_item_id": representative_news_item_id,
        "story_key": story_key,
        "story": {"story_key": story_key, "member_count": 1},
        "duplicate_count": 1,
        "market_scope": {
            "scope": ["crypto"],
            "primary": "crypto",
            "status": "classified",
            "reason": "test_crypto_subject",
            "basis": {"test": True},
            "version": "test_news_market_scope_v1",
        },
        "agent_admission_status": "eligible",
        "agent_admission_reason": "test_agent_ready",
        "agent_admission": {
            "status": "eligible",
            "reason": "test_agent_ready",
            "representative_news_item_id": representative_news_item_id,
        },
        **row,
    }


def engine(*, events=None, alerts=None, pulse=None, news=None, notifications=None):
    return NotificationRuleEngine(
        settings=Settings(
            ws_token="secret",
            handles=("toly",),
            notifications=notifications or NotificationsConfig(),
        ),
        evidence=FakeEvidence(events or []),
        account_alerts=FakeAccountAlerts(alerts or []),
        pulse=pulse or FakePulse([]),
        news=news,
    )


def test_watched_account_activity_candidate_uses_committed_event_identity():
    candidates = engine(
        events=[
            {
                "event_id": "event-1",
                "author_handle": "toly",
                "action": "tweet",
                "received_at_ms": NOW_MS - 10_000,
                "text_clean": "building on base",
            }
        ]
    ).evaluate(now_ms=NOW_MS)

    candidate = next(item for item in candidates if item.rule_id == "watched_account_activity")
    bucket = (NOW_MS - 10_000) // 300_000
    assert candidate.dedup_key == f"watched_account_activity:account:toly:tweet:{bucket}"
    assert candidate.severity == "info"
    assert candidate.entity_type == "account"
    assert candidate.entity_key == "account:toly"
    assert candidate.author_handle == "toly"
    assert candidate.source_table == "events"
    assert candidate.source_id == "event-1"
    assert candidate.payload["event_id"] == "event-1"


def test_watched_account_activity_uses_account_action_bucket_when_cooldown_configured():
    notifications = NotificationsConfig(
        rules={"watched_account_activity": {"enabled": True, "channels": ["in_app"], "cooldown_seconds": 300}}
    )
    events = [
        {"event_id": "event-1", "author_handle": "toly", "action": "post", "received_at_ms": NOW_MS, "text": "one"},
        {
            "event_id": "event-2",
            "author_handle": "toly",
            "action": "post",
            "received_at_ms": NOW_MS + 60_000,
            "text": "two",
        },
    ]

    candidates = [
        item
        for item in engine(events=events, notifications=notifications).evaluate(now_ms=NOW_MS)
        if item.rule_id == "watched_account_activity"
    ]

    assert len(candidates) == 2
    assert candidates[0].dedup_key == candidates[1].dedup_key
    assert candidates[0].dedup_key == f"watched_account_activity:account:toly:post:{NOW_MS // 300_000}"


def test_watched_account_activity_does_not_fall_back_to_event_key_when_cooldown_zero():
    notifications = NotificationsConfig(
        rules={"watched_account_activity": {"enabled": True, "channels": ["in_app"], "cooldown_seconds": 0}}
    )

    candidate = next(
        item
        for item in engine(
            events=[
                {
                    "event_id": "event-1",
                    "author_handle": "toly",
                    "action": "post",
                    "received_at_ms": NOW_MS,
                    "text": "one",
                }
            ],
            notifications=notifications,
        ).evaluate(now_ms=NOW_MS)
        if item.rule_id == "watched_account_activity"
    )

    assert candidate.dedup_key == f"watched_account_activity:account:toly:post:{NOW_MS // 1000}"


def test_notification_rule_query_windows_and_news_overscan_use_formal_config():
    notifications = NotificationsConfig(
        candidate_limit=4,
        watched_activity_window_ms=2 * 60 * 60_000,
        news_high_signal_recency_window_ms=10_000,
        news_high_signal_query_min_limit=7,
        news_high_signal_query_multiplier=3,
    )
    news = FakeNews(
        [
            _market_scoped_news_row(
                {
                    "news_item_id": "news-stale-by-config",
                    "latest_at_ms": NOW_MS - 15_000,
                    "headline": "Stale by configured notification recency",
                    "source_domain": "example.test",
                    "canonical_url": "https://example.test/stale",
                    "signal": {
                        "direction": "bullish",
                        "alert_eligibility": {
                            "in_app_eligible": True,
                            "external_push_ready": True,
                            "external_push_basis": "agent_brief",
                            "decision_class": "driver",
                        },
                    },
                    "token_impacts": [{"symbol": "OLD"}],
                    "agent_brief": {
                        "status": "ready",
                        "direction": "bullish",
                        "decision_class": "driver",
                        "title_zh": "旧新闻",
                        "summary_zh": "超过配置窗口。",
                    },
                }
            )
        ]
    )

    rule_engine = engine(
        events=[
            {
                "event_id": "event-old-but-configured",
                "author_handle": "toly",
                "action": "post",
                "received_at_ms": NOW_MS - 90 * 60_000,
                "text": "inside configured activity window",
            }
        ],
        news=news,
        notifications=notifications,
    )
    candidates = rule_engine.evaluate(now_ms=NOW_MS)

    assert news.calls == [{"limit": 12}]
    assert rule_engine.evidence.kwargs["since_ms"] == NOW_MS - 2 * 60 * 60_000
    assert [item.source_id for item in candidates if item.rule_id == "watched_account_activity"] == [
        "event-old-but-configured"
    ]
    assert [item for item in candidates if item.rule_id == "news_high_signal"] == []


def test_account_token_alert_candidate_preserves_first_seen_flags():
    rule_engine = engine(
        alerts=[
            {
                "alert_id": "alert-1",
                "event_id": "event-1",
                "author_handle": "toly",
                "normalized_value": "PEPE",
                "entity_key": "symbol:PEPE",
                "chain": None,
                "received_at_ms": NOW_MS - 10_000,
                "is_first_seen_global": 1,
                "is_first_seen_by_author": 1,
            }
        ]
    )
    candidates = rule_engine.evaluate(now_ms=NOW_MS)

    candidate = next(item for item in candidates if item.rule_id == "watched_account_token_alert")
    bucket = (NOW_MS - 10_000) // 900_000
    assert rule_engine.account_alerts.kwargs["now_ms"] == NOW_MS
    assert candidate.dedup_key == f"watched_account_token_alert:symbol:PEPE:author:toly:{bucket}"
    assert candidate.severity == "warning"
    assert candidate.entity_type == "token"
    assert candidate.symbol == "PEPE"
    assert candidate.payload["is_first_seen_global"] is True


def test_watched_account_token_alert_uses_asset_author_bucket_when_cooldown_configured():
    notifications = NotificationsConfig(
        rules={
            "watched_account_token_alert": {
                "enabled": True,
                "channels": ["in_app", "pushdeer"],
                "cooldown_seconds": 900,
            }
        }
    )
    alerts = [
        {
            "alert_id": "alert-1",
            "received_at_ms": NOW_MS,
            "author_handle": "toly",
            "normalized_value": "TROLL",
            "entity_key": "asset:solana:token:troll",
            "is_first_seen_global": True,
            "is_first_seen_by_author": True,
        },
        {
            "alert_id": "alert-2",
            "received_at_ms": NOW_MS + 120_000,
            "author_handle": "toly",
            "normalized_value": "TROLL",
            "entity_key": "asset:solana:token:troll",
            "is_first_seen_global": False,
            "is_first_seen_by_author": False,
        },
    ]

    candidates = [
        item
        for item in engine(alerts=alerts, notifications=notifications).evaluate(now_ms=NOW_MS)
        if item.rule_id == "watched_account_token_alert"
    ]

    assert len(candidates) == 2
    assert candidates[0].dedup_key == candidates[1].dedup_key
    assert (
        candidates[0].dedup_key
        == f"watched_account_token_alert:asset:solana:token:troll:author:toly:{NOW_MS // 900_000}"
    )


def test_watched_account_token_alert_does_not_fall_back_to_alert_key_when_cooldown_zero():
    notifications = NotificationsConfig(
        rules={"watched_account_token_alert": {"enabled": True, "channels": ["in_app"], "cooldown_seconds": 0}}
    )

    candidate = next(
        item
        for item in engine(
            alerts=[
                {
                    "alert_id": "alert-1",
                    "received_at_ms": NOW_MS,
                    "author_handle": "toly",
                    "normalized_value": "TROLL",
                    "entity_key": "asset:solana:token:troll",
                    "is_first_seen_global": True,
                    "is_first_seen_by_author": True,
                }
            ],
            notifications=notifications,
        ).evaluate(now_ms=NOW_MS)
        if item.rule_id == "watched_account_token_alert"
    )

    assert candidate.dedup_key == f"watched_account_token_alert:asset:solana:token:troll:author:toly:{NOW_MS // 1000}"


def test_signal_pulse_rule_is_enabled_by_default():
    rules = NotificationsConfig().rules

    assert "signal_pulse_candidate" in rules
    assert rules["signal_pulse_candidate"].enabled is True
    assert rules["signal_pulse_candidate"].channels == ("in_app",)


def test_signal_pulse_notifications_use_materialized_candidates_and_severity_mapping():
    pulse = FakePulse(
        [
            pulse_candidate("trade", status="trade_candidate", score_band="high_conviction", symbol="PEPE"),
            pulse_candidate("watch", status="token_watch", score_band="watch", symbol="BONK"),
            pulse_candidate("risk", status="risk_rejected_high_info", score_band="blocked", risks=["chase_risk"]),
            pulse_candidate("blocked", status="blocked_low_information", score_band="blocked"),
        ]
    )

    candidates = [
        item for item in engine(pulse=pulse).evaluate(now_ms=NOW_MS) if item.rule_id == "signal_pulse_candidate"
    ]

    assert {item.source_table for item in candidates} == {"pulse_candidates"}
    assert {item.source_id for item in candidates} == {"trade", "watch", "risk"}
    assert {item.source_id: item.severity for item in candidates} == {
        "trade": "critical",
        "watch": "high",
        "risk": "warning",
    }
    assert all(item.source_id != "blocked" for item in candidates)
    assert pulse.calls == [
        {
            "window": "1h",
            "scopes": ("all", "matched"),
            "statuses": ("risk_rejected_high_info", "token_watch", "trade_candidate"),
            "per_scope_status_limit": 250,
        }
    ]
    trade = next(item for item in candidates if item.source_id == "trade")
    assert trade.payload["candidate_id"] == "trade"
    assert "decision" in trade.payload
    assert "stage_count" not in trade.payload["decision"]
    assert "agent_recommendation" not in trade.payload
    assert "gate" in trade.payload
    assert "factor_snapshot" in trade.payload
    assert "top_risks" not in trade.payload
    assert "confirmation_triggers_zh" not in trade.payload
    assert "kind" not in trade.payload


def test_signal_pulse_notification_decision_uses_scalar_columns_not_json_fallback():
    row = pulse_candidate("watch", status="token_watch")
    row["decision_route"] = None
    row["decision_recommendation"] = None
    row["decision_abstain_reason"] = None
    row["decision_json"] = {
        **row["decision_json"],
        "route": "meme",
        "recommendation": "watchlist",
        "abstain_reason": "json_legacy_reason",
        "summary_zh": "通知富文本仍来自 decision_json。",
    }

    candidate = _only_pulse_notification(row)

    assert candidate.payload["decision"]["route"] is None
    assert candidate.payload["decision"]["recommendation"] is None
    assert candidate.payload["decision"]["abstain_reason"] is None
    assert candidate.payload["decision"]["summary_zh"] == "通知富文本仍来自 decision_json。"


def test_signal_pulse_dedup_key_uses_in_app_and_external_identity():
    in_app_only_row = pulse_candidate("watch", status="token_watch", edge_events=["score_band_crossed"])
    external_row = pulse_candidate("watch", status="token_watch", edge_events=["pulse_status_changed"])
    notifications = _signal_pulse_notifications(channels=["in_app", "pushdeer"], statuses=["token_watch"])

    in_app_only = _only_pulse_notification(in_app_only_row, notifications=notifications)
    external = _only_pulse_notification(external_row, notifications=notifications)

    assert in_app_only.payload["semantic_signature"] == external.payload["semantic_signature"]
    assert in_app_only.payload["external_push_signature"] is None
    assert external.payload["external_push_signature"]
    assert in_app_only.dedup_key == f"signal_pulse_candidate:{in_app_only.payload['semantic_signature']}:in_app"
    external_identity = external.payload["external_push_signature"]
    assert external.dedup_key == f"signal_pulse_candidate:{external.payload['semantic_signature']}:{external_identity}"


def test_signal_pulse_signature_changes_on_stable_dimension_shifts():
    """v2 signature must change when any stable decision dimension shifts."""
    base = pulse_candidate("watch", status="token_watch", score_band="watch", risks=["public_stream_coverage"])
    gate_changed = pulse_candidate("watch")
    gate_changed["factor_snapshot_json"] = {
        **gate_changed["factor_snapshot_json"],
        "gates": {**gate_changed["factor_snapshot_json"]["gates"], "max_decision": "watch"},
    }
    # decision-route shift
    route_changed = pulse_candidate("watch")
    route_changed["decision_route"] = "cex"
    # narrative_archetype shift (in decision_json)
    archetype_changed = pulse_candidate("watch")
    archetype_changed["decision_json"] = {
        **archetype_changed["decision_json"],
        "narrative_archetype": "vc_endorsed_launch",
    }
    # bull_view.strength absent → strong
    bull_changed = pulse_candidate("watch")
    bull_changed["decision_json"] = {
        **bull_changed["decision_json"],
        "bull_view": {"strength": "strong", "thesis_zh": "x", "supporting_event_ids": []},
    }
    # has_playbook flip
    playbook_added = pulse_candidate("watch")
    playbook_added["decision_json"] = {
        **playbook_added["decision_json"],
        "playbook": {
            "has_playbook": True,
            "monitoring_horizon": "4h",
            "watch_signals": ["a"],
            "exit_triggers": ["b"],
        },
    }

    signatures = {
        "base": _only_pulse_notification(base).payload["semantic_signature"],
        "score_band": _only_pulse_notification({**base, "score_band": "high_conviction"}).payload["semantic_signature"],
        "gate": _only_pulse_notification(gate_changed).payload["semantic_signature"],
        "route": _only_pulse_notification(route_changed).payload["semantic_signature"],
        "narrative_archetype": _only_pulse_notification(archetype_changed).payload["semantic_signature"],
        "bull_strength": _only_pulse_notification(bull_changed).payload["semantic_signature"],
        "has_playbook": _only_pulse_notification(playbook_added).payload["semantic_signature"],
    }

    assert len(set(signatures.values())) == len(signatures)


def test_signal_pulse_signature_does_not_change_for_free_text_only_change():
    """Free-text changes (thesis_zh / narrative_thesis_zh / summary_zh) MUST NOT
    bump the signature — otherwise minor agent paraphrasing would re-page users.
    """
    base = pulse_candidate("watch", status="token_watch")
    base_sig = _only_pulse_notification(base).payload["semantic_signature"]

    # Only summary_zh / narrative_thesis_zh / bull_view.thesis_zh differ
    paraphrased = pulse_candidate("watch", status="token_watch", recommendation_summary="完全不同的文字描述")
    paraphrased["decision_json"] = {
        **paraphrased["decision_json"],
        "narrative_thesis_zh": "另一段完全不同的叙事文字。",
        "bull_view": {
            "strength": "moderate",
            "thesis_zh": "原始 thesis 改成了完全不同的文字",
            "supporting_event_ids": ["event-1"],
        },
    }
    # Add same bull_view to base so structure matches, only thesis_zh differs
    base["decision_json"] = {
        **base["decision_json"],
        "bull_view": {
            "strength": "moderate",
            "thesis_zh": "原始 thesis",
            "supporting_event_ids": ["event-1"],
        },
    }
    base_sig_with_bull = _only_pulse_notification(base).payload["semantic_signature"]
    paraphrased_sig = _only_pulse_notification(paraphrased).payload["semantic_signature"]

    assert paraphrased_sig == base_sig_with_bull
    # And neither matches the pre-bull base (because adding bull strength is a stable shift)
    assert paraphrased_sig != base_sig


def test_signal_pulse_signature_does_not_change_for_evidence_or_edge_event_churn():
    """Adding new evidence ids / edge events MUST NOT bump signature when stable
    decision dimensions are unchanged. These are noisy churn fields.
    """
    base = pulse_candidate("watch", status="token_watch", evidence_ids=["event-1"], source_ids=["event-1"])
    churned = pulse_candidate(
        "watch",
        status="token_watch",
        evidence_ids=["event-1", "event-9", "event-10"],
        source_ids=["event-1", "event-9"],
        edge_events=["hard_risk_added", "score_band_crossed"],
        updated_at_ms=NOW_MS + 600_000,
    )

    assert (
        _only_pulse_notification(base).payload["semantic_signature"]
        == _only_pulse_notification(churned).payload["semantic_signature"]
    )


def test_signal_pulse_signature_changes_when_bull_strength_changes():
    base = pulse_candidate("watch", status="token_watch")
    base["decision_json"] = {
        **base["decision_json"],
        "bull_view": {"strength": "absent", "thesis_zh": "", "supporting_event_ids": []},
    }
    bumped = pulse_candidate("watch", status="token_watch")
    bumped["decision_json"] = {
        **bumped["decision_json"],
        "bull_view": {"strength": "strong", "thesis_zh": "升级", "supporting_event_ids": []},
    }

    assert (
        _only_pulse_notification(base).payload["semantic_signature"]
        != _only_pulse_notification(bumped).payload["semantic_signature"]
    )


def test_signal_pulse_signature_changes_on_playbook_structure_not_raw_text():
    base = pulse_candidate("watch", status="token_watch")
    base["decision_json"] = {
        **base["decision_json"],
        "playbook": {
            "has_playbook": True,
            "monitoring_horizon": "4h",
            "watch_signals": ["新增独立作者"],
            "exit_triggers": ["讨论降温"],
        },
    }
    raw_text_changed = pulse_candidate("watch", status="token_watch")
    raw_text_changed["decision_json"] = {
        **raw_text_changed["decision_json"],
        "playbook": {
            "has_playbook": True,
            "monitoring_horizon": "4h",
            "watch_signals": ["另一种安全说法"],
            "exit_triggers": ["另一个安全触发"],
        },
    }
    horizon_changed = pulse_candidate("watch", status="token_watch")
    horizon_changed["decision_json"] = {
        **horizon_changed["decision_json"],
        "playbook": {
            "has_playbook": True,
            "monitoring_horizon": "24h",
            "watch_signals": ["新增独立作者"],
            "exit_triggers": ["讨论降温"],
        },
    }
    count_changed = pulse_candidate("watch", status="token_watch")
    count_changed["decision_json"] = {
        **count_changed["decision_json"],
        "playbook": {
            "has_playbook": True,
            "monitoring_horizon": "4h",
            "watch_signals": ["新增独立作者", "watched_mentions 增长"],
            "exit_triggers": ["讨论降温"],
        },
    }

    base_sig = _only_pulse_notification(base).payload["semantic_signature"]

    assert _only_pulse_notification(raw_text_changed).payload["semantic_signature"] == base_sig
    assert _only_pulse_notification(horizon_changed).payload["semantic_signature"] != base_sig
    assert _only_pulse_notification(count_changed).payload["semantic_signature"] != base_sig


def test_signal_pulse_signature_counts_only_safe_playbook_entries():
    base = pulse_candidate("watch", status="token_watch")
    base["decision_json"] = {
        **base["decision_json"],
        "playbook": {
            "has_playbook": True,
            "monitoring_horizon": "4h",
            "watch_signals": ["新增独立作者"],
            "exit_triggers": ["讨论降温"],
        },
    }
    unsafe_extra = pulse_candidate("watch", status="token_watch")
    unsafe_extra["decision_json"] = {
        **unsafe_extra["decision_json"],
        "playbook": {
            "has_playbook": True,
            "monitoring_horizon": "4h",
            "watch_signals": ["新增独立作者", "建议买入"],
            "exit_triggers": ["讨论降温", "设置止损"],
        },
    }

    assert (
        _only_pulse_notification(base).payload["semantic_signature"]
        == _only_pulse_notification(unsafe_extra).payload["semantic_signature"]
    )


def test_signal_pulse_pushdeer_uses_target_cooldown_signature_once_across_scopes() -> None:
    row = pulse_candidate(
        "pulse-all",
        status="trade_candidate",
        symbol="PEPE",
        eligible_for_high_alert=True,
    )
    matched = dict(row)
    matched["candidate_id"] = "pulse-matched"
    matched["scope"] = "matched"
    notifications = _signal_pulse_notifications(
        channels=["in_app", "pushdeer"],
        scopes=["all", "matched"],
        statuses=["trade_candidate"],
        cooldown_seconds=900,
    )

    candidates = [
        item
        for item in engine(pulse=FakePulse([row, matched]), notifications=notifications).evaluate(now_ms=NOW_MS)
        if item.rule_id == "signal_pulse_candidate"
    ]

    assert {item.source_id for item in candidates} == {"pulse-all", "pulse-matched"}
    pushed = [item for item in candidates if "pushdeer" in item.channels]
    assert len(pushed) == 1
    assert pushed[0].channels == ("in_app", "pushdeer")
    assert pushed[0].payload["external_push_eligible"] is True
    external_signature = pushed[0].payload["external_push_signature"]
    assert external_signature
    assert pushed[0].payload["external_push_suppression_reason"] is None
    assert pushed[0].payload["semantic_signature"]

    in_app_only = [item for item in candidates if item not in pushed]
    assert len(in_app_only) == 1
    assert in_app_only[0].channels == ("in_app",)
    assert in_app_only[0].payload["external_push_eligible"] is False
    assert in_app_only[0].payload["external_push_signature"] == external_signature
    assert in_app_only[0].payload["external_push_suppression_reason"] == "external_signature_duplicate"
    assert in_app_only[0].payload["semantic_signature"]


def test_signal_pulse_score_band_only_change_is_in_app_only() -> None:
    row = pulse_candidate("pulse-score-band", status="token_watch", eligible_for_high_alert=True)
    row["last_edge_events_json"] = ["score_band_crossed"]

    candidate = _only_pulse_notification(
        row,
        notifications=_signal_pulse_notifications(channels=["in_app", "pushdeer"], statuses=["token_watch"]),
    )

    assert candidate.channels == ("in_app",)
    assert candidate.payload["external_push_eligible"] is False
    assert candidate.payload["external_push_suppression_reason"] == "not_escalation"


def test_signal_pulse_risk_rejected_high_info_is_in_app_only() -> None:
    row = pulse_candidate("pulse-risk", status="risk_rejected_high_info", risks=["chase_risk"])

    candidate = _only_pulse_notification(
        row,
        notifications=_signal_pulse_notifications(
            channels=["in_app", "pushdeer"],
            statuses=["risk_rejected_high_info"],
        ),
    )

    assert candidate.severity == "warning"
    assert candidate.channels == ("in_app",)
    assert candidate.payload["external_push_eligible"] is False
    assert candidate.payload["external_push_suppression_reason"] == "risk_rejected_in_app_only"


def test_signal_pulse_external_signature_ignores_in_app_decision_detail_churn() -> None:
    base = pulse_candidate("pulse-watch", status="token_watch")
    playbook_changed = pulse_candidate("pulse-watch", status="token_watch")
    playbook_changed["decision_json"] = {
        **playbook_changed["decision_json"],
        "playbook": {
            "has_playbook": True,
            "monitoring_horizon": "24h",
            "watch_signals": ["新增独立作者"],
            "exit_triggers": ["讨论降温"],
        },
        "bull_view": {"strength": "strong", "thesis_zh": "文本变化", "supporting_event_ids": ["event-1"]},
    }

    notifications = _signal_pulse_notifications(channels=["in_app", "pushdeer"], statuses=["token_watch"])
    base_candidate = _only_pulse_notification(base, notifications=notifications)
    changed_candidate = _only_pulse_notification(playbook_changed, notifications=notifications)

    assert base_candidate.payload["semantic_signature"] != changed_candidate.payload["semantic_signature"]
    assert base_candidate.payload["external_push_signature"] == changed_candidate.payload["external_push_signature"]


def test_signal_pulse_external_signature_uses_snapshot_target_when_row_target_is_absent() -> None:
    first = pulse_candidate("pulse-first", status="trade_candidate")
    second = pulse_candidate("pulse-second", status="trade_candidate")
    for row in (first, second):
        row["target_type"] = None
        row["target_id"] = None
    notifications = _signal_pulse_notifications(channels=["in_app", "pushdeer"], statuses=["trade_candidate"])

    candidates = [
        item
        for item in engine(pulse=FakePulse([first, second]), notifications=notifications).evaluate(now_ms=NOW_MS)
        if item.rule_id == "signal_pulse_candidate"
    ]

    assert {item.source_id for item in candidates} == {"pulse-first", "pulse-second"}
    assert all(item.channels == ("in_app", "pushdeer") for item in candidates)
    assert len({item.payload["external_push_signature"] for item in candidates}) == 2


def test_signal_pulse_rule_can_be_disabled():
    notifications = NotificationsConfig(rules={"signal_pulse_candidate": NotificationRuleConfig(enabled=False)})

    candidates = engine(
        pulse=FakePulse([pulse_candidate("watch", status="token_watch")]),
        notifications=notifications,
    ).evaluate(now_ms=NOW_MS)

    assert [item for item in candidates if item.rule_id == "signal_pulse_candidate"] == []


def test_signal_pulse_candidate_rule_uses_window_scope_status_without_downstream_score_gates():
    hot_row = pulse_candidate(
        "pulse-hot",
        window="1h",
        scope="all",
        candidate_score=74,
        radar_score={"heat": {"score": 72}},
    )
    cold_row = pulse_candidate(
        "pulse-cold",
        window="1h",
        scope="all",
        candidate_score=74,
        radar_score={"heat": {"score": 12}},
    )
    low_score_row = pulse_candidate(
        "pulse-low-score",
        window="1h",
        scope="all",
        candidate_score=9,
        radar_score={"heat": {"score": 75}},
    )
    ignored_scope_row = pulse_candidate(
        "pulse-ignored-scope",
        window="1h",
        scope="matched",
        candidate_score=90,
        radar_score={"heat": {"score": 90}},
    )
    pulse = FakePulse([hot_row, cold_row, low_score_row, ignored_scope_row])
    notifications = NotificationsConfig(
        rules={
            "signal_pulse_candidate": {
                "enabled": True,
                "channels": ["in_app", "pushdeer"],
                "window": "1h",
                "scopes": ["all"],
                "statuses": ["token_watch"],
                "cooldown_seconds": 120,
            }
        }
    )

    candidates = engine(pulse=pulse, notifications=notifications).evaluate(now_ms=NOW_MS)
    pulse_candidates = [item for item in candidates if item.rule_id == "signal_pulse_candidate"]

    assert [item.source_id for item in pulse_candidates] == [
        "pulse-hot",
        "pulse-cold",
        "pulse-low-score",
    ]
    assert pulse_candidates[0].channels == ("in_app", "pushdeer")
    assert pulse_candidates[0].dedup_key == (
        "signal_pulse_candidate:"
        f"{pulse_candidates[0].payload['semantic_signature']}:"
        f"{pulse_candidates[0].payload['external_push_signature']}"
    )
    assert pulse.calls == [
        {
            "window": "1h",
            "scopes": ("all",),
            "statuses": ("token_watch",),
            "per_scope_status_limit": 250,
        }
    ]


def test_signal_pulse_candidate_limit_uses_configured_notification_limit_without_service_floor():
    row = pulse_candidate("pulse-config-limit", window="1h", scope="all", status="token_watch")
    pulse = FakePulse([row])
    notifications = NotificationsConfig(
        candidate_limit=12,
        rules={
            "signal_pulse_candidate": {
                "enabled": True,
                "channels": ["in_app"],
                "window": "1h",
                "scopes": ["all"],
                "statuses": ["token_watch"],
            }
        },
    )

    candidates = [
        item
        for item in engine(pulse=pulse, notifications=notifications).evaluate(now_ms=NOW_MS)
        if item.rule_id == "signal_pulse_candidate"
    ]

    assert [item.source_id for item in candidates] == ["pulse-config-limit"]
    assert pulse.calls == [
        {
            "window": "1h",
            "scopes": ("all",),
            "statuses": ("token_watch",),
            "per_scope_status_limit": 60,
        }
    ]


def test_signal_pulse_candidate_rule_paginates_with_status_filter_at_source():
    class StatusAwarePulse:
        def __init__(self):
            self.calls = []

        def list_signal_pulse_notification_candidates(self, **kwargs):
            self.calls.append(kwargs)
            if tuple(kwargs.get("statuses") or ()) == ("trade_candidate",):
                return [pulse_candidate("trade-only", status="trade_candidate", symbol="TRADE")]
            return [pulse_candidate(f"watch-{idx}", status="token_watch") for idx in range(100)]

    notifications = NotificationsConfig(
        rules={
            "signal_pulse_candidate": {
                "enabled": True,
                "channels": ["in_app"],
                "window": "1h",
                "scopes": ["all"],
                "statuses": ["trade_candidate"],
            }
        }
    )
    pulse = StatusAwarePulse()

    candidates = [
        item
        for item in engine(pulse=pulse, notifications=notifications).evaluate(now_ms=NOW_MS)
        if item.rule_id == "signal_pulse_candidate"
    ]

    assert [tuple(call["statuses"]) for call in pulse.calls] == [("trade_candidate",)]
    assert [item.source_id for item in candidates] == ["trade-only"]


def test_signal_pulse_low_liquidity_factor_snapshot_cannot_emit_high_notification():
    row = pulse_candidate(
        "pulse-low-liq",
        status="token_watch",
        symbol="BOV",
        eligible_for_high_alert=False,
        blocked_reasons=["liquidity_below_high_alert_floor"],
        market_facts={"liquidity_usd": 6553, "holders": 46, "market_cap_usd": 12087, "market_status": "fresh"},
        social_facts={"mentions_1h": 3, "unique_authors": 2, "watched_mentions": 0},
    )

    candidates = [
        item
        for item in engine(pulse=FakePulse([row])).evaluate(now_ms=NOW_MS)
        if item.rule_id == "signal_pulse_candidate"
    ]

    assert candidates == []


def test_signal_pulse_eligible_token_watch_can_emit_high_notification():
    row = pulse_candidate(
        "pulse-watch",
        status="token_watch",
        symbol="BOV",
        eligible_for_high_alert=True,
        market_facts={"liquidity_usd": 55_000, "holders": 600, "market_cap_usd": 250_000, "market_status": "fresh"},
        social_facts={"mentions_1h": 6, "unique_authors": 4, "watched_mentions": 1},
        recommendation_summary="链上质量达标，可以高优先级观察。",
    )

    candidate = _only_pulse_notification(row)

    assert candidate.severity == "high"
    assert candidate.symbol == "BOV"
    # New SurfaceCard body: header always present, links always present
    assert "## $BOV" in candidate.body
    assert "Signal Pulse" in candidate.body
    assert "### 🔗 链接" in candidate.body
    assert "[X 搜索]" in candidate.body
    assert "Pulse: `pulse-watch`" in candidate.body


def test_signal_pulse_notification_requires_non_empty_factor_snapshot():
    row = pulse_candidate("pulse-legacy", status="token_watch")
    row["factor_snapshot_json"] = {}
    row["thesis_json"] = {
        "summary_zh": "旧 thesis 不应触发通知",
        "confirmation_triggers_zh": ["旧确认"],
        "top_risks": ["旧风险"],
    }

    candidates = [
        item
        for item in engine(pulse=FakePulse([row])).evaluate(now_ms=NOW_MS)
        if item.rule_id == "signal_pulse_candidate"
    ]

    assert candidates == []


def test_signal_pulse_notification_rejects_malformed_factor_snapshot_contract():
    row = pulse_candidate(
        "pulse-malformed",
        status="token_watch",
        eligible_for_high_alert=True,
        gate={"eligible_for_high_alert": True, "max_recommendation": "watch", "blocked_reasons": []},
    )
    row["factor_snapshot_json"] = {
        "schema_version": "token_factor_snapshot_legacy",
        "subject": {"target_type": "Asset", "target_id": "asset:malformed", "symbol": "BAD"},
        "hard_gates": {"eligible_for_high_alert": True, "blocked_reasons": []},
        "composite": {"rank_score": 82},
    }

    candidates = [
        item
        for item in engine(pulse=FakePulse([row])).evaluate(now_ms=NOW_MS)
        if item.rule_id == "signal_pulse_candidate"
    ]

    assert candidates == []


@pytest.mark.parametrize(
    "mutate",
    [
        lambda snapshot: snapshot["families"].__setitem__("market_quality", {"facts": {}}),
        lambda snapshot: snapshot.pop("normalization"),
        lambda snapshot: snapshot.pop("provenance"),
        lambda snapshot: snapshot.__setitem__("legacy_score", {"score": 100}),
    ],
)
def test_signal_pulse_notification_rejects_malformed_v3_snapshot_shape(mutate):
    row = pulse_candidate("pulse-malformed-v2", status="token_watch", eligible_for_high_alert=True)
    mutate(row["factor_snapshot_json"])

    candidates = [
        item
        for item in engine(pulse=FakePulse([row])).evaluate(now_ms=NOW_MS)
        if item.rule_id == "signal_pulse_candidate"
    ]

    assert candidates == []


def test_signal_pulse_notifications_read_dedicated_candidate_keyset_once():
    pulse = FakePulse(
        [
            pulse_candidate("page-1", status="token_watch"),
            pulse_candidate("page-2", status="token_watch"),
            pulse_candidate("page-3", status="token_watch"),
        ],
        page_size=1,
    )

    candidates = [
        item for item in engine(pulse=pulse).evaluate(now_ms=NOW_MS) if item.rule_id == "signal_pulse_candidate"
    ]

    assert [item.source_id for item in candidates] == ["page-1", "page-2", "page-3"]
    assert pulse.calls == [
        {
            "window": "1h",
            "scopes": ("all", "matched"),
            "statuses": ("risk_rejected_high_info", "token_watch", "trade_candidate"),
            "per_scope_status_limit": 250,
        }
    ]


def test_signal_pulse_notification_page_budget_uses_formal_config():
    pulse = FakePulse(
        [
            pulse_candidate("page-budget-1", status="token_watch"),
            pulse_candidate("page-budget-2", status="token_watch"),
            pulse_candidate("page-budget-3", status="token_watch"),
        ],
        page_size=1,
    )
    notifications = NotificationsConfig(
        candidate_limit=1,
        signal_pulse_max_pages=2,
        rules={
            "signal_pulse_candidate": {
                "enabled": True,
                "channels": ["in_app"],
                "window": "1h",
                "scopes": ["all"],
                "statuses": ["token_watch"],
            }
        },
    )

    candidates = [
        item
        for item in engine(pulse=pulse, notifications=notifications).evaluate(now_ms=NOW_MS)
        if item.rule_id == "signal_pulse_candidate"
    ]

    assert [item.source_id for item in candidates] == ["page-budget-1", "page-budget-2"]
    assert pulse.calls == [
        {
            "window": "1h",
            "scopes": ("all",),
            "statuses": ("token_watch",),
            "per_scope_status_limit": 2,
        }
    ]


def test_news_high_signal_uses_ready_agent_brief_for_display_and_builds_push_signatures():
    news = FakeNews(
        [
            _market_scoped_news_row(
                {
                    "news_item_id": "news-1",
                    "latest_at_ms": NOW_MS - 5_000,
                    "agent_brief_computed_at_ms": NOW_MS - 1_000,
                    "headline": "Major listing catalyst",
                    "source_domain": "example.test",
                    "canonical_url": "https://example.test/news-1",
                    "duplicate_count": 3,
                    "projection_version": "news-page-v1",
                    "signal": {
                        "direction": "bullish",
                        "alert_eligibility": {
                            "in_app_eligible": True,
                            "external_push_ready": True,
                            "external_push_basis": "agent_brief",
                            "decision_class": "driver",
                        },
                    },
                    "token_impacts": [{"symbol": "BOV"}],
                    "agent_brief": {
                        "status": "ready",
                        "direction": "bullish",
                        "decision_class": "driver",
                        "title_zh": "AI 标题：重大上所催化",
                        "summary_zh": "高分新闻已由 agent 归纳。",
                        "brief_json": {
                            "title_zh": "AI 标题：重大上所催化",
                            "summary_zh": "高分新闻已由 agent 归纳。",
                            "watch_triggers": ["成交量确认"],
                            "affected_entities": [{"symbol": "BOV"}],
                        },
                    },
                }
            )
        ]
    )
    notifications = NotificationsConfig(
        rules={
            "news_high_signal": {
                "enabled": True,
                "channels": ["in_app", "pushdeer"],
                "cooldown_seconds": 3600,
            }
        }
    )

    candidates = [
        item
        for item in engine(news=news, notifications=notifications).evaluate(now_ms=NOW_MS)
        if item.rule_id == "news_high_signal"
    ]

    assert news.calls == [{"limit": 1000}]
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.severity == "high"
    assert candidate.symbol == "BOV"
    assert candidate.channels == ("in_app", "pushdeer")
    assert candidate.payload["semantic_signature"].startswith("sha256:")
    assert candidate.payload["external_push_signature"].startswith("sha256:")
    assert candidate.payload["external_push_eligible"] is True
    assert candidate.payload["token_impacts"] == [{"symbol": "BOV"}]
    assert candidate.payload["agent_brief"]["summary_zh"] == "高分新闻已由 agent 归纳。"
    assert "brief_json" not in candidate.payload["agent_brief"]
    assert "provider_score" not in candidate.payload
    assert candidate.dedup_key == f"news_high_signal:{candidate.payload['semantic_signature']}"
    assert candidate.title == "AI 标题：重大上所催化"
    assert candidate.payload["display_title"] == "AI 标题：重大上所催化"
    assert "高分新闻已由 agent 归纳" in candidate.body
    assert "Score:" not in candidate.body
    assert candidate.occurrence_at_ms == NOW_MS - 5_000


def test_news_high_signal_requires_projected_representative_identity_without_item_fallback() -> None:
    row = _market_scoped_news_row(
        {
            "news_item_id": "news-missing-representative",
            "latest_at_ms": NOW_MS - 5_000,
            "headline": "Missing representative identity",
            "source_domain": "example.test",
            "canonical_url": "https://example.test/missing-representative",
            "signal": {
                "direction": "bullish",
                "alert_eligibility": {
                    "in_app_eligible": True,
                    "external_push_ready": True,
                    "external_push_basis": "agent_brief",
                    "decision_class": "driver",
                },
            },
            "token_impacts": [{"symbol": "BOV"}],
            "agent_brief": {
                "status": "ready",
                "direction": "bullish",
                "decision_class": "driver",
                "summary_zh": "Projected row is missing representative identity.",
            },
        }
    )
    row.pop("representative_news_item_id", None)

    with pytest.raises(ValueError, match="news_high_signal_representative_news_item_id_required"):
        engine(news=FakeNews([row])).evaluate(now_ms=NOW_MS)


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        ("signal_scalar", "news_high_signal_signal_required"),
        ("alert_eligibility_scalar", "news_high_signal_alert_eligibility_required"),
        ("in_app_eligible_missing", "news_high_signal_alert_eligibility_in_app_eligible_required"),
        ("in_app_eligible_false", "news_high_signal_alert_eligibility_in_app_eligible_required"),
        ("in_app_eligible_non_bool", "news_high_signal_alert_eligibility_in_app_eligible_required"),
        ("external_push_ready_non_bool", "news_high_signal_alert_eligibility_external_push_ready_required"),
        ("external_push_basis_missing", "news_high_signal_alert_eligibility_external_push_basis_required"),
        ("external_push_basis_blank", "news_high_signal_alert_eligibility_external_push_basis_required"),
        ("external_push_basis_non_string", "news_high_signal_alert_eligibility_external_push_basis_required"),
        ("external_push_basis_wrong", "news_high_signal_alert_eligibility_external_push_basis_required"),
        (
            "external_push_ready_block_reason_non_string",
            "news_high_signal_alert_eligibility_external_push_block_reason_required",
        ),
        ("external_push_block_reason_blank", "news_high_signal_alert_eligibility_external_push_block_reason_required"),
        (
            "external_push_block_reason_non_string",
            "news_high_signal_alert_eligibility_external_push_block_reason_required",
        ),
        ("agent_brief_scalar", "news_high_signal_agent_brief_required"),
        ("agent_brief_affected_entities_object", "news_high_signal_agent_brief_affected_entities_required"),
        ("agent_brief_affected_entities_member", "news_high_signal_agent_brief_affected_entities_required"),
        ("news_item_id_missing", "news_high_signal_news_item_id_required"),
        ("news_item_id_blank", "news_high_signal_news_item_id_required"),
        ("representative_news_item_id_missing", "news_high_signal_representative_news_item_id_required"),
        ("representative_news_item_id_blank", "news_high_signal_representative_news_item_id_required"),
        ("token_impacts_object", "news_high_signal_token_impacts_required"),
        ("token_impacts_member", "news_high_signal_token_impacts_required"),
        ("token_impacts_symbol_non_string", "news_high_signal_token_impacts_symbol_required"),
        ("token_impacts_market_type_non_string", "news_high_signal_token_impacts_market_type_required"),
        ("story_missing", "news_high_signal_story_required"),
        ("story_scalar", "news_high_signal_story_required"),
        ("story_story_key_non_string", "news_high_signal_story_story_key_required"),
        ("story_member_count_string", "news_high_signal_story_member_count_required"),
        ("story_member_count_bool", "news_high_signal_story_member_count_required"),
        ("story_member_count_negative", "news_high_signal_story_member_count_required"),
        ("story_source_domains_member_non_string", "news_high_signal_story_source_domains_required"),
        ("market_scope_scalar", "news_high_signal_market_scope_required"),
        ("market_scope_scope_non_list", "news_high_signal_market_scope_scope_required"),
        ("market_scope_scope_member_non_string", "news_high_signal_market_scope_scope_required"),
        ("market_scope_primary_non_string", "news_high_signal_market_scope_primary_required"),
        ("market_scope_status_non_string", "news_high_signal_market_scope_status_required"),
        ("market_scope_reason_non_string", "news_high_signal_market_scope_reason_required"),
        ("market_scope_basis_scalar", "news_high_signal_market_scope_basis_required"),
        ("market_scope_version_non_string", "news_high_signal_market_scope_version_required"),
        ("agent_admission_scalar", "news_high_signal_agent_admission_required"),
        ("agent_admission_payload_status_non_string", "news_high_signal_agent_admission_status_required"),
        ("agent_admission_payload_reason_non_string", "news_high_signal_agent_admission_reason_required"),
        (
            "agent_admission_payload_representative_non_string",
            "news_high_signal_agent_admission_representative_news_item_id_required",
        ),
        ("agent_admission_payload_basis_scalar", "news_high_signal_agent_admission_basis_required"),
        ("agent_admission_payload_version_non_string", "news_high_signal_agent_admission_version_required"),
        ("agent_admission_payload_eligible_non_bool", "news_high_signal_agent_admission_eligible_required"),
        ("latest_at_ms_missing", "news_high_signal_latest_at_ms_required"),
        ("latest_at_ms_string", "news_high_signal_latest_at_ms_required"),
        ("row_id_missing", "news_high_signal_row_id_required"),
        ("row_id_blank", "news_high_signal_row_id_required"),
        ("story_key_missing", "news_high_signal_story_key_required"),
        ("story_key_blank", "news_high_signal_story_key_required"),
        ("duplicate_count_missing", "news_high_signal_duplicate_count_required"),
        ("duplicate_count_string", "news_high_signal_duplicate_count_required"),
        ("duplicate_count_bool", "news_high_signal_duplicate_count_required"),
        ("duplicate_count_negative", "news_high_signal_duplicate_count_required"),
        ("source_domain_missing", "news_high_signal_source_domain_required"),
        ("source_domain_blank", "news_high_signal_source_domain_required"),
        ("source_domain_non_string", "news_high_signal_source_domain_required"),
        ("canonical_url_blank", "news_high_signal_canonical_url_required"),
        ("canonical_url_non_string", "news_high_signal_canonical_url_required"),
        ("agent_admission_status_missing", "news_high_signal_agent_admission_status_required"),
        ("agent_admission_status_blank", "news_high_signal_agent_admission_status_required"),
        ("agent_admission_status_non_string", "news_high_signal_agent_admission_status_required"),
        ("agent_admission_reason_missing", "news_high_signal_agent_admission_reason_required"),
        ("agent_admission_reason_blank", "news_high_signal_agent_admission_reason_required"),
        ("agent_admission_reason_non_string", "news_high_signal_agent_admission_reason_required"),
    ],
)
def test_news_high_signal_rejects_malformed_projected_payload_sections(
    mutation: str,
    error: str,
) -> None:
    row = _market_scoped_news_row(
        {
            "news_item_id": "news-malformed-projection",
            "representative_news_item_id": "news-malformed-projection",
            "story_key": "news-story:subject:malformed-projection:t412000",
            "latest_at_ms": NOW_MS - 5_000,
            "headline": "Malformed projected payload",
            "source_domain": "example.test",
            "canonical_url": "https://example.test/malformed-projection",
            "duplicate_count": 1,
            "signal": {
                "direction": "bullish",
                "alert_eligibility": {
                    "in_app_eligible": True,
                    "external_push_ready": True,
                    "external_push_basis": "agent_brief",
                    "decision_class": "driver",
                },
            },
            "token_impacts": [{"symbol": "BTC", "score": 90}],
            "agent_brief": {
                "status": "ready",
                "direction": "bullish",
                "decision_class": "driver",
                "summary_zh": "Malformed projected payload must fail visibly.",
                "affected_entities": [{"symbol": "BTC"}],
            },
        }
    )
    if mutation == "signal_scalar":
        row["signal"] = "bullish"
    elif mutation == "alert_eligibility_scalar":
        row["signal"]["alert_eligibility"] = "ready"
    elif mutation == "in_app_eligible_missing":
        row["signal"]["alert_eligibility"].pop("in_app_eligible")
    elif mutation == "in_app_eligible_false":
        row["signal"]["alert_eligibility"]["in_app_eligible"] = False
    elif mutation == "in_app_eligible_non_bool":
        row["signal"]["alert_eligibility"]["in_app_eligible"] = "true"
    elif mutation == "external_push_ready_non_bool":
        row["signal"]["alert_eligibility"]["external_push_ready"] = "yes"
    elif mutation == "external_push_basis_missing":
        row["signal"]["alert_eligibility"].pop("external_push_basis")
    elif mutation == "external_push_basis_blank":
        row["signal"]["alert_eligibility"]["external_push_basis"] = " "
    elif mutation == "external_push_basis_non_string":
        row["signal"]["alert_eligibility"]["external_push_basis"] = 123
    elif mutation == "external_push_basis_wrong":
        row["signal"]["alert_eligibility"]["external_push_basis"] = "legacy_signal"
    elif mutation == "external_push_ready_block_reason_non_string":
        row["signal"]["alert_eligibility"]["external_push_block_reason"] = 123
    elif mutation == "external_push_block_reason_blank":
        row["signal"]["alert_eligibility"]["external_push_ready"] = False
        row["signal"]["alert_eligibility"]["external_push_block_reason"] = " "
    elif mutation == "external_push_block_reason_non_string":
        row["signal"]["alert_eligibility"]["external_push_ready"] = False
        row["signal"]["alert_eligibility"]["external_push_block_reason"] = 123
    elif mutation == "agent_brief_scalar":
        row["agent_brief"] = "ready"
    elif mutation == "agent_brief_affected_entities_object":
        row["agent_brief"]["affected_entities"] = {"symbol": "BTC"}
    elif mutation == "agent_brief_affected_entities_member":
        row["agent_brief"]["affected_entities"] = ["BTC"]
    elif mutation == "news_item_id_missing":
        row.pop("news_item_id")
    elif mutation == "news_item_id_blank":
        row["news_item_id"] = " "
    elif mutation == "representative_news_item_id_missing":
        row.pop("representative_news_item_id")
    elif mutation == "representative_news_item_id_blank":
        row["representative_news_item_id"] = " "
    elif mutation == "token_impacts_object":
        row["token_impacts"] = {"symbol": "BTC"}
    elif mutation == "token_impacts_member":
        row["token_impacts"] = ["BTC"]
    elif mutation == "token_impacts_symbol_non_string":
        row["token_impacts"] = [{"symbol": 123}]
    elif mutation == "token_impacts_market_type_non_string":
        row["token_impacts"] = [{"symbol": "BTC", "market_type": 123}]
    elif mutation == "story_missing":
        row.pop("story")
    elif mutation == "story_scalar":
        row["story"] = "story"
    elif mutation == "story_story_key_non_string":
        row["story"]["story_key"] = 123
    elif mutation == "story_member_count_string":
        row["story"]["member_count"] = "1"
    elif mutation == "story_member_count_bool":
        row["story"]["member_count"] = True
    elif mutation == "story_member_count_negative":
        row["story"]["member_count"] = -1
    elif mutation == "story_source_domains_member_non_string":
        row["story"]["source_domains"] = ["example.test", 123]
    elif mutation == "market_scope_scalar":
        row["market_scope"] = ["crypto"]
    elif mutation == "market_scope_scope_non_list":
        row["market_scope"]["scope"] = "crypto"
    elif mutation == "market_scope_scope_member_non_string":
        row["market_scope"]["scope"] = ["crypto", 123]
    elif mutation == "market_scope_primary_non_string":
        row["market_scope"]["primary"] = 123
    elif mutation == "market_scope_status_non_string":
        row["market_scope"]["status"] = 123
    elif mutation == "market_scope_reason_non_string":
        row["market_scope"]["reason"] = 123
    elif mutation == "market_scope_basis_scalar":
        row["market_scope"]["basis"] = "crypto"
    elif mutation == "market_scope_version_non_string":
        row["market_scope"]["version"] = 123
    elif mutation == "agent_admission_scalar":
        row["agent_admission"] = "eligible"
    elif mutation == "agent_admission_payload_status_non_string":
        row["agent_admission"]["status"] = 123
    elif mutation == "agent_admission_payload_reason_non_string":
        row["agent_admission"]["reason"] = 123
    elif mutation == "agent_admission_payload_representative_non_string":
        row["agent_admission"]["representative_news_item_id"] = 123
    elif mutation == "agent_admission_payload_basis_scalar":
        row["agent_admission"]["basis"] = "test"
    elif mutation == "agent_admission_payload_version_non_string":
        row["agent_admission"]["version"] = 123
    elif mutation == "agent_admission_payload_eligible_non_bool":
        row["agent_admission"]["eligible"] = 1
    elif mutation == "latest_at_ms_missing":
        row.pop("latest_at_ms")
    elif mutation == "latest_at_ms_string":
        row["latest_at_ms"] = "recent"
    elif mutation == "row_id_missing":
        row.pop("row_id")
    elif mutation == "row_id_blank":
        row["row_id"] = " "
    elif mutation == "story_key_missing":
        row.pop("story_key")
    elif mutation == "story_key_blank":
        row["story_key"] = " "
    elif mutation == "duplicate_count_missing":
        row.pop("duplicate_count", None)
    elif mutation == "duplicate_count_string":
        row["duplicate_count"] = "1"
    elif mutation == "duplicate_count_bool":
        row["duplicate_count"] = True
    elif mutation == "duplicate_count_negative":
        row["duplicate_count"] = -1
    elif mutation == "source_domain_missing":
        row.pop("source_domain", None)
    elif mutation == "source_domain_blank":
        row["source_domain"] = " "
    elif mutation == "source_domain_non_string":
        row["source_domain"] = 123
    elif mutation == "canonical_url_blank":
        row["canonical_url"] = " "
    elif mutation == "canonical_url_non_string":
        row["canonical_url"] = {"url": "https://example.test/malformed-projection"}
    elif mutation == "agent_admission_status_missing":
        row.pop("agent_admission_status", None)
    elif mutation == "agent_admission_status_blank":
        row["agent_admission_status"] = " "
    elif mutation == "agent_admission_status_non_string":
        row["agent_admission_status"] = 123
    elif mutation == "agent_admission_reason_missing":
        row.pop("agent_admission_reason", None)
    elif mutation == "agent_admission_reason_blank":
        row["agent_admission_reason"] = " "
    elif mutation == "agent_admission_reason_non_string":
        row["agent_admission_reason"] = 123
    else:  # pragma: no cover - keeps parametrization explicit.
        raise AssertionError(mutation)

    with pytest.raises(ValueError, match=error):
        engine(news=FakeNews([row])).evaluate(now_ms=NOW_MS)


def test_news_high_signal_public_mapping_payloads_drop_unknown_fields_without_passthrough() -> None:
    row = _market_scoped_news_row(
        {
            "news_item_id": "news-public-mapping-allowlist",
            "representative_news_item_id": "news-public-mapping-allowlist",
            "story_key": "news-story:subject:public-mapping-allowlist:t412000",
            "story": {
                "story_key": "news-story:subject:public-mapping-allowlist:t412000",
                "member_count": 1,
                "source_domains": ["example.test"],
                "legacy_story_passthrough": {"bad": True},
            },
            "market_scope": {
                "scope": ["crypto"],
                "primary": "crypto",
                "status": "classified",
                "reason": "test_crypto_subject",
                "basis": {},
                "version": "test_news_market_scope_v1",
                "legacy_scope_passthrough": "bad",
            },
            "agent_admission": {
                "status": "eligible",
                "reason": "test_agent_ready",
                "representative_news_item_id": "news-public-mapping-allowlist",
                "legacy_admission_passthrough": "bad",
            },
            "latest_at_ms": NOW_MS - 5_000,
            "headline": "Unknown nested mapping fields should not publish",
            "source_domain": "example.test",
            "canonical_url": "https://example.test/public-mapping-allowlist",
            "duplicate_count": 1,
            "signal": {
                "direction": "bullish",
                "alert_eligibility": {
                    "in_app_eligible": True,
                    "external_push_ready": True,
                    "external_push_basis": "agent_brief",
                    "decision_class": "driver",
                },
            },
            "token_impacts": [{"symbol": "BTC", "score": 90}],
            "agent_brief": {
                "status": "ready",
                "direction": "bullish",
                "decision_class": "driver",
                "summary_zh": "Unknown nested fields must not pass through.",
                "affected_entities": [{"symbol": "BTC"}],
            },
        }
    )

    candidate = engine(news=FakeNews([row])).evaluate(now_ms=NOW_MS)[0]

    assert candidate.payload["story"] == {
        "story_key": "news-story:subject:public-mapping-allowlist:t412000",
        "member_count": 1,
        "source_domains": ["example.test"],
    }
    assert "legacy_scope_passthrough" not in candidate.payload["market_scope"]
    assert "legacy_admission_passthrough" not in candidate.payload["agent_admission"]


def test_news_high_signal_allows_market_wide_ready_watch_candidate():
    market_scope = {
        "scope": ["us_equity"],
        "primary": "us_equity",
        "status": "classified",
        "reason": "private_company_equity_context",
        "basis": {"subject": "private_company_equity_context"},
        "version": "test_news_market_scope_v1",
    }
    news = FakeNews(
        [
            {
                "row_id": "news-page-row:news-market-watch",
                "news_item_id": "news-market-watch",
                "representative_news_item_id": "news-market-watch",
                "story_key": "news-story:subject:spacex-valuation:t412000",
                "story": {"story_key": "news-story:subject:spacex-valuation:t412000", "member_count": 1},
                "latest_at_ms": NOW_MS - 5_000,
                "headline": "SpaceX valuation reset lifts private-market risk appetite",
                "source_domain": "example.test",
                "canonical_url": "https://example.test/spacex",
                "duplicate_count": 1,
                "market_scope": market_scope,
                "agent_admission_status": "eligible",
                "agent_admission_reason": "market_wide_watch",
                "agent_admission": {
                    "status": "eligible",
                    "reason": "market_wide_watch",
                    "representative_news_item_id": "news-market-watch",
                },
                "content_class": "low_signal",
                "content_tags": ["private_markets"],
                "signal": {
                    "direction": "bullish",
                    "alert_eligibility": {
                        "in_app_eligible": True,
                        "external_push_ready": True,
                        "external_push_basis": "agent_brief",
                        "decision_class": "watch",
                        "market_scope": market_scope,
                    },
                },
                "token_impacts": [{"symbol": "SPCX", "score": 90}],
                "agent_brief": {
                    "status": "ready",
                    "direction": "bullish",
                    "decision_class": "watch",
                    "title_zh": "SpaceX 估值重估",
                    "summary_zh": "私人市场风险偏好改善，值得观察相关权益风险。",
                    "brief_json": {
                        "title_zh": "SpaceX 估值重估",
                        "summary_zh": "私人市场风险偏好改善，值得观察相关权益风险。",
                        "market_impacts": [{"label": "SPCX", "market_type": "us_equity"}],
                    },
                },
            }
        ]
    )
    notifications = NotificationsConfig(
        rules={
            "news_high_signal": {
                "enabled": True,
                "channels": ["in_app", "pushdeer"],
                "cooldown_seconds": 3600,
            }
        }
    )

    candidates = [
        item
        for item in engine(news=news, notifications=notifications).evaluate(now_ms=NOW_MS)
        if item.rule_id == "news_high_signal"
    ]

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.channels == ("in_app", "pushdeer")
    assert candidate.payload["market_scope"] == market_scope
    assert candidate.payload["agent_admission_status"] == "eligible"
    assert candidate.payload["agent_admission_reason"] == "market_wide_watch"
    assert candidate.payload["agent_admission"]["representative_news_item_id"] == "news-market-watch"
    assert "analysis_admission_status" not in candidate.payload
    assert "analysis_admission_reason" not in candidate.payload
    assert "analysis_admission" not in candidate.payload


def test_news_high_signal_uses_projection_external_push_readiness() -> None:
    news = FakeNews(
        [
            _market_scoped_news_row(
                {
                    "news_item_id": "news-ready-without-publishable-brief",
                    "latest_at_ms": NOW_MS - 5_000,
                    "agent_brief_computed_at_ms": NOW_MS - 1_000,
                    "headline": "Ready status without publishable agent text",
                    "source_domain": "example.test",
                    "canonical_url": "https://example.test/ready-empty",
                    "signal": {
                        "direction": "bullish",
                        "alert_eligibility": {
                            "in_app_eligible": True,
                            "external_push_ready": False,
                            "external_push_block_reason": "agent_brief_missing_summary",
                            "decision_class": "driver",
                        },
                    },
                    "token_impacts": [{"symbol": "BTC", "score": 90}],
                    "agent_brief": {
                        "status": "ready",
                        "direction": "bullish",
                        "decision_class": "driver",
                        "title_zh": "AI 标题但缺少正文",
                        "brief_json": {"title_zh": "AI 标题但缺少正文"},
                    },
                }
            )
        ]
    )
    notifications = NotificationsConfig(
        rules={
            "news_high_signal": {
                "enabled": True,
                "channels": ["in_app", "pushdeer"],
                "cooldown_seconds": 3600,
            }
        }
    )

    candidates = [
        item
        for item in engine(news=news, notifications=notifications).evaluate(now_ms=NOW_MS)
        if item.rule_id == "news_high_signal"
    ]

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.channels == ("in_app",)
    assert candidate.payload["external_push_eligible"] is False
    assert candidate.payload["external_push_suppression_reason"] == "agent_brief_missing_summary"


def test_news_high_signal_external_push_requires_current_summary_without_market_read_fallback() -> None:
    news = FakeNews(
        [
            _market_scoped_news_row(
                {
                    "news_item_id": "news-ready-market-read-only",
                    "latest_at_ms": NOW_MS - 5_000,
                    "agent_brief_computed_at_ms": NOW_MS - 1_000,
                    "headline": "Ready status with legacy market read only",
                    "source_domain": "example.test",
                    "canonical_url": "https://example.test/ready-market-read-only",
                    "signal": {
                        "direction": "bullish",
                        "alert_eligibility": {
                            "in_app_eligible": True,
                            "external_push_ready": True,
                            "external_push_basis": "agent_brief",
                            "decision_class": "driver",
                        },
                    },
                    "token_impacts": [{"symbol": "BTC", "score": 90}],
                    "agent_brief": {
                        "status": "ready",
                        "direction": "bullish",
                        "decision_class": "driver",
                        "title_zh": "AI 标题但缺少当前摘要",
                        "market_read_zh": "旧 market_read 不应让外部推送通过。",
                    },
                }
            )
        ]
    )
    notifications = NotificationsConfig(
        rules={
            "news_high_signal": {
                "enabled": True,
                "channels": ["in_app", "pushdeer"],
                "cooldown_seconds": 3600,
            }
        }
    )

    candidates = [
        item
        for item in engine(news=news, notifications=notifications).evaluate(now_ms=NOW_MS)
        if item.rule_id == "news_high_signal"
    ]

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.channels == ("in_app",)
    assert "旧 market_read 不应让外部推送通过。" not in candidate.body
    assert candidate.payload["external_push_eligible"] is False
    assert candidate.payload["external_push_signature"] is None
    assert candidate.payload["external_push_suppression_reason"] == "agent_brief_missing_summary"


def test_news_high_signal_rejects_malformed_ready_summary_without_string_repair() -> None:
    news = FakeNews(
        [
            _market_scoped_news_row(
                {
                    "news_item_id": "news-ready-malformed-summary",
                    "latest_at_ms": NOW_MS - 5_000,
                    "agent_brief_computed_at_ms": NOW_MS - 1_000,
                    "headline": "Ready status with malformed summary",
                    "source_domain": "example.test",
                    "canonical_url": "https://example.test/ready-malformed-summary",
                    "signal": {
                        "direction": "bullish",
                        "alert_eligibility": {
                            "in_app_eligible": True,
                            "external_push_ready": True,
                            "external_push_basis": "agent_brief",
                            "decision_class": "driver",
                        },
                    },
                    "token_impacts": [{"symbol": "BTC", "score": 90}],
                    "agent_brief": {
                        "status": "ready",
                        "direction": "bullish",
                        "decision_class": "driver",
                        "title_zh": "AI 标题但摘要类型错误",
                        "summary_zh": 123,
                    },
                }
            )
        ]
    )

    with pytest.raises(ValueError, match="news_high_signal_agent_brief_summary_zh_required"):
        engine(news=news).evaluate(now_ms=NOW_MS)


def test_news_display_title_rejects_malformed_agent_title_without_string_repair() -> None:
    row = _market_scoped_news_row(
        {
            "news_item_id": "news-malformed-title",
            "headline": "Headline fallback remains available",
            "signal": {"display_signal": {"title_zh": "Projected display fallback"}},
        }
    )

    with pytest.raises(ValueError, match="news_high_signal_agent_brief_title_zh_required"):
        _news_display_title(row, agent_brief={"title_zh": 123})


def test_news_display_title_rejects_malformed_projected_title_without_string_repair() -> None:
    row = _market_scoped_news_row(
        {
            "news_item_id": "news-malformed-projected-title",
            "headline": "Headline fallback remains available",
            "signal": {"display_signal": {"title_zh": 123}},
        }
    )

    with pytest.raises(ValueError, match="news_high_signal_display_signal_title_zh_required"):
        _news_display_title(row, agent_brief={})


def test_news_display_title_rejects_malformed_headline_without_string_repair() -> None:
    row = _market_scoped_news_row(
        {
            "news_item_id": "news-malformed-headline",
            "headline": 123,
            "signal": {"display_signal": {}},
        }
    )

    with pytest.raises(ValueError, match="news_high_signal_headline_required"):
        _news_display_title(row, agent_brief={})


def test_news_display_title_falls_back_when_agent_title_is_absent() -> None:
    row = _market_scoped_news_row(
        {
            "news_item_id": "news-title-fallback",
            "headline": "Headline fallback remains available",
            "signal": {"display_signal": {"title_zh": "Projected display fallback"}},
        }
    )

    assert _news_display_title(row, agent_brief={}) == "Projected display fallback"


@pytest.mark.parametrize("field_name", ["direction", "decision_class", "title_zh", "summary_zh", "market_read_zh"])
def test_news_high_signal_public_agent_brief_rejects_malformed_optional_text_without_payload_passthrough(
    field_name: str,
) -> None:
    news = FakeNews(
        [
            _market_scoped_news_row(
                {
                    "news_item_id": f"news-pending-malformed-{field_name}",
                    "latest_at_ms": NOW_MS - 5_000,
                    "headline": "Pending brief with malformed public field",
                    "source_domain": "example.test",
                    "canonical_url": f"https://example.test/pending-malformed-{field_name}",
                    "signal": {
                        "direction": "bullish",
                        "alert_eligibility": {
                            "in_app_eligible": True,
                            "external_push_ready": False,
                            "external_push_block_reason": "agent_brief_not_ready",
                            "decision_class": "driver",
                        },
                    },
                    "token_impacts": [{"symbol": "BTC", "score": 90}],
                    "agent_brief": {
                        "status": "pending",
                        field_name: 123,
                    },
                }
            )
        ]
    )

    with pytest.raises(ValueError, match=f"news_high_signal_agent_brief_{field_name}_required"):
        engine(news=news).evaluate(now_ms=NOW_MS)


@pytest.mark.parametrize("field_name", ["label", "symbol", "name", "entity_type", "reason_zh"])
def test_news_high_signal_public_agent_brief_rejects_malformed_affected_entity_text_fields(
    field_name: str,
) -> None:
    news = FakeNews(
        [
            _market_scoped_news_row(
                {
                    "news_item_id": f"news-malformed-affected-{field_name}",
                    "latest_at_ms": NOW_MS - 5_000,
                    "headline": "Malformed public affected entity",
                    "source_domain": "example.test",
                    "canonical_url": f"https://example.test/malformed-affected-{field_name}",
                    "signal": {
                        "direction": "bullish",
                        "alert_eligibility": {
                            "in_app_eligible": True,
                            "external_push_ready": False,
                            "external_push_block_reason": "agent_brief_not_ready",
                            "decision_class": "driver",
                        },
                    },
                    "token_impacts": [{"symbol": "BTC", "score": 90}],
                    "agent_brief": {
                        "status": "pending",
                        "affected_entities": [
                            {
                                "symbol": "BTC",
                                "label": "BTC",
                                field_name: 123,
                            }
                        ],
                    },
                }
            )
        ]
    )

    with pytest.raises(ValueError, match=f"news_high_signal_agent_brief_affected_entities_{field_name}_required"):
        engine(news=news).evaluate(now_ms=NOW_MS)


def test_news_high_signal_public_agent_brief_rejects_malformed_affected_entity_evidence_refs() -> None:
    news = FakeNews(
        [
            _market_scoped_news_row(
                {
                    "news_item_id": "news-malformed-affected-evidence",
                    "latest_at_ms": NOW_MS - 5_000,
                    "headline": "Malformed public affected entity evidence",
                    "source_domain": "example.test",
                    "canonical_url": "https://example.test/malformed-affected-evidence",
                    "signal": {
                        "direction": "bullish",
                        "alert_eligibility": {
                            "in_app_eligible": True,
                            "external_push_ready": False,
                            "external_push_block_reason": "agent_brief_not_ready",
                            "decision_class": "driver",
                        },
                    },
                    "token_impacts": [{"symbol": "BTC", "score": 90}],
                    "agent_brief": {
                        "status": "pending",
                        "affected_entities": [{"symbol": "BTC", "evidence_refs": ["news:item", 123]}],
                    },
                }
            )
        ]
    )

    with pytest.raises(ValueError, match="news_high_signal_agent_brief_affected_entities_evidence_refs_required"):
        engine(news=news).evaluate(now_ms=NOW_MS)


@pytest.mark.parametrize(
    ("missing_field", "suppression_reason"),
    [
        ("direction", "agent_brief_missing_direction"),
        ("decision_class", "agent_brief_missing_decision_class"),
    ],
)
def test_news_high_signal_external_push_and_payload_require_ready_brief_signal_fields_without_display_signal_fallback(
    missing_field: str,
    suppression_reason: str,
) -> None:
    agent_brief = {
        "status": "ready",
        "direction": "bullish",
        "decision_class": "driver",
        "title_zh": "AI 标题",
        "summary_zh": "当前摘要可推送。",
    }
    agent_brief.pop(missing_field)
    news = FakeNews(
        [
            _market_scoped_news_row(
                {
                    "news_item_id": f"news-ready-missing-{missing_field}",
                    "latest_at_ms": NOW_MS - 5_000,
                    "agent_brief_computed_at_ms": NOW_MS - 1_000,
                    "headline": "Ready status with signal fallback temptation",
                    "source_domain": "example.test",
                    "canonical_url": f"https://example.test/ready-missing-{missing_field}",
                    "signal": {
                        "direction": "bullish",
                        "display_signal": {"direction": "bullish"},
                        "alert_eligibility": {
                            "in_app_eligible": True,
                            "external_push_ready": True,
                            "external_push_basis": "agent_brief",
                            "decision_class": "driver",
                        },
                    },
                    "token_impacts": [{"symbol": "BTC", "score": 90}],
                    "agent_brief": agent_brief,
                }
            )
        ]
    )
    notifications = NotificationsConfig(
        rules={
            "news_high_signal": {
                "enabled": True,
                "channels": ["in_app", "pushdeer"],
                "cooldown_seconds": 3600,
            }
        }
    )

    candidates = [
        item
        for item in engine(news=news, notifications=notifications).evaluate(now_ms=NOW_MS)
        if item.rule_id == "news_high_signal"
    ]

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.channels == ("in_app",)
    assert candidate.payload["external_push_eligible"] is False
    assert candidate.payload["external_push_signature"] is None
    assert candidate.payload["external_push_suppression_reason"] == suppression_reason
    assert candidate.payload[missing_field] == ""


def test_news_external_push_signature_requires_ready_brief_direction_without_none_signature() -> None:
    row = _market_scoped_news_row(
        {
            "news_item_id": "news-signature-missing-direction",
            "latest_at_ms": NOW_MS - 5_000,
            "headline": "Signature should fail closed",
            "source_domain": "example.test",
            "canonical_url": "https://example.test/signature-missing-direction",
            "signal": {
                "direction": "bullish",
                "display_signal": {"direction": "bullish"},
                "alert_eligibility": {
                    "in_app_eligible": True,
                    "external_push_ready": True,
                    "external_push_basis": "agent_brief",
                    "decision_class": "driver",
                },
            },
            "token_impacts": [{"symbol": "BTC"}],
            "agent_brief": {
                "status": "ready",
                "decision_class": "driver",
                "summary_zh": "Ready brief is missing direction.",
            },
        }
    )

    with pytest.raises(ValueError, match="news_high_signal_agent_brief_direction_required"):
        _news_external_push_signature(row, occurrence_at_ms=NOW_MS, cooldown_seconds=3600)


def test_news_high_signal_ignores_legacy_brief_json_for_display_payload_and_push():
    news = FakeNews(
        [
            _market_scoped_news_row(
                {
                    "news_item_id": "news-legacy-brief-json",
                    "latest_at_ms": NOW_MS - 5_000,
                    "agent_brief_computed_at_ms": NOW_MS - 1_000,
                    "headline": "Scalar headline wins",
                    "source_domain": "example.test",
                    "canonical_url": "https://example.test/legacy-brief-json",
                    "signal": {
                        "direction": "bullish",
                        "alert_eligibility": {
                            "in_app_eligible": True,
                            "external_push_ready": True,
                            "external_push_basis": "agent_brief",
                            "decision_class": "driver",
                        },
                    },
                    "token_impacts": [],
                    "agent_brief": {
                        "status": "ready",
                        "direction": "bullish",
                        "decision_class": "driver",
                        "brief_json": {
                            "title_zh": "旧 JSON 标题不应展示",
                            "summary_zh": "旧 JSON 摘要不应推送",
                            "affected_entities": [{"symbol": "LEGACY"}],
                            "agent_run_id": "run-legacy",
                        },
                    },
                }
            )
        ]
    )
    notifications = NotificationsConfig(
        rules={
            "news_high_signal": {
                "enabled": True,
                "channels": ["in_app", "pushdeer"],
                "cooldown_seconds": 3600,
            }
        }
    )

    candidates = [
        item
        for item in engine(news=news, notifications=notifications).evaluate(now_ms=NOW_MS)
        if item.rule_id == "news_high_signal"
    ]

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.channels == ("in_app",)
    assert candidate.title == "Scalar headline wins"
    assert "旧 JSON 摘要不应推送" not in candidate.body
    assert candidate.symbol is None
    assert candidate.payload["affected_entities"] == []
    assert candidate.payload["agent_brief"] == {
        "status": "ready",
        "direction": "bullish",
        "decision_class": "driver",
    }
    assert candidate.payload["external_push_suppression_reason"] == "agent_brief_missing_summary"


def test_news_high_signal_affected_entities_ignore_legacy_symbol_aliases():
    news = FakeNews(
        [
            _market_scoped_news_row(
                {
                    "news_item_id": "news-legacy-entity-alias",
                    "latest_at_ms": NOW_MS - 5_000,
                    "headline": "Legacy affected entity alias",
                    "source_domain": "example.test",
                    "canonical_url": "https://example.test/legacy-entity-alias",
                    "signal": {
                        "direction": "bullish",
                        "alert_eligibility": {
                            "in_app_eligible": True,
                            "external_push_ready": True,
                            "external_push_basis": "agent_brief",
                            "decision_class": "driver",
                        },
                    },
                    "token_impacts": [{"market_type": "spot"}],
                    "agent_brief": {
                        "status": "ready",
                        "direction": "bullish",
                        "decision_class": "driver",
                        "summary_zh": "Legacy entity aliases must not drive notification asset identity.",
                        "affected_entities": [{"ticker": "LEGACY"}],
                    },
                }
            )
        ]
    )

    candidate = next(item for item in engine(news=news).evaluate(now_ms=NOW_MS) if item.rule_id == "news_high_signal")

    assert candidate.symbol is None
    assert candidate.payload["affected_entities"] == []
    assert "affected_entities" not in candidate.payload["agent_brief"]
    assert candidate.payload["token_impacts"] == []


def test_news_high_signal_rejects_malformed_agent_brief_status_without_pending_repair():
    news = FakeNews(
        [
            _market_scoped_news_row(
                {
                    "news_item_id": "news-bad-status",
                    "latest_at_ms": NOW_MS - 1_000,
                    "headline": "Malformed agent status",
                    "source_domain": "example.test",
                    "canonical_url": "https://example.test/bad-status",
                    "signal": {
                        "direction": "bullish",
                        "display_signal": {"direction": "bullish", "title_zh": "Fallback title"},
                        "alert_eligibility": {
                            "in_app_eligible": True,
                            "external_push_ready": False,
                            "external_push_block_reason": "agent_brief_not_ready",
                            "decision_class": "driver",
                        },
                    },
                    "token_impacts": [{"symbol": "BAD"}],
                    "agent_brief": {"status": True},
                }
            )
        ]
    )

    with pytest.raises(ValueError, match="news_high_signal_agent_brief_status_required"):
        engine(news=news).evaluate(now_ms=NOW_MS)


def test_news_high_signal_rejects_malformed_pending_signal_direction_without_string_repair():
    news = FakeNews(
        [
            _market_scoped_news_row(
                {
                    "news_item_id": "news-bad-direction",
                    "latest_at_ms": NOW_MS - 1_000,
                    "headline": "Malformed signal direction",
                    "source_domain": "example.test",
                    "canonical_url": "https://example.test/bad-direction",
                    "signal": {
                        "direction": True,
                        "alert_eligibility": {
                            "in_app_eligible": True,
                            "external_push_ready": False,
                            "external_push_block_reason": "agent_brief_not_ready",
                            "decision_class": "driver",
                        },
                    },
                    "token_impacts": [{"symbol": "BAD"}],
                    "agent_brief": {"status": "pending"},
                }
            )
        ]
    )

    with pytest.raises(ValueError, match="news_high_signal_signal_direction_required"):
        engine(news=news).evaluate(now_ms=NOW_MS)


def test_news_high_signal_skips_stale_source_items_even_when_agent_finished_now():
    news = FakeNews(
        [
            _market_scoped_news_row(
                {
                    "news_item_id": "news-old",
                    "latest_at_ms": NOW_MS - 7 * 60 * 60_000,
                    "agent_brief_computed_at_ms": NOW_MS - 1_000,
                    "headline": "Old high signal",
                    "source_domain": "example.test",
                    "canonical_url": "https://example.test/old",
                    "signal": {
                        "direction": "bullish",
                        "alert_eligibility": {
                            "in_app_eligible": True,
                            "external_push_ready": True,
                            "external_push_basis": "agent_brief",
                            "decision_class": "driver",
                        },
                    },
                    "token_impacts": [{"symbol": "OLD", "score": 90}],
                    "agent_brief": {
                        "status": "ready",
                        "direction": "bullish",
                        "decision_class": "driver",
                        "title_zh": "旧新闻不应推送",
                        "summary_zh": "agent 刚完成，但源新闻已经过期。",
                        "brief_json": {
                            "title_zh": "旧新闻不应推送",
                            "summary_zh": "agent 刚完成，但源新闻已经过期。",
                            "affected_entities": [{"symbol": "OLD"}],
                        },
                    },
                }
            )
        ]
    )

    candidates = [item for item in engine(news=news).evaluate(now_ms=NOW_MS) if item.rule_id == "news_high_signal"]

    assert candidates == []


def test_news_high_signal_semantic_dedup_ignores_projection_and_summary_churn():
    base_row = _market_scoped_news_row(
        {
            "news_item_id": "news-1",
            "latest_at_ms": NOW_MS - 5_000,
            "agent_brief_computed_at_ms": NOW_MS - 1_000,
            "headline": "Major listing catalyst",
            "source_domain": "example.test",
            "canonical_url": "https://example.test/news-1",
            "duplicate_count": 3,
            "signal": {
                "direction": "bullish",
                "alert_eligibility": {
                    "in_app_eligible": True,
                    "external_push_ready": True,
                    "external_push_basis": "agent_brief",
                    "decision_class": "driver",
                },
            },
            "token_impacts": [{"symbol": "BOV"}],
            "agent_brief": {
                "status": "ready",
                "direction": "bullish",
                "decision_class": "driver",
                "summary_zh": "第一版中文摘要。",
                "brief_json": {
                    "summary_zh": "第一版中文摘要。",
                    "watch_triggers": ["成交量确认"],
                    "affected_entities": [{"symbol": "BOV"}],
                },
            },
        }
    )
    revised_row = {
        **base_row,
        "news_item_id": "news-2",
        "projection_version": "news-page-v2",
        "agent_brief": {
            **base_row["agent_brief"],
            "summary_zh": "第二版中文摘要，措辞不同。",
            "brief_json": {
                **base_row["agent_brief"]["brief_json"],
                "summary_zh": "第二版中文摘要，措辞不同。",
            },
        },
    }

    candidates = [
        item
        for item in engine(news=FakeNews([base_row, revised_row])).evaluate(now_ms=NOW_MS)
        if item.rule_id == "news_high_signal"
    ]

    assert len(candidates) == 1


def test_jpm_citi_story_variants_emit_one_candidate():
    story_key = "news-story:subject:jpmorgan-citi-tokenized-deposit:t412000"
    jpm_row = _market_scoped_news_row(
        {
            "row_id": "row-jpm-story",
            "news_item_id": "news-jpm",
            "representative_news_item_id": "news-jpm",
            "story_key": story_key,
            "story": {
                "story_key": story_key,
                "representative_news_item_id": "news-jpm",
                "member_news_item_ids": ["news-jpm", "news-citi"],
                "member_count": 2,
                "source_domains": ["bloomberg.com", "reuters.com"],
            },
            "latest_at_ms": NOW_MS - 5_000,
            "headline": "JPMorgan tests tokenized deposit network",
            "source_domain": "bloomberg.com",
            "canonical_url": "https://bloomberg.example/jpm-tokenized-deposits",
            "content_class": "crypto_market",
            "content_tags": ["tokenized_deposits", "jpmorgan"],
            "signal": {
                "direction": "bullish",
                "alert_eligibility": {
                    "in_app_eligible": True,
                    "external_push_ready": False,
                    "external_push_block_reason": "agent_brief_not_ready",
                    "decision_class": "driver",
                },
            },
            "token_impacts": [{"symbol": "BTC", "score": 91}],
            "agent_brief": {"status": "pending"},
        }
    )
    citi_row = _market_scoped_news_row(
        {
            **jpm_row,
            "row_id": "row-citi-story",
            "news_item_id": "news-citi",
            "headline": "Citi joins tokenized deposit pilot with JPMorgan",
            "source_domain": "reuters.com",
            "canonical_url": "https://reuters.example/citi-tokenized-deposits",
            "content_tags": ["tokenized_deposits", "citi"],
            "token_impacts": [{"symbol": "ETH", "score": 90}],
        }
    )

    candidates = [
        item
        for item in engine(news=FakeNews([jpm_row, citi_row])).evaluate(now_ms=NOW_MS)
        if item.rule_id == "news_high_signal"
    ]

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.entity_type == "news_story"
    assert candidate.entity_key == f"news_story:{story_key}"
    assert candidate.source_id == "row-jpm-story"
    assert candidate.payload["story_key"] == story_key
    assert candidate.payload["story"]["member_count"] == 2
    assert candidate.payload["market_scope"]["primary"] == "crypto"
    assert candidate.payload["agent_admission_status"] == "eligible"
    assert candidate.payload["agent_admission_reason"] == "test_agent_ready"
    assert candidate.payload["agent_admission"]["representative_news_item_id"] == "news-jpm"
    assert candidate.payload["decision_class"] == "driver"
    assert candidate.payload["direction"] == "bullish"
    assert candidate.payload["affected_entities"] == []


def test_news_high_signal_external_push_signature_keeps_distinct_stories_push_eligible():
    base_row = _market_scoped_news_row(
        {
            "row_id": "row-story-a",
            "news_item_id": "news-story-a",
            "story_key": "news-story:subject:oil-supply-a:t412000",
            "story": {"story_key": "news-story:subject:oil-supply-a:t412000", "member_count": 1},
            "latest_at_ms": NOW_MS - 5_000,
            "agent_brief_computed_at_ms": NOW_MS - 1_000,
            "headline": "Oil supply shock story A",
            "source_domain": "example.test",
            "canonical_url": "https://example.test/news-story-a",
            "content_tags": ["oil"],
            "signal": {
                "direction": "bullish",
                "alert_eligibility": {
                    "in_app_eligible": True,
                    "external_push_ready": True,
                    "external_push_basis": "agent_brief",
                    "decision_class": "driver",
                },
            },
            "token_impacts": [{"symbol": "CL", "score": 90}],
            "agent_brief": {
                "status": "ready",
                "direction": "bullish",
                "decision_class": "driver",
                "summary_zh": "第一条独立故事。",
                "brief_json": {
                    "summary_zh": "第一条独立故事。",
                    "affected_entities": [{"symbol": "CL"}],
                },
            },
        }
    )
    second_story = {
        **base_row,
        "row_id": "row-story-b",
        "news_item_id": "news-story-b",
        "story_key": "news-story:subject:oil-supply-b:t412000",
        "story": {"story_key": "news-story:subject:oil-supply-b:t412000", "member_count": 1},
        "headline": "Oil supply shock story B",
        "canonical_url": "https://example.test/news-story-b",
        "agent_brief": {
            **base_row["agent_brief"],
            "summary_zh": "第二条独立故事。",
            "brief_json": {
                "summary_zh": "第二条独立故事。",
                "affected_entities": [{"symbol": "CL"}],
            },
        },
    }
    notifications = NotificationsConfig(
        rules={
            "news_high_signal": {
                "enabled": True,
                "channels": ["in_app", "pushdeer"],
                "cooldown_seconds": 3600,
            }
        }
    )

    candidates = [
        item
        for item in engine(news=FakeNews([base_row, second_story]), notifications=notifications).evaluate(now_ms=NOW_MS)
        if item.rule_id == "news_high_signal"
    ]

    assert len(candidates) == 2
    assert candidates[0].payload["external_push_signature"] != candidates[1].payload["external_push_signature"]
    assert candidates[0].channels == ("in_app", "pushdeer")
    assert candidates[1].channels == ("in_app", "pushdeer")
    assert candidates[1].payload["external_push_suppression_reason"] is None


def test_news_high_signal_same_story_variants_emit_one_candidate_without_item_identity():
    base_row = _market_scoped_news_row(
        {
            "news_item_id": "news-1",
            "latest_at_ms": NOW_MS - 5_000,
            "agent_brief_computed_at_ms": NOW_MS - 1_000,
            "headline": "Iran disruption lifts oil risk",
            "source_domain": "example.test",
            "canonical_url": "https://example.test/news-1",
            "duplicate_count": 1,
            "content_tags": ["iran"],
            "signal": {
                "direction": "bullish",
                "alert_eligibility": {
                    "in_app_eligible": True,
                    "external_push_ready": True,
                    "external_push_basis": "agent_brief",
                    "decision_class": "driver",
                },
            },
            "token_impacts": [{"symbol": "CL", "score": 90}, {"symbol": "BTC", "score": 25}],
            "agent_brief": {
                "status": "ready",
                "direction": "bullish",
                "decision_class": "driver",
                "summary_zh": "第一条同主题新闻。",
                "brief_json": {
                    "summary_zh": "第一条同主题新闻。",
                    "watch_triggers": ["原油冲击"],
                    "affected_entities": [{"symbol": "CL"}],
                },
            },
        }
    )
    same_topic_row = {
        **base_row,
        "news_item_id": "news-2",
        "headline": "Hormuz risk sends crude higher",
        "canonical_url": "https://example.test/news-2",
        "content_tags": ["hormuz"],
        "agent_brief": {
            **base_row["agent_brief"],
            "summary_zh": "第二条同主题新闻。",
            "brief_json": {
                "summary_zh": "第二条同主题新闻。",
                "watch_triggers": ["航运风险"],
                "affected_entities": [{"symbol": "CL"}],
            },
        },
    }
    notifications = NotificationsConfig(
        rules={
            "news_high_signal": {
                "enabled": True,
                "channels": ["in_app", "pushdeer"],
                "cooldown_seconds": 3600,
            }
        }
    )

    candidates = [
        item
        for item in engine(news=FakeNews([base_row, same_topic_row]), notifications=notifications).evaluate(
            now_ms=NOW_MS
        )
        if item.rule_id == "news_high_signal"
    ]

    assert len(candidates) == 1
    assert candidates[0].entity_type == "news_story"
    assert candidates[0].entity_key == f"news_story:{base_row['story_key']}"
    assert candidates[0].payload["story_key"] == base_row["story_key"]
    assert candidates[0].payload["external_push_signature"].startswith("sha256:")
    assert candidates[0].channels == ("in_app", "pushdeer")
    assert candidates[0].payload["external_push_suppression_reason"] is None


def _only_pulse_notification(row: dict, *, notifications: NotificationsConfig | None = None):
    candidates = engine(pulse=FakePulse([row]), notifications=notifications).evaluate(now_ms=NOW_MS)
    pulse_candidates = [item for item in candidates if item.rule_id == "signal_pulse_candidate"]
    assert len(pulse_candidates) == 1
    return pulse_candidates[0]


def _signal_pulse_notifications(
    *,
    channels: list[str],
    statuses: list[str],
    scopes: list[str] | None = None,
    cooldown_seconds: int = 900,
) -> NotificationsConfig:
    return NotificationsConfig(
        rules={
            "signal_pulse_candidate": {
                "enabled": True,
                "channels": channels,
                "window": "1h",
                "scopes": scopes or ["all"],
                "statuses": statuses,
                "cooldown_seconds": cooldown_seconds,
            }
        }
    )


def pulse_candidate(
    candidate_id: str,
    *,
    status: str = "token_watch",
    score_band: str = "watch",
    symbol: str | None = "PEPE",
    window: str = "1h",
    scope: str = "all",
    candidate_score: float = 82.0,
    radar_score: dict | None = None,
    risks: list[str] | None = None,
    confirmations: list[str] | None = None,
    eligible_for_high_alert: bool = True,
    blocked_reasons: list[str] | None = None,
    market_facts: dict | None = None,
    social_facts: dict | None = None,
    gate: dict | None = None,
    recommendation_summary: str = "社交与链上事实支持继续观察。",
    evidence_ids: list[str] | None = None,
    source_ids: list[str] | None = None,
    edge_events: list[str] | None = None,
    updated_at_ms: int = NOW_MS,
) -> dict:
    resolved_blocked_reasons = (
        blocked_reasons if blocked_reasons is not None else (risks if status == "risk_rejected_high_info" else [])
    )
    resolved_gate = {
        "pulse_status": status,
        "verdict": status,
        "candidate_score": candidate_score,
        "score_band": score_band,
        "gate_reasons": resolved_blocked_reasons or ["factor_snapshot_watch_gate_passed"],
        "risk_reasons": resolved_blocked_reasons,
        "hard_risks": resolved_blocked_reasons,
        "max_recommendation": "trade_candidate"
        if status == "trade_candidate"
        else "watch"
        if status == "token_watch"
        else "research"
        if status == "risk_rejected_high_info"
        else "ignore",
        "eligible_for_high_alert": eligible_for_high_alert and not resolved_blocked_reasons,
        "blocked_reasons": resolved_blocked_reasons,
    }
    if gate:
        resolved_gate.update(gate)
    factor_snapshot = _factor_snapshot(
        symbol=symbol,
        target_type="Asset" if symbol else None,
        target_id=f"asset:{candidate_id}" if symbol else None,
        eligible_for_high_alert=eligible_for_high_alert,
        blocked_reasons=resolved_blocked_reasons,
        market_facts=market_facts,
        social_facts=social_facts,
        rank_score=candidate_score,
    )
    return {
        "candidate_id": candidate_id,
        "candidate_type": "token_target",
        "subject_key": symbol or "source:event",
        "target_type": "Asset" if symbol else None,
        "target_id": f"asset:{candidate_id}" if symbol else None,
        "symbol": symbol,
        "window": window,
        "scope": scope,
        "pulse_status": status,
        "verdict": status,
        "social_phase": "ignition",
        "candidate_score": candidate_score,
        "score_band": score_band,
        "radar_score_json": radar_score or {"heat": {"score": 82}},
        "factor_snapshot_json": factor_snapshot,
        "gate_json": resolved_gate,
        "decision_route": "meme",
        "decision_recommendation": "watchlist",
        "decision_confidence": 0.72,
        "decision_abstain_reason": None,
        "decision_stage_count": 1,
        "decision_json": {
            "route": "meme",
            "recommendation": "watchlist",
            "confidence": 0.72,
            "abstain_reason": None,
            "summary_zh": recommendation_summary,
            "invalidation_conditions": ["讨论迅速降温"],
            "residual_risks": risks or ["public_stream_coverage"],
            "evidence_event_ids": evidence_ids or ["event-1"],
        },
        "thesis_json": {
            "summary_zh": "社交热度正在上升。",
            "why_now_zh": "多源讨论在当前窗口同步出现。",
            "confirmation_triggers_zh": confirmations or ["新增独立作者确认"],
            "invalidation_triggers_zh": ["讨论迅速降温"],
            "top_risks": risks or ["public_stream_coverage"],
        },
        "risk_reasons_json": risks or ["public_stream_coverage"],
        "gate_reasons_json": ["trade_gate_incomplete"],
        "evidence_event_ids_json": evidence_ids or ["event-1"],
        "source_event_ids_json": source_ids or ["event-1"],
        "last_edge_events_json": edge_events or ["pulse_status_changed"],
        "pulse_version": "signal-pulse-v3-factor-snapshot",
        "created_at_ms": updated_at_ms - 60_000,
        "updated_at_ms": updated_at_ms,
    }


def _factor_snapshot(
    *,
    symbol: str | None,
    target_type: str | None,
    target_id: str | None,
    eligible_for_high_alert: bool,
    blocked_reasons: list[str],
    market_facts: dict | None,
    social_facts: dict | None,
    rank_score: float,
) -> dict:
    resolved_market_facts = {
        "market_cap_usd": 120_000,
        "liquidity_usd": 55_000,
        "holders": 800,
        **(market_facts or {}),
    }
    resolved_social_facts = {"mentions_1h": 9, "unique_authors": 4, "watched_mentions": 1, **(social_facts or {})}
    market_status = resolved_market_facts.get("market_status", "fresh")
    market_ready = "ready" if market_status == "fresh" else "partial"
    return {
        "schema_version": "token_factor_snapshot_v3_social_attention",
        "subject": {
            "symbol": symbol,
            "target_type": target_type,
            "target_id": target_id,
            "target_market_type": "dex" if target_id else None,
        },
        "market": _market_context(target_type=target_type, target_id=target_id, market_status=market_status),
        "gates": {
            "eligible_for_high_alert": eligible_for_high_alert and not blocked_reasons,
            "blocked_reasons": blocked_reasons,
            "risk_reasons": blocked_reasons,
            "max_decision": "watch" if blocked_reasons else "high_alert",
        },
        "data_health": {
            "identity": "ready" if target_id else "unresolved",
            "market": market_ready if target_id else "no_resolved_target",
            "social": "ready",
            "alpha": "ready",
        },
        "families": {
            "social_heat": {
                "raw_score": 82,
                "score": 82,
                "weight": 0.35,
                "data_health": "ready",
                "facts": resolved_social_facts,
                "factors": {"mentions_1h": {"family": "social_heat", "key": "mentions_1h"}},
            },
            "social_propagation": {
                "raw_score": 78,
                "score": 78,
                "weight": 0.3,
                "data_health": "ready",
                "facts": {"independent_authors": resolved_social_facts.get("unique_authors")},
                "factors": {"independent_authors": {"family": "social_propagation", "key": "independent_authors"}},
            },
            "semantic_catalyst": {
                "raw_score": 70,
                "score": 70,
                "weight": 0.25,
                "data_health": "ready",
                "facts": {"phase": "ignition"},
                "factors": {},
            },
            "timing_risk": {
                "raw_score": 64,
                "score": 64,
                "weight": 0.1,
                "data_health": "ready",
                "facts": {"price_change_status": resolved_market_facts.get("market_status", "fresh")},
                "factors": {},
            },
        },
        "normalization": {"status": "pending_cross_section"},
        "composite": {
            "rank_score": rank_score,
            "recommended_decision": "high_alert" if rank_score >= 70 else "watch",
            "family_scores": {
                "social_heat": 82,
                "social_propagation": 78,
                "semantic_catalyst": 70,
                "timing_risk": 64,
            },
        },
        "provenance": {"source_event_ids": ["event-1"], "computed_at_ms": 1_700_000_000_000},
    }


def _market_context(*, target_type: str | None, target_id: str | None, market_status: str | None) -> dict:
    ready = bool(target_id and market_status == "fresh")
    observation = {
        "target_type": target_type,
        "target_id": target_id,
        "source": "event_anchor",
        "provider": "okx" if ready else None,
        "pricefeed_id": None,
        "price_usd": 0.42 if ready else None,
        "price_quote": None,
        "quote_symbol": "USD" if ready else None,
        "price_basis": "usd" if ready else None,
        "market_cap_usd": 120_000 if ready else None,
        "liquidity_usd": 55_000 if ready else None,
        "holders": 800 if ready else None,
        "volume_24h_usd": None,
        "open_interest_usd": None,
        "observed_at_ms": 1_700_000_000_000 if ready else None,
        "received_at_ms": 1_700_000_000_000 if ready else None,
        "raw_payload_hash": None,
    }
    return {
        "event_anchor": observation if ready else None,
        "decision_latest": {**observation, "source": "decision_latest"} if ready else None,
        "readiness": {
            "anchor_status": "ready" if ready else "missing",
            "latest_status": "live" if ready else "missing",
            "dex_floor_status": "ready" if ready else "missing_fields",
            "missing_fields": [] if ready else ["holders", "liquidity_usd", "market_cap_usd"],
            "stale_fields": [],
        },
    }
