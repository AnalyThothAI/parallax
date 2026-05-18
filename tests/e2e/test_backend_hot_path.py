from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from gmgn_twitter_intel.app.runtime.app import create_app
from gmgn_twitter_intel.app.runtime.worker_factories.notifications import _notification_rule_engine
from gmgn_twitter_intel.domains.asset_market.runtime.event_anchor_backfill_worker import EventAnchorBackfillWorker
from gmgn_twitter_intel.domains.notifications.runtime.notification_delivery import NotificationDeliveryWorker
from gmgn_twitter_intel.domains.notifications.runtime.notification_worker import NotificationWorker
from gmgn_twitter_intel.domains.pulse_lab.runtime.pulse_candidate_worker import (
    PulseCandidateWorker,
    PulseTriggerThresholds,
)
from gmgn_twitter_intel.domains.pulse_lab.services.pulse_candidate_gate import PulseGateThresholds
from gmgn_twitter_intel.domains.token_intel.runtime.token_radar_projection_worker import TokenRadarProjectionWorker
from tests.postgres_test_utils import connect_postgres_test, prepare_postgres_database
from tests.support.db_seeds import (
    assert_count_at_least,
    first_row,
    hot_path_counts,
    promote_latest_token_radar_row_for_pulse,
)
from tests.support.fake_providers import (
    FakeDexQuoteProvider,
    FakeGmgnUpstreamClient,
    FakePulseDecisionProvider,
    RecordingWakeEmitter,
)
from tests.support.hot_path_runtime import (
    AUTHOR_HANDLE,
    EVENT_ID,
    FIXED_NOW_MS,
    MARKET_TARGET_ID,
    MARKET_TARGET_TYPE,
    SYMBOL,
    WS_TOKEN,
    auth_headers,
    backend_hot_path_settings,
)
from tests.support.provider_fixtures import load_provider_fixture


@pytest.mark.e2e
def test_complete_backend_hot_path_without_notify_dependency(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    e2e_postgres: str,
) -> None:
    monkeypatch.setenv("GMGN_TEST_POSTGRES_DSN", e2e_postgres)
    prepare_postgres_database()
    settings = backend_hot_path_settings(tmp_path)
    app = create_app(settings=settings, start_collector=False)
    frame = load_provider_fixture("gmgn_public_tw_complete.json")

    with TestClient(app) as client:
        runtime = client.app.state.service
        upstream = FakeGmgnUpstreamClient([frame], runtime.collector.handle_frame, received_at_ms=FIXED_NOW_MS)

        client.portal.call(upstream.run)
        _assert_counts(
            {
                "raw_frames": 1,
                "events": 1,
                "token_intents": 1,
                "token_intent_resolutions": 1,
                "enriched_events": 1,
                "event_anchor_jobs": 1,
            }
        )

        wake = RecordingWakeEmitter()
        backfill_result = asyncio.run(
            EventAnchorBackfillWorker(
                pool_bundle=runtime.db,
                providers=SimpleNamespace(
                    dex_quote_market=FakeDexQuoteProvider(observed_at_ms=FIXED_NOW_MS + 500),
                    message_cex_market=None,
                ),
                wake_emitter=wake,
                batch_size=10,
                concurrency=2,
                min_age_ms=0,
                max_anchor_lag_ms=30 * 24 * 60 * 60 * 1000,
                clock=_wall_now_ms,
            ).run_once()
        )
        assert backfill_result.processed == 1
        assert wake.market_tick_writes == [(MARKET_TARGET_TYPE, MARKET_TARGET_ID)]
        _assert_counts({"market_ticks": 1, "ready_enriched_events": 1})

        radar_result = asyncio.run(
            TokenRadarProjectionWorker(
                name="token_radar_projection",
                settings=runtime.settings.workers.token_radar_projection,
                db=runtime.db,
                telemetry=runtime.telemetry,
                wake_bus=None,
            ).run_once(now_ms=FIXED_NOW_MS + 2_000)
        )
        assert radar_result.notes["rows_written"] >= 1
        _assert_counts({"token_radar_rows": 1})
        _promote_single_fixture_radar_row_for_pulse()

        pulse_client = FakePulseDecisionProvider()
        pulse_result = asyncio.run(
            PulseCandidateWorker(
                name="pulse_candidate",
                settings=runtime.settings.workers.pulse_candidate,
                db=runtime.db,
                telemetry=runtime.telemetry,
                decision_client=pulse_client,
                trigger_thresholds=PulseTriggerThresholds(min_rank_score=0),
                gate_thresholds=PulseGateThresholds(
                    trade_candidate_min=0,
                    token_watch_min=0,
                    high_info_rejection_min=0,
                    high_conviction_min=0,
                ),
            ).run_once(now_ms=FIXED_NOW_MS + 3_000)
        )
        assert pulse_result.notes["scan"]["asset_enqueued"] >= 1
        assert pulse_result.notes["process"]["processed"] >= 1
        assert pulse_client.contexts, _pulse_debug()
        _assert_counts({"pulse_agent_jobs": 1, "pulse_agent_runs": 1, "pulse_candidates": 1})

        notification_worker = NotificationWorker(
            name="notification_rule",
            settings=runtime.settings.workers.notification_rule,
            db=runtime.db,
            telemetry=runtime.telemetry,
            rule_engine_factory=lambda repos: _notification_rule_engine(runtime.settings, repos),
            publisher=runtime.hub,
            delivery_channels=runtime.settings.notifications.channels,
            delivery_max_attempts=runtime.settings.workers.notification_delivery.max_attempts,
        )
        notification_result = asyncio.run(notification_worker.run_once(now_ms=FIXED_NOW_MS + 4_000))
        assert notification_result.processed == 1
        _assert_counts({"notifications": 1, "notification_deliveries": 1})

        delivery_result = asyncio.run(
            NotificationDeliveryWorker(
                name="notification_delivery",
                settings=runtime.settings.workers.notification_delivery,
                db=runtime.db,
                telemetry=runtime.telemetry,
                channels=runtime.settings.notifications.channels,
            ).run_once(now_ms=_wall_now_ms())
        )
        assert delivery_result.processed == 1
        _assert_counts({"delivered_notifications": 1})

        _assert_http_surfaces(client)
        _assert_websocket_surfaces(client, runtime)


