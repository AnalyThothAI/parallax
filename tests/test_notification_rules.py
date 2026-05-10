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


class FakeHarness:
    def __init__(self, items):
        self.items = items

    def snapshots(self, **kwargs):
        self.kwargs = kwargs
        return {"items": self.items}


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
        if kwargs.get("displayable_only"):
            rows = [
                item
                for item in rows
                if item.get("pulse_status")
                in {"trade_candidate", "token_watch", "theme_watch", "risk_rejected_high_info"}
                and item.get("verdict") != "blocked_low_information"
            ]
        limit = int(kwargs.get("limit") or len(rows))
        page_size = min(limit, self.page_size) if self.page_size else limit
        cursor = int(kwargs.get("cursor") or 0)
        page_rows = rows[cursor : cursor + page_size]
        next_cursor = str(cursor + page_size) if cursor + page_size < len(rows) else None
        return {"items": page_rows, "next_cursor": next_cursor}


def engine(*, events=None, alerts=None, asset_flow=None, snapshots=None, pulse=None, notifications=None):
    return NotificationRuleEngine(
        settings=Settings(
            ws_token="secret",
            handles=("toly",),
            notifications=notifications or NotificationsConfig(),
        ),
        evidence=FakeEvidence(events or []),
        account_alerts=FakeAccountAlerts(alerts or []),
        asset_flow=FakeAssetFlow(asset_flow or {"targets": [], "attention": []}),
        harness=FakeHarness(snapshots or []),
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
                    "decision": "driver",
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
    assert "**Heat:** 92" in hot[0].body
    assert "**Discussion quality:** 78" in hot[0].body
    assert "`0xpepe`" in hot[0].body
    assert "[GMGN](https://gmgn.ai/eth/token/0xpepe)" in hot[0].body
    assert "[X Search]" in hot[0].body
    assert hot[0].source_table == "token_radar_rows"
    assert hot[0].payload["target_id"] == "asset:eip155:1:erc20:0xpepe"
    assert hot[0].payload["social_heat_score"] == 92
    assert hot[0].payload["decision"] == "driver"
    assert hot[0].payload["score_version"] == "social_opportunity_v3"


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
                    "data_health": {"identity": "NIL", "market": "no_resolved_target"},
                }
            ],
        }
    ).evaluate(now_ms=NOW_MS)

    assert not [item for item in candidates if item.rule_id in {"hot_quality_token_5m", "quality_token_5m"}]


def test_harness_snapshot_candidate_uses_combined_score_threshold():
    candidates = engine(
        snapshots=[
            {
                "snapshot_id": "snapshot-1",
                "asset": "PEPE",
                "horizon": "6h",
                "combined_score": 0.86,
                "policy_signal": "watch",
                "source_event_id": "event-1",
                "decision_time_ms": NOW_MS - 10_000,
            },
            {
                "snapshot_id": "snapshot-2",
                "asset": "DOGE",
                "horizon": "6h",
                "combined_score": 0.3,
                "policy_signal": "watch",
                "source_event_id": "event-2",
                "decision_time_ms": NOW_MS - 10_000,
            },
        ]
    ).evaluate(now_ms=NOW_MS)

    snapshots = [item for item in candidates if item.rule_id == "harness_snapshot_high_score"]
    assert len(snapshots) == 1
    assert snapshots[0].dedup_key == "harness_snapshot_high_score:snapshot:snapshot-1"
    assert snapshots[0].symbol == "PEPE"
    assert snapshots[0].payload["combined_score"] == 0.86


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
            pulse_candidate("theme", status="theme_watch", score_band="speculative", symbol=None),
            pulse_candidate("risk", status="risk_rejected_high_info", score_band="blocked", risks=["chase_risk"]),
            pulse_candidate("blocked", status="blocked_low_information", score_band="blocked"),
        ]
    )

    candidates = [
        item for item in engine(pulse=pulse).evaluate(now_ms=NOW_MS) if item.rule_id == "signal_pulse_candidate"
    ]

    assert {item.source_table for item in candidates} == {"pulse_candidates"}
    assert {item.source_id for item in candidates} == {"trade", "watch", "theme", "risk"}
    assert {item.source_id: item.severity for item in candidates} == {
        "trade": "critical",
        "watch": "high",
        "theme": "warning",
        "risk": "warning",
    }
    assert all(item.source_id != "blocked" for item in candidates)
    assert pulse.calls[0]["displayable_only"] is True
    assert candidates[0].payload["candidate_id"] == "trade"
    assert "agent_recommendation" in candidates[0].payload
    assert "gate" in candidates[0].payload
    assert "factor_snapshot" in candidates[0].payload
    assert "top_risks" not in candidates[0].payload
    assert "confirmation_triggers_zh" not in candidates[0].payload
    assert "kind" not in candidates[0].payload


