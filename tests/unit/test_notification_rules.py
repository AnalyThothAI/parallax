import pytest

from gmgn_twitter_intel.domains.notifications.services.notification_rules import NotificationRuleEngine
from gmgn_twitter_intel.platform.config.settings import NotificationRuleConfig, NotificationsConfig, Settings

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


class FakeAssetFlow:
    def __init__(self, data):
        self.data = data

    def asset_flow(self, **kwargs):
        self.kwargs = kwargs
        return self.data


class FakePulse:
    def __init__(self, items, *, page_size: int | None = None):
        self.items = items
        self.page_size = page_size
        self.calls = []

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


def engine(*, events=None, alerts=None, asset_flow=None, pulse=None, notifications=None):
    return NotificationRuleEngine(
        settings=Settings(
            ws_token="secret",
            handles=("toly",),
            notifications=notifications or NotificationsConfig(),
        ),
        evidence=FakeEvidence(events or []),
        account_alerts=FakeAccountAlerts(alerts or []),
        asset_flow=FakeAssetFlow(asset_flow or {"targets": [], "attention": []}),
        pulse=pulse or FakePulse([]),
    )


def radar_score(*, heat: int, quality: int, opportunity: int) -> dict:
    def block(score: int) -> dict:
        return {
            "score": score,
            "score_version": "social_opportunity_v3",
            "reasons": [],
            "risks": [],
            "contributions": [],
            "risk_caps": [],
        }

    return {
        "heat": block(heat),
        "quality": block(quality),
        "propagation": block(60),
        "tradeability": block(80),
        "timing": block(50),
        "opportunity": {
            **block(opportunity),
            "components": {
                "heat": heat,
                "quality": quality,
                "propagation": 60,
                "tradeability": 80,
                "timing": 50,
            },
        },
    }


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


def test_account_token_alert_candidate_preserves_first_seen_flags():
    candidates = engine(
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
    ).evaluate(now_ms=NOW_MS)

    candidate = next(item for item in candidates if item.rule_id == "watched_account_token_alert")
    bucket = (NOW_MS - 10_000) // 900_000
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


def test_hot_quality_token_candidate_uses_asset_flow_contract():
    candidates = engine(
        asset_flow={
            "targets": [
                {
                    "target": {
                        "target_type": "Asset",
                        "target_id": "asset:eip155:1:erc20:0xpepe",
                        "symbol": "PEPE",
                        "chain_id": "eth",
                        "address": "0xpepe",
                    },
                    "attention": {
                        "mentions_window": 5,
                        "unique_authors": 3,
                        "watched_mentions": 1,
                        "latest_seen_ms": NOW_MS,
                    },
                    "resolution": {"status": "EXACT"},
                    "score": radar_score(heat=92, quality=78, opportunity=81),
                    "decision": "investigate",
                    "factor_snapshot": _factor_snapshot(
                        symbol="PEPE",
                        target_type="Asset",
                        target_id="asset:eip155:1:erc20:0xpepe",
                        eligible_for_high_alert=True,
                        blocked_reasons=[],
                        market_facts={"market_status": "fresh"},
                        social_facts={"mentions_1h": 5, "unique_authors": 3, "watched_mentions": 1},
                        rank_score=81,
                    ),
                    "data_health": {"identity": "EXACT", "market": "ready"},
                },
                {
                    "target": {
                        "target_type": None,
                        "target_id": None,
                        "symbol": "FOMO",
                    },
                    "attention": {
                        "mentions_window": 1,
                        "unique_authors": 1,
                        "watched_mentions": 0,
                        "latest_seen_ms": NOW_MS,
                    },
                    "resolution": {"status": "NIL"},
                    "score": radar_score(heat=100, quality=70, opportunity=96),
                    "decision": "investigate",
                    "factor_snapshot": _factor_snapshot(
                        symbol="FOMO",
                        target_type=None,
                        target_id=None,
                        eligible_for_high_alert=False,
                        blocked_reasons=["identity_unresolved"],
                        market_facts={"market_status": "missing"},
                        social_facts={"mentions_1h": 1, "unique_authors": 1, "watched_mentions": 0},
                        rank_score=96,
                    ),
                    "data_health": {"identity": "NIL", "market": "no_resolved_target"},
                },
            ],
            "attention": [],
        }
    ).evaluate(now_ms=NOW_MS)

    hot = [item for item in candidates if item.rule_id == "hot_quality_token_5m"]
    assert len(hot) == 1
    assert hot[0].dedup_key == "hot_quality_token_5m:asset:eip155:1:erc20:0xpepe:1888889"
    assert hot[0].severity == "high"
    assert hot[0].symbol == "PEPE"
    assert "## $PEPE 5m heat alert" in hot[0].body
    assert "**Heat:** 82" in hot[0].body
    assert "**Discussion quality:** 70" in hot[0].body
    assert "`0xpepe`" in hot[0].body
    assert "[GMGN](https://gmgn.ai/eth/token/0xpepe)" in hot[0].body
    assert "[X Search]" in hot[0].body
    assert hot[0].source_table == "token_radar_current_rows"
    assert hot[0].payload["target_id"] == "asset:eip155:1:erc20:0xpepe"
    assert hot[0].payload["social_heat_score"] == 82
    assert hot[0].payload["decision"] == "driver"
    assert hot[0].payload["score_version"] == "token_factor_snapshot_v3_social_attention"