def _assert_counts(expected_minimums: dict[str, int]) -> dict[str, int]:
    conn = connect_postgres_test(read_only=False)
    try:
        counts = hot_path_counts(conn, event_id=EVENT_ID)
    finally:
        conn.close()
    for name, minimum in expected_minimums.items():
        assert_count_at_least(counts, name, minimum)
    return counts


def _promote_single_fixture_radar_row_for_pulse() -> None:
    conn = connect_postgres_test(read_only=False)
    try:
        promote_latest_token_radar_row_for_pulse(conn, target_id=MARKET_TARGET_ID)
    finally:
        conn.close()


def _pulse_debug() -> dict[str, Any]:
    conn = connect_postgres_test(read_only=False)
    try:
        runs = conn.execute(
            """
            SELECT decision_route, outcome, request_json, response_json, error
            FROM pulse_agent_runs
            ORDER BY started_at_ms DESC
            LIMIT 3
            """
        ).fetchall()
        candidates = conn.execute(
            """
            SELECT pulse_status, decision_recommendation, gate_reasons_json, risk_reasons_json
            FROM pulse_candidates
            ORDER BY updated_at_ms DESC
            LIMIT 3
            """
        ).fetchall()
        return {"runs": [dict(row) for row in runs], "candidates": [dict(row) for row in candidates]}
    finally:
        conn.close()


def _assert_http_surfaces(client: TestClient) -> None:
    ready = client.get("/readyz")
    assert ready.status_code == 200, ready.text
    assert ready.json()["ok"] is True

    recent = client.get("/api/recent", params={"limit": 10}, headers=auth_headers())
    assert recent.status_code == 200, recent.text
    assert EVENT_ID in json.dumps(recent.json(), default=str)

    radar = client.get("/api/token-radar", params={"window": "1h", "scope": "all", "limit": 10}, headers=auth_headers())
    assert radar.status_code == 200, radar.text
    radar_text = json.dumps(radar.json(), default=str)
    assert SYMBOL in radar_text

    pulse = client.get(
        "/api/signal-lab/pulse",
        params={"window": "1h", "scope": "all", "status": "trade_candidate", "limit": 10},
        headers=auth_headers(),
    )
    assert pulse.status_code == 200, pulse.text
    pulse_text = json.dumps(pulse.json(), default=str)
    assert "trade_candidate" in pulse_text
    assert SYMBOL in pulse_text

    notifications = client.get("/api/notifications", params={"limit": 10}, headers=auth_headers())
    assert notifications.status_code == 200, notifications.text
    assert "signal_pulse_candidate" in json.dumps(notifications.json(), default=str)


def _assert_websocket_surfaces(client: TestClient, runtime: Any) -> None:
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "auth", "token": WS_TOKEN})
        assert ws.receive_json()["type"] == "ready"
        ws.send_json({"type": "subscribe", "handles": [AUTHOR_HANDLE], "replay": 10})
        replay = _receive_matching(ws, lambda msg: msg.get("type") == "event")
        assert replay["event"]["event_id"] == EVENT_ID

    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "auth", "token": WS_TOKEN})
        assert ws.receive_json()["type"] == "ready"
        ws.send_json(
            {
                "type": "subscribe",
                "market_targets": [{"target_type": MARKET_TARGET_TYPE, "target_id": MARKET_TARGET_ID}],
                "replay": 0,
            }
        )
        client.portal.call(
            runtime.hub.publish,
            {
                "type": "live_market_update",
                "target_type": MARKET_TARGET_TYPE,
                "target_id": MARKET_TARGET_ID,
                "price_usd": 0.129,
            },
        )
        market_update = ws.receive_json()
        assert market_update["type"] == "live_market_update"
        assert market_update["target_id"] == MARKET_TARGET_ID

    conn = connect_postgres_test(read_only=False)
    try:
        notification = first_row(
            conn,
            """
            SELECT notification_id, rule_id, title
            FROM notifications
            WHERE rule_id = 'signal_pulse_candidate'
            ORDER BY created_at_ms DESC
            LIMIT 1
            """,
        )
    finally:
        conn.close()

    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "auth", "token": WS_TOKEN})
        assert ws.receive_json()["type"] == "ready"
        ws.send_json({"type": "subscribe", "notifications": True, "replay": 0})
        client.portal.call(
            runtime.hub.publish,
            {"type": "notification", "notification": notification},
        )
        pushed = ws.receive_json()
        assert pushed["type"] == "notification"
        assert pushed["notification"]["rule_id"] == "signal_pulse_candidate"


def _receive_matching(ws: Any, predicate: Any) -> dict[str, Any]:
    for _ in range(10):
        message = ws.receive_json()
        if predicate(message):
            return message
    raise AssertionError("websocket did not receive matching message")


def _wall_now_ms() -> int:
    return int(time.time() * 1000)
