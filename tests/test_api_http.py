import time
from dataclasses import replace

from fastapi.testclient import TestClient

from gmgn_twitter_intel.api.app import create_app
from gmgn_twitter_intel.collector.gmgn_token_payload import parse_gmgn_token_payload
from gmgn_twitter_intel.models import Author, Content, Source, TwitterEvent
from gmgn_twitter_intel.pipeline.narrative_token_linker import NarrativeTokenLinker
from gmgn_twitter_intel.settings import Settings

PEPE = "0x6982508145454ce325ddbe47a25d4ec3d2311933"


def make_settings(tmp_path) -> Settings:
    settings = Settings(
        handles=("toly", "elonmusk"),
        ws_token="secret",
    )
    settings.set_config_dir(tmp_path / "app-home")
    return settings


def make_event(event_id: str, handle: str = "toly", text: str | None = None) -> TwitterEvent:
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
        received_at_ms=int(time.time() * 1000),
        author=Author(handle=handle, name=handle, avatar=None, followers=100, tags=[]),
        content=Content(text=text or f"{handle} text", media=[]),
        reference=None,
        unfollow_target=None,
        avatar_change=None,
        bio_change=None,
        matched_handles=[handle],
        raw={"id": event_id},
    )


def make_token_event(
    event_id: str,
    *,
    symbol: str,
    address: str,
    handle: str = "toly",
    text: str | None = None,
) -> TwitterEvent:
    snapshot = parse_gmgn_token_payload(
        {
            "tt": "ca",
            "t": {
                "a": address,
                "c": "eth",
                "mc": "60490.341996",
                "p": "1.0",
                "s": symbol,
            },
        }
    )
    return replace(
        make_event(event_id, handle=handle, text=text or f"${symbol} launch"),
        source=Source(
            provider="gmgn",
            transport="direct_ws",
            coverage="public_stream",
            channel="twitter_monitor_token",
        ),
        token_snapshot=snapshot,
    )


def test_api_bootstrap_exposes_frontend_runtime_config_without_token(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        response = client.get("/api/bootstrap")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"] == {
        "ws_token": "secret",
        "handles": ["toly", "elonmusk"],
        "replay_limit": 100,
    }


