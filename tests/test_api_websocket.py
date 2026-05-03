from fastapi.testclient import TestClient

from gmgn_twitter_intel.api.app import create_app
from gmgn_twitter_intel.models import Author, Content, Source, TwitterEvent
from gmgn_twitter_intel.settings import Settings


def make_settings() -> Settings:
    return Settings(
        handles=("toly", "elonmusk"),
        ws_token="secret",
    )


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


def test_websocket_auth_subscribe_replay_and_live_filtering(tmp_path, monkeypatch):
    monkeypatch.setenv("GMGN_TWITTER_HOME", str(tmp_path / "app-home"))
    app = create_app(settings=make_settings(), start_collector=False)

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
            assert "enrichment" in replay

            ignored = _ingest_payload(client, make_event("event-2", "elonmusk"), is_watched=True)
            matched = _ingest_payload(client, make_event("event-3", "toly"), is_watched=True)
            client.portal.call(client.app.state.service.hub.publish, ignored)
            client.portal.call(client.app.state.service.hub.publish, matched)
            live = ws.receive_json()
            assert live["event"]["event_id"] == "event-3"


def test_websocket_can_subscribe_by_ca_for_replay_and_live_events(tmp_path, monkeypatch):
    monkeypatch.setenv("GMGN_TWITTER_HOME", str(tmp_path / "app-home"))
    app = create_app(settings=make_settings(), start_collector=False)

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


def _ingest_payload(client, event: TwitterEvent, *, is_watched: bool) -> dict:
    result = client.app.state.service.ingest.ingest_event(event, is_watched=is_watched)
    return {
        "type": "event",
        "event": event.to_dict(),
        "entities": result.entities,
        "alerts": result.alerts,
        "enrichment": None,
    }
