from gmgn_twitter_intel.pipeline.notification_rules import NotificationRuleEngine
from gmgn_twitter_intel.settings import NotificationRuleConfig, NotificationsConfig, Settings

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


def engine(*, events=None, alerts=None, asset_flow=None, snapshots=None, notifications=None):
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
    )


def radar_score(*, heat: int, quality: int, opportunity: int) -> dict:
    def block(score: int) -> dict:
        return {
            "score": score,
            "score_version": "token_radar_v4",
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
    assert candidate.dedup_key == "watched_account_activity:event:event-1"
    assert candidate.severity == "info"
    assert candidate.entity_type == "account"
    assert candidate.entity_key == "account:toly"
    assert candidate.author_handle == "toly"
    assert candidate.source_table == "events"
    assert candidate.source_id == "event-1"
    assert candidate.payload["event_id"] == "event-1"


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
    assert candidate.dedup_key == "watched_account_token_alert:alert:alert-1"
    assert candidate.severity == "warning"
    assert candidate.entity_type == "token"
    assert candidate.symbol == "PEPE"
    assert candidate.payload["is_first_seen_global"] is True


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
    assert hot[0].payload["score_version"] == "token_radar_v4"


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