def test_api_rejects_protected_reads_without_token(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        response = client.get("/api/recent")

    assert response.status_code == 401
    assert response.json() == {"ok": False, "error": "unauthorized"}


def test_api_exposes_recent_search_and_signal_read_models(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        event = make_event("event-1", text=f"$PEPE ignition {PEPE}")
        client.app.state.service.ingest.ingest_event(event, is_watched=True)

        headers = {"Authorization": "Bearer secret"}
        recent = client.get("/api/recent?limit=5", headers=headers)
        search = client.get("/api/search", params={"q": "$PEPE", "limit": 5}, headers=headers)
        token_flow = client.get("/api/token-flow?window=5m&limit=5", headers=headers)
        account_alerts = client.get("/api/account-alerts?window=24h&limit=5", headers=headers)

    assert recent.status_code == 200
    assert recent.json()["data"]["events"][0]["event_id"] == "event-1"

    assert search.status_code == 200
    assert search.json()["data"]["items"][0]["event"]["event_id"] == "event-1"

    assert token_flow.status_code == 200
    assert token_flow.json()["data"]["items"] == []

    assert account_alerts.status_code == 200
    assert account_alerts.json()["data"]["items"][0]["event_id"] == "event-1"
    assert account_alerts.json()["data"]["items"][0]["token_resolution_status"] == "unresolved_chain_ca"


def test_api_token_flow_scope_filters_watched_mentions(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        watched_event = make_token_event(
            "event-watched",
            symbol="PEPE",
            address="0x6982508145454ce325ddbe47a25d4ec3d2311933",
            text="$PEPE watched",
        )
        public_event = make_token_event(
            "event-public",
            symbol="BONK",
            address="0x44b28991b167582f18ba0259e0173176ca125505",
            handle="anon",
            text="$BONK public",
        )
        client.app.state.service.ingest.ingest_event(watched_event, is_watched=True)
        client.app.state.service.ingest.ingest_event(public_event, is_watched=False)

        headers = {"Authorization": "Bearer secret"}
        all_flow = client.get("/api/token-flow", params={"window": "5m", "scope": "all"}, headers=headers)
        watched_flow = client.get("/api/token-flow", params={"window": "5m", "scope": "matched"}, headers=headers)

    assert all_flow.status_code == 200
    assert {item["identity"]["symbol"] for item in all_flow.json()["data"]["items"]} == {"PEPE", "BONK"}

    assert watched_flow.status_code == 200
    assert watched_flow.json()["data"]["scope"] == "matched"
    assert [item["identity"]["symbol"] for item in watched_flow.json()["data"]["items"]] == ["PEPE"]


def test_api_token_flow_exposes_seed_linked_watch_status(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        seed_event = make_event("seed-event", text="AI agent narrative is accelerating")
        public_event = make_token_event(
            "public-token",
            symbol="GROK",
            address="0x44b28991b167582f18ba0259e0173176ca125505",
            handle="anon",
            text="$GROK AI agent momentum",
        )
        client.app.state.service.ingest.ingest_event(seed_event, is_watched=True)
        client.app.state.service.ingest.ingest_event(public_event, is_watched=False)
        seed = client.app.state.service.enrichment.upsert_narrative_seed(
            event_id="seed-event",
            narrative_label="ai_agent",
            seed_family="ai_agent",
            seed_terms=["ai agent"],
            market_interpretation="Market may look for AI-agent tokens.",
            stance="bullish",
            intent="market_commentary",
            confidence=0.9,
            source_weight=0.6,
            novelty_status="new_global",
            received_at_ms=seed_event.received_at_ms,
            author_handle="toly",
            evidence="AI agent narrative is accelerating",
            summary="Watched account discussed AI agents.",
        )
        NarrativeTokenLinker(
            evidence=client.app.state.service.evidence,
            signals=client.app.state.service.signals,
            enrichment=client.app.state.service.enrichment,
            tokens=client.app.state.service.tokens,
        ).link_seed(seed=seed, window="1h")

        response = client.get(
            "/api/token-flow",
            params={"window": "1h", "limit": 5, "scope": "all"},
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 200
    token_item = response.json()["data"]["items"][0]
    assert token_item["identity"]["symbol"] == "GROK"
    assert token_item["watch"]["status"] == "seed_linked"
    assert token_item["watch"]["seed_link_count"] == 1
    assert token_item["watch"]["top_seed"]["seed_id"] == seed["seed_id"]


def test_api_status_exposes_operational_state(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        response = client.get("/api/status", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["collector"]["frames_received"] == 0
    assert body["data"]["handles"] == ["toly", "elonmusk"]
    assert body["data"]["enrichment"]["llm_configured"] is False


def test_api_exposes_narrative_link_read_models(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        event = make_event("seed-1", text="$GROK Grok is getting scary good")
        client.app.state.service.ingest.ingest_event(event, is_watched=True)
        seed = client.app.state.service.enrichment.upsert_narrative_seed(
            event_id="seed-1",
            narrative_label="ai_agent_grok",
            seed_family="ai_agent",
            seed_terms=["grok"],
            market_interpretation="Market may look for Grok tokens.",
            stance="bullish",
            intent="technical_commentary",
            confidence=0.9,
            source_weight=0.6,
            novelty_status="new_global",
            received_at_ms=event.received_at_ms,
            author_handle="toly",
            evidence="Grok is getting scary good",
            summary="Watched account discussed Grok.",
        )
        NarrativeTokenLinker(
            evidence=client.app.state.service.evidence,
            signals=client.app.state.service.signals,
            enrichment=client.app.state.service.enrichment,
            tokens=client.app.state.service.tokens,
        ).link_seed(seed=seed, window="1h")

        headers = {"Authorization": "Bearer secret"}
        seeds = client.get("/api/narrative-seeds?window=24h&limit=5", headers=headers)
        flow = client.get(
            "/api/narrative-token-flow",
            params={"seed_id": seed["seed_id"], "window": "1h", "limit": 5},
            headers=headers,
        )
        unsupported_flow_window = client.get(
            "/api/narrative-token-flow",
            params={"seed_id": seed["seed_id"], "window": "1m", "limit": 5},
            headers=headers,
        )
        frontier = client.get("/api/attention-frontier?window=1h&limit=5", headers=headers)

    assert seeds.status_code == 200
    assert seeds.json()["data"]["items"][0]["seed"]["narrative_label"] == "ai_agent_grok"

    assert flow.status_code == 200
    assert flow.json()["data"]["seed"]["seed_id"] == seed["seed_id"]
    assert flow.json()["data"]["links"][0]["identity"]["symbol"] == "GROK"
    assert unsupported_flow_window.status_code == 200
    assert unsupported_flow_window.json()["data"]["window"] == "1h"

    assert frontier.status_code == 200
    assert frontier.json()["data"]["items"][0]["seed"]["narrative_label"] == "ai_agent_grok"
