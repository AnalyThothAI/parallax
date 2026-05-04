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


def make_event(
    event_id: str,
    handle: str = "toly",
    text: str | None = None,
    received_at_ms: int | None = None,
) -> TwitterEvent:
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
        received_at_ms=received_at_ms if received_at_ms is not None else int(time.time() * 1000),
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
    received_at_ms: int | None = None,
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
        make_event(event_id, handle=handle, text=text or f"${symbol} launch", received_at_ms=received_at_ms),
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


def test_api_status_exposes_market_observation_backlog(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        event = make_token_event(
            "event-market-observation",
            symbol="PEPE",
            address=PEPE,
            text="$PEPE payload",
        )
        client.app.state.service.ingest.ingest_event(event, is_watched=True)

        response = client.get("/api/status", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 200
    market_observations = response.json()["data"]["market_observations"]
    assert market_observations["worker_running"] is True
    assert set(market_observations) >= {
        "pending",
        "running",
        "ready",
        "cached",
        "provider_not_configured",
        "provider_error",
        "rate_limited",
        "dead",
        "worker_running",
    }
    assert (
        market_observations["pending"]
        + market_observations["provider_not_configured"]
        + market_observations["running"]
    ) >= 1


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
    assert "token_attributions" in recent.json()["data"]["items"][0]

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


def test_api_token_posts_returns_full_post_pages_and_requires_identity(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        base_ms = int(time.time() * 1000)
        for index in range(3):
            event = make_token_event(
                f"event-pepe-post-{index}",
                symbol="PEPE",
                address=PEPE,
                handle=f"voice{index}",
                text=f"$PEPE post {index}",
                received_at_ms=base_ms - index * 1_000,
            )
            client.app.state.service.ingest.ingest_event(event, is_watched=index == 0)

        token_flow = client.get(
            "/api/token-flow",
            params={"window": "5m", "limit": 5, "scope": "all"},
            headers={"Authorization": "Bearer secret"},
        ).json()["data"]["items"][0]
        token_id = token_flow["identity"]["token_id"]

        missing = client.get("/api/token-posts?window=5m", headers={"Authorization": "Bearer secret"})
        first_page = client.get(
            "/api/token-posts",
            params={"token_id": token_id, "window": "5m", "scope": "all", "limit": 2},
            headers={"Authorization": "Bearer secret"},
        )
        second_page = client.get(
            "/api/token-posts",
            params={
                "token_id": token_id,
                "window": "5m",
                "scope": "all",
                "limit": 2,
                "cursor": first_page.json()["data"]["next_cursor"],
            },
            headers={"Authorization": "Bearer secret"},
        )
        ca_page = client.get(
            "/api/token-posts",
            params={"chain": "eth", "address": PEPE, "window": "5m", "scope": "all", "limit": 10},
            headers={"Authorization": "Bearer secret"},
        )

    assert missing.status_code == 400
    assert missing.json() == {"ok": False, "error": "missing_token_identity"}
    assert first_page.status_code == 200
    first_body = first_page.json()["data"]
    assert first_body["total_count"] == 3
    assert first_body["returned_count"] == 2
    assert first_body["has_more"] is True
    assert first_body["query"]["token_id"] == token_id
    assert first_body["items"][0]["post_quality"]["score_version"] == "post_quality_v1"
    assert first_body["items"][0]["post_quality"]["contributions"]
    assert "score" not in first_body["items"][0]
    assert second_page.status_code == 200
    assert second_page.json()["data"]["returned_count"] == 1
    assert ca_page.status_code == 200
    assert ca_page.json()["data"]["total_count"] == 3
    assert ca_page.json()["data"]["query"]["chain"] == "eth"


def test_api_token_posts_rejects_malformed_cursor(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        response = client.get(
            "/api/token-posts",
            params={"token_id": f"token:eth:{PEPE}", "window": "5m", "cursor": "abcde"},
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 400
    assert response.json() == {"ok": False, "error": "invalid_cursor"}


def test_api_token_social_timeline_returns_buckets_authors_and_posts(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        base_ms = int(time.time() * 1000)
        for index in range(3):
            event = make_token_event(
                f"event-pepe-timeline-{index}",
                symbol="PEPE",
                address=PEPE,
                handle=f"voice{index}",
                text=f"$PEPE timeline mcap liquidity {index}",
                received_at_ms=base_ms - index * 30_000,
            )
            client.app.state.service.ingest.ingest_event(event, is_watched=index == 0)

        token_flow = client.get(
            "/api/token-flow",
            params={"window": "5m", "limit": 5, "scope": "all"},
            headers={"Authorization": "Bearer secret"},
        ).json()["data"]["items"][0]
        token_id = token_flow["identity"]["token_id"]

        missing = client.get("/api/token-social-timeline?window=5m", headers={"Authorization": "Bearer secret"})
        response = client.get(
            "/api/token-social-timeline",
            params={"token_id": token_id, "window": "5m", "bucket": "1m", "scope": "all", "limit": 2},
            headers={"Authorization": "Bearer secret"},
        )

    assert missing.status_code == 400
    assert missing.json() == {"ok": False, "error": "missing_token_identity"}
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["summary"]["posts"] == 3
    assert data["buckets"]
    assert data["authors"]
    assert data["returned_count"] == 2
    assert data["has_more"] is True


def test_api_token_posts_rejects_invalid_chain_address_identity(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        response = client.get(
            "/api/token-posts",
            params={"chain": "eth", "address": "not-a-ca", "window": "5m"},
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 400
    assert response.json() == {"ok": False, "error": "invalid_token_identity"}


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
    assert token_item["propagation"]["score"] > 0
    assert token_item["opportunity"]["decision"] in {"watch", "driver"}
    assert "signal" not in token_item


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