def test_investigate_token_radar_rows_do_not_fire_tradeable_token_alerts():
    candidates = engine(
        asset_flow={
            "targets": [],
            "attention": [
                {
                    "target": {
                        "target_id": None,
                        "symbol": "VERSA",
                    },
                    "attention": {
                        "mentions_window": 9,
                        "unique_authors": 5,
                        "watched_mentions": 2,
                        "latest_seen_ms": NOW_MS,
                    },
                    "resolution": {"status": "NIL"},
                    "score": radar_score(heat=100, quality=70, opportunity=98),
                    "decision": "investigate",
                    "factor_snapshot": _factor_snapshot(
                        symbol="VERSA",
                        target_type=None,
                        target_id=None,
                        eligible_for_high_alert=False,
                        blocked_reasons=["identity_unresolved"],
                        market_facts={"market_status": "missing"},
                        social_facts={"mentions_1h": 9, "unique_authors": 5, "watched_mentions": 2},
                        rank_score=98,
                    ),
                    "data_health": {"identity": "NIL", "market": "no_resolved_target"},
                }
            ],
        }
    ).evaluate(now_ms=NOW_MS)

    assert not [item for item in candidates if item.rule_id in {"hot_quality_token_5m", "quality_token_5m"}]


def test_disabled_rule_does_not_emit_candidates():
    notifications = NotificationsConfig(
        rules={
            "hot_quality_token_5m": NotificationRuleConfig(enabled=False),
        }
    )
    candidates = engine(
        notifications=notifications,
        asset_flow={
            "targets": [
                {
                    "target": {"target_id": "asset:eip155:1:erc20:0xpepe", "symbol": "PEPE"},
                    "attention": {
                        "mentions_window": 10,
                        "unique_authors": 5,
                        "watched_mentions": 2,
                    },
                    "resolution": {"status": "EXACT"},
                },
            ],
            "attention": [],
        },
    ).evaluate(now_ms=NOW_MS)

    assert [item for item in candidates if item.rule_id == "hot_quality_token_5m"] == []


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
    assert pulse.calls[0]["displayable_only"] is True
    trade = next(item for item in candidates if item.source_id == "trade")
    assert trade.payload["candidate_id"] == "trade"
    assert "decision" in trade.payload
    assert "agent_recommendation" not in trade.payload
    assert "gate" in trade.payload
    assert "factor_snapshot" in trade.payload
    assert "top_risks" not in trade.payload
    assert "confirmation_triggers_zh" not in trade.payload
    assert "kind" not in trade.payload


def test_signal_pulse_dedup_key_uses_in_app_and_external_identity():
    in_app_only_row = pulse_candidate("watch", status="token_watch", edge_events=["score_band_crossed"])
    external_row = pulse_candidate("watch", status="token_watch", edge_events=["pulse_status_changed"])
    notifications = _signal_pulse_notifications(channels=["in_app", "pushdeer"], statuses=["token_watch"])

    in_app_only = _only_pulse_notification(in_app_only_row, notifications=notifications)
    external = _only_pulse_notification(external_row, notifications=notifications)

    assert in_app_only.payload["in_app_signature"] == external.payload["in_app_signature"]
    assert in_app_only.payload["external_push_signature"] is None
    assert external.payload["external_push_signature"]
    assert in_app_only.dedup_key == f"signal_pulse_candidate:{in_app_only.payload['in_app_signature']}:in_app"
    external_identity = external.payload["external_push_signature"]
    assert external.dedup_key == f"signal_pulse_candidate:{external.payload['in_app_signature']}:{external_identity}"