def test_signal_pulse_dedup_key_uses_candidate_status_bucket_not_signature():
    watch_row = pulse_candidate("watch", status="token_watch", updated_at_ms=NOW_MS, evidence_ids=["event-1"])
    changed_signature_row = pulse_candidate(
        "watch",
        status="token_watch",
        updated_at_ms=NOW_MS + 60_000,
        evidence_ids=["event-1", "event-2"],
    )
    trade_row = pulse_candidate("watch", status="trade_candidate", updated_at_ms=NOW_MS)

    watch = _only_pulse_notification(watch_row)
    changed_signature = _only_pulse_notification(changed_signature_row)
    trade = _only_pulse_notification(trade_row)

    assert watch.payload["notification_signature"] != changed_signature.payload["notification_signature"]
    assert watch.dedup_key == changed_signature.dedup_key
    assert watch.dedup_key == f"signal_pulse_candidate:watch:token_watch:{NOW_MS // (30 * 60_000)}"
    assert trade.dedup_key == f"signal_pulse_candidate:watch:trade_candidate:{NOW_MS // (15 * 60_000)}"


def test_signal_pulse_signature_changes_on_meaningful_state_changes():
    base = pulse_candidate("watch", status="token_watch", score_band="watch", risks=["public_stream_coverage"])

    signatures = {
        "base": _only_pulse_notification(base).payload["notification_signature"],
        "high_conviction": _only_pulse_notification({**base, "score_band": "high_conviction"}).payload[
            "notification_signature"
        ],
        "gate": _only_pulse_notification(
            pulse_candidate("watch", gate={"gate_reasons": ["manual_gate_override"]})
        ).payload["notification_signature"],
        "recommendation": _only_pulse_notification(
            pulse_candidate("watch", recommendation_summary="新增独立作者确认")
        ).payload["notification_signature"],
        "new_source": _only_pulse_notification(
            pulse_candidate("watch", evidence_ids=["event-1", "event-9"], source_ids=["event-1", "event-9"])
        ).payload["notification_signature"],
    }

    assert len(set(signatures.values())) == len(signatures)


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
    source_seed_row = {
        **pulse_candidate(
            "pulse-source-seed",
            window="5m",
            scope="all",
            status="theme_watch",
            symbol=None,
            candidate_score=80,
            radar_score={},
        ),
        "candidate_type": "source_seed",
        "target_type": None,
        "target_id": None,
    }
    pulse = FakePulse([hot_row, cold_row, low_score_row, ignored_scope_row, source_seed_row])
    notifications = NotificationsConfig(
        rules={
            "signal_pulse_candidate": {
                "enabled": True,
                "channels": ["in_app", "pushdeer"],
                "window": "5m",
                "scopes": ["all"],
                "statuses": ["token_watch", "theme_watch"],
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
        "pulse-source-seed",
    ]
    assert pulse_candidates[0].channels == ("in_app", "pushdeer")
    assert pulse_candidates[0].dedup_key.endswith(f":{NOW_MS // 120_000}")
    assert pulse.calls == [
        {
            "window": "5m",
            "scope": "all",
            "status": None,
            "limit": 50,
            "cursor": None,
            "displayable_only": True,
        }
    ]


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
    assert "- **Status:** token watch" in candidate.body
    assert "- **Gate:** clear" in candidate.body
    assert "- **Market:** mcap $250.0k · liq $55.0k · holders 600 · fresh" in candidate.body
    assert "- **Social:** 6 mentions · 4 authors · watched 1" in candidate.body
    assert "链上质量达标" in candidate.body


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
    assert [call["cursor"] for call in pulse.calls[:3]] == [None, "1", "2"]


def _only_pulse_notification(row: dict):
    candidates = engine(pulse=FakePulse([row])).evaluate(now_ms=NOW_MS)
    pulse_candidates = [item for item in candidates if item.rule_id == "signal_pulse_candidate"]
    assert len(pulse_candidates) == 1
    return pulse_candidates[0]


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
        "narrative_type": "direct_token",
        "candidate_score": candidate_score,
        "score_band": score_band,
        "radar_score_json": radar_score or {"heat": {"score": 82}},
        "factor_snapshot_json": factor_snapshot,
        "gate_json": resolved_gate,
        "agent_recommendation_json": {
            "schema_version": "pulse_recommendation_v1",
            "recommendation": "watch",
            "summary_zh": recommendation_summary,
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
        "pulse_version": "signal-pulse-v2-agent-thesis",
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
        "market_status": "fresh",
        **(market_facts or {}),
    }
    resolved_social_facts = {"mentions_1h": 9, "unique_authors": 4, "watched_mentions": 1, **(social_facts or {})}
    return {
        "schema_version": "token_factor_snapshot_v1",
        "subject": {"symbol": symbol, "target_type": target_type, "target_id": target_id},
        "families": {
            "market_quality": {"facts": resolved_market_facts},
            "social_attention": {"facts": resolved_social_facts},
            "social_quality": {"facts": {"independent_authors": resolved_social_facts.get("unique_authors")}},
        },
        "hard_gates": {
            "eligible_for_high_alert": eligible_for_high_alert and not blocked_reasons,
            "blocked_reasons": blocked_reasons,
        },
        "composite": {"rank_score": rank_score},
    }
