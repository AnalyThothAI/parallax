from fastapi.testclient import TestClient

from gmgn_twitter_intel.api.app import create_app
from gmgn_twitter_intel.models import Author, Content, Source, TwitterEvent
from gmgn_twitter_intel.pipeline.harness_snapshot_builder import HarnessSnapshotBuilder
from gmgn_twitter_intel.pipeline.social_event_extraction import AnchorTerm, SocialEventExtraction, SocialTokenCandidate
from gmgn_twitter_intel.settings import Settings


def make_settings(tmp_path) -> Settings:
    settings = Settings(
        handles=("toly", "elonmusk"),
        ws_token="secret",
    )
    settings.set_config_dir(tmp_path / "app-home")
    return settings


PEPE = "0x6982508145454ce325ddbe47a25d4ec3d2311933"


def make_event(event_id: str, handle: str, text: str | None = None) -> TwitterEvent:
    return TwitterEvent(
        event_id=event_id,
        source=Source(
            provider="gmgn",
            transport="direct_ws",
            coverage="public_stream",
            channel="twitter_monitor_basic",
        ),
        action="tweet",
        original_action=None,
        tweet_id=event_id,
        internal_id=event_id,
        timestamp=1,
        received_at_ms=1000,
        author=Author(handle=handle, name=handle, avatar=None, followers=None, tags=[]),
        content=Content(text=text or f"{handle} text", media=[]),
        reference=None,
        unfollow_target=None,
        avatar_change=None,
        bio_change=None,
        matched_handles=[handle],
        raw=None,
    )


def test_websocket_auth_subscribe_replay_and_live_filtering(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        client.app.state.service.ingest.ingest_event(make_event("event-1", "toly"), is_watched=True)

        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "auth", "token": "secret"})
            assert ws.receive_json()["type"] == "ready"

            ws.send_json({"type": "subscribe", "handles": ["toly"], "replay": 5})
            replay = ws.receive_json()
            assert replay["type"] == "event"
            assert replay["event"]["event_id"] == "event-1"
            assert "entities" in replay
            assert "alerts" in replay
            assert "token_attributions" in replay
            assert "harness" in replay

            ignored = _ingest_payload(client, make_event("event-2", "elonmusk"), is_watched=True)
            matched = _ingest_payload(client, make_event("event-3", "toly"), is_watched=True)
            client.portal.call(client.app.state.service.hub.publish, ignored)
            client.portal.call(client.app.state.service.hub.publish, matched)
            live = ws.receive_json()
            assert live["event"]["event_id"] == "event-3"


def test_websocket_can_subscribe_by_ca_for_replay_and_live_events(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        replay_event = make_event("event-ca-replay", "toly", text=f"$PEPE replay {PEPE}")
        client.app.state.service.ingest.ingest_event(replay_event, is_watched=True)

        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "auth", "token": "secret"})
            assert ws.receive_json()["type"] == "ready"

            ws.send_json({"type": "subscribe", "cas": [PEPE], "replay": 5})
            replay = ws.receive_json()
            assert replay["type"] == "event"
            assert replay["event"]["event_id"] == "event-ca-replay"
            assert replay["entities"][0]["entity_type"] in {"symbol", "ca"}

            ignored = make_event("event-ignore", "toly", text="no token")
            matched = make_event("event-ca-live", "elonmusk", text=f"$PEPE live {PEPE}")
            ignored_payload = _ingest_payload(client, ignored, is_watched=True)
            matched_payload = _ingest_payload(client, matched, is_watched=True)
            client.portal.call(client.app.state.service.hub.publish, ignored_payload)
            client.portal.call(client.app.state.service.hub.publish, matched_payload)
            live = ws.receive_json()
            assert live["event"]["event_id"] == "event-ca-live"


def test_websocket_replay_includes_harness_state_for_social_event(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        event = make_event("seed-event", "toly", text="Grok DOG is getting scary good")
        client.app.state.service.ingest.ingest_event(event, is_watched=True)
        HarnessSnapshotBuilder(client.app.state.service.harness).materialize(
            event=event.to_dict(),
            extraction=SocialEventExtraction(
                is_signal_event=True,
                event_type="meme_phrase_seed",
                source_action="posted",
                subject="Grok DOG attention",
                direction_hint="attention_positive",
                attention_mechanism="meme_phrase",
                impact_hint=0.8,
                semantic_novelty_hint=0.75,
                confidence=0.9,
                anchor_terms=[AnchorTerm(term="Grok", role="meme_phrase", evidence="Grok")],
                token_candidates=[
                    SocialTokenCandidate(
                        symbol="DOG",
                        project_name=None,
                        chain="eth",
                        address=None,
                        evidence="DOG",
                        confidence=0.9,
                    )
                ],
                semantic_risks=["public_stream_coverage"],
                summary_zh="Grok DOG 形成 harness 注意力事件。",
                raw_response={"ok": True},
            ),
            run_id="run-seed",
            model_version="fake-model",
        )

        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "auth", "token": "secret"})
            assert ws.receive_json()["type"] == "ready"
            ws.send_json({"type": "subscribe", "handles": ["toly"], "replay": 5})
            replay = ws.receive_json()

    assert replay["type"] == "event"
    assert replay["harness"]["social_event"]["event_id"] == "seed-event"
    assert replay["harness"]["attention_seed"]["event_id"] == "seed-event"
    assert replay["harness"]["snapshots"][0]["asset"] == "DOG"


def test_websocket_routes_harness_updates_by_seed_event_handle(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        event = make_event("seed-event", "toly", text="Grok is getting scary good")
        client.app.state.service.ingest.ingest_event(event, is_watched=True)

        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "auth", "token": "secret"})
            assert ws.receive_json()["type"] == "ready"
            ws.send_json({"type": "subscribe", "handles": ["toly"], "replay": 0})

            client.portal.call(
                client.app.state.service.hub.publish,
                {
                    "type": "harness_update",
                    "event": event.to_dict(),
                    "social_event": {"event_id": "seed-event", "event_type": "meme_phrase_seed"},
                    "seed": {"seed_id": "seed-1", "event_id": "seed-event"},
                    "snapshots": [{"asset": "DOG"}],
                },
            )
            update = ws.receive_json()

    assert update["type"] == "harness_update"
    assert update["seed"]["seed_id"] == "seed-1"


def test_websocket_routes_live_notifications_when_subscribed(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        notification = client.app.state.service.notifications.insert_notification(
            dedup_key="activity:event-1",
            rule_id="watched_account_activity",
            severity="info",
            title="activity",
            body="new post",
            entity_type="account",
            entity_key="account:toly",
            author_handle="toly",
            event_id="event-1",
            source_table="events",
            source_id="event-1",
            occurrence_at_ms=1_700_000_000_000,
            payload={"event_id": "event-1"},
            channels=["in_app"],
        )
        assert notification is not None

        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "auth", "token": "secret"})
            assert ws.receive_json()["type"] == "ready"
            ws.send_json({"type": "subscribe", "handles": ["elonmusk"], "notifications": True, "replay": 0})

            client.portal.call(
                client.app.state.service.hub.publish,
                {"type": "notification", "notification": notification},
            )
            message = ws.receive_json()

    assert message["type"] == "notification"
    assert message["notification"]["notification_id"] == notification["notification_id"]


def _ingest_payload(client, event: TwitterEvent, *, is_watched: bool) -> dict:
    result = client.app.state.service.ingest.ingest_event(event, is_watched=is_watched)
    return {
        "type": "event",
        "event": event.to_dict(),
        "entities": result.entities,
        "alerts": result.alerts,
        "token_attributions": result.token_attributions,
        "harness": None,
    }