def test_signal_pulse_signature_changes_on_stable_dimension_shifts():
    """v2 signature must change when any stable decision dimension shifts."""
    base = pulse_candidate("watch", status="token_watch", score_band="watch", risks=["public_stream_coverage"])
    gate_changed = pulse_candidate("watch")
    gate_changed["factor_snapshot_json"] = {
        **gate_changed["factor_snapshot_json"],
        "gates": {**gate_changed["factor_snapshot_json"]["gates"], "max_decision": "alert"},
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
        "base": _only_pulse_notification(base).payload["notification_signature"],
        "score_band": _only_pulse_notification({**base, "score_band": "high_conviction"}).payload[
            "notification_signature"
        ],
        "gate": _only_pulse_notification(gate_changed).payload["notification_signature"],
        "route": _only_pulse_notification(route_changed).payload["notification_signature"],
        "narrative_archetype": _only_pulse_notification(archetype_changed).payload["notification_signature"],
        "bull_strength": _only_pulse_notification(bull_changed).payload["notification_signature"],
        "has_playbook": _only_pulse_notification(playbook_added).payload["notification_signature"],
    }

    assert len(set(signatures.values())) == len(signatures)


def test_signal_pulse_signature_does_not_change_for_free_text_only_change():
    """Free-text changes (thesis_zh / narrative_thesis_zh / summary_zh) MUST NOT
    bump the signature — otherwise minor agent paraphrasing would re-page users.
    """
    base = pulse_candidate("watch", status="token_watch")
    base_sig = _only_pulse_notification(base).payload["notification_signature"]

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
    base_sig_with_bull = _only_pulse_notification(base).payload["notification_signature"]
    paraphrased_sig = _only_pulse_notification(paraphrased).payload["notification_signature"]

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
        _only_pulse_notification(base).payload["notification_signature"]
        == _only_pulse_notification(churned).payload["notification_signature"]
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
        _only_pulse_notification(base).payload["notification_signature"]
        != _only_pulse_notification(bumped).payload["notification_signature"]
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

    base_sig = _only_pulse_notification(base).payload["notification_signature"]

    assert _only_pulse_notification(raw_text_changed).payload["notification_signature"] == base_sig
    assert _only_pulse_notification(horizon_changed).payload["notification_signature"] != base_sig
    assert _only_pulse_notification(count_changed).payload["notification_signature"] != base_sig


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
        _only_pulse_notification(base).payload["notification_signature"]
        == _only_pulse_notification(unsafe_extra).payload["notification_signature"]
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
    assert pushed[0].payload["in_app_signature"]

    in_app_only = [item for item in candidates if item not in pushed]
    assert len(in_app_only) == 1
    assert in_app_only[0].channels == ("in_app",)
    assert in_app_only[0].payload["external_push_eligible"] is False
    assert in_app_only[0].payload["external_push_signature"] == external_signature
    assert in_app_only[0].payload["external_push_suppression_reason"] == "external_signature_duplicate"
    assert in_app_only[0].payload["in_app_signature"]


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

    assert base_candidate.payload["notification_signature"] != changed_candidate.payload["notification_signature"]
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
        window="5m",
        scope="all",
        candidate_score=74,
        radar_score={"heat": {"score": 72}},
    )
    cold_row = pulse_candidate(
        "pulse-cold",
        window="5m",
        scope="all",
        candidate_score=74,
        radar_score={"heat": {"score": 12}},
    )
    low_score_row = pulse_candidate(
        "pulse-low-score",
        window="5m",
        scope="all",
        candidate_score=9,
        radar_score={"heat": {"score": 75}},
    )
    ignored_scope_row = pulse_candidate(
        "pulse-ignored-scope",
        window="5m",
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
                "window": "5m",
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
        f"{pulse_candidates[0].payload['in_app_signature']}:"
        f"{pulse_candidates[0].payload['external_push_signature']}"
    )
    assert pulse.calls == [
        {
            "window": "5m",
            "scope": "all",
            "status": "token_watch",
            "limit": 50,
            "cursor": None,
            "displayable_only": True,
        }
    ]


def test_signal_pulse_candidate_rule_paginates_with_status_filter_at_source():
    class StatusAwarePulse:
        def __init__(self):
            self.calls = []

        def list_candidates(self, **kwargs):
            self.calls.append(kwargs)
            status = kwargs.get("status")
            if status == "trade_candidate":
                return {
                    "items": [pulse_candidate("trade-only", status="trade_candidate", symbol="TRADE")],
                    "next_cursor": None,
                }
            if status is None:
                return {
                    "items": [pulse_candidate(f"watch-{idx}", status="token_watch") for idx in range(100)],
                    "next_cursor": None,
                }
            return {"items": [], "next_cursor": None}

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

    assert [call["status"] for call in pulse.calls] == ["trade_candidate"]
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


def test_signal_pulse_notifications_follow_candidate_pages():
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
    token_watch_calls = [call for call in pulse.calls if call["status"] == "token_watch"]
    assert [call["cursor"] for call in token_watch_calls[:3]] == [None, "1", "2"]


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
        "decision_stage_count": 3,
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
