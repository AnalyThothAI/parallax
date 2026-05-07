import time
from dataclasses import replace

from fastapi.testclient import TestClient

from gmgn_twitter_intel.api.app import create_app
from gmgn_twitter_intel.collector.gmgn_token_payload import parse_gmgn_token_payload
from gmgn_twitter_intel.models import Author, Content, Source, TwitterEvent
from gmgn_twitter_intel.pipeline.harness_snapshot_builder import HarnessSnapshotBuilder
from gmgn_twitter_intel.pipeline.social_event_extraction import AnchorTerm, SocialEventExtraction, SocialTokenCandidate
from gmgn_twitter_intel.settings import Settings
from tests.postgres_test_utils import postgres_settings_storage, prepare_postgres_database

PEPE = "0x6982508145454ce325ddbe47a25d4ec3d2311933"


def make_settings(tmp_path) -> Settings:
    prepare_postgres_database()
    settings = Settings(
        handles=("toly", "elonmusk"),
        ws_token="secret",
        storage=postgres_settings_storage(),
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


def test_api_removed_token_signal_reads_are_not_registered(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        snapshots = client.get("/api/token-signal-snapshots", headers={"Authorization": "Bearer secret"})
        outcomes = client.get("/api/token-signal-outcomes", headers={"Authorization": "Bearer secret"})
        evaluations = client.get("/api/token-signal-evaluations", headers={"Authorization": "Bearer secret"})

    assert snapshots.status_code == 404
    assert outcomes.status_code == 404
    assert evaluations.status_code == 404


def test_api_status_exposes_asset_market_sync_status(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        response = client.get("/api/status", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 200
    asset_market_sync = response.json()["data"]["asset_market_sync"]
    assert set(asset_market_sync) >= {"worker_running", "last_run_at_ms", "last_result", "providers"}
    token_discovery = response.json()["data"]["token_discovery"]
    assert set(token_discovery) >= {"worker_running", "last_run_at_ms", "last_result", "last_error"}
    token_radar_projection = response.json()["data"]["token_radar_projection"]
    assert set(token_radar_projection) >= {"worker_running", "last_run_at_ms", "last_result", "last_error"}


def test_api_exposes_recent_search_and_signal_read_models(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        event = make_token_event("event-1", symbol="PEPE", address=PEPE, text=f"$PEPE ignition {PEPE}")
        client.app.state.service.ingest.ingest_event(event, is_watched=True)
        HarnessSnapshotBuilder(
            client.app.state.service.harness,
            tokens=client.app.state.service.tokens,
        ).materialize(
            event=event.to_dict(),
            extraction=SocialEventExtraction(
                is_signal_event=True,
                event_type="meme_phrase_seed",
                source_action="posted",
                subject="PEPE ignition",
                direction_hint="attention_positive",
                attention_mechanism="direct_token_mention",
                impact_hint=0.75,
                semantic_novelty_hint=0.7,
                confidence=0.9,
                anchor_terms=[AnchorTerm(term="$PEPE", role="asset", evidence="$PEPE")],
                token_candidates=[
                    SocialTokenCandidate(
                        symbol="PEPE",
                        project_name=None,
                        chain="eth",
                        address=PEPE,
                        evidence="$PEPE",
                        confidence=0.9,
                    )
                ],
                semantic_risks=["public_stream_coverage"],
                summary_zh="PEPE ignition 形成 harness 事件。",
                raw_response={"ok": True},
            ),
            run_id="run-event-1",
            model_version="fake-model",
        )

        headers = {"Authorization": "Bearer secret"}
        recent = client.get("/api/recent?limit=5", headers=headers)
        search = client.get("/api/search", params={"q": "$PEPE", "limit": 5}, headers=headers)
        asset_flow = client.get("/api/token-radar?window=5m&limit=5", headers=headers)
        account_alerts = client.get("/api/account-alerts?window=24h&limit=5", headers=headers)

    assert recent.status_code == 200
    assert recent.json()["data"]["events"][0]["event_id"] == "event-1"
    assert "token_intents" in recent.json()["data"]["items"][0]
    assert "token_resolutions" in recent.json()["data"]["items"][0]
    assert recent.json()["data"]["items"][0]["harness"]["social_event"]["event_id"] == "event-1"
    assert "enrichment" not in recent.json()["data"]["items"][0]

    assert search.status_code == 200
    assert search.json()["data"]["items"][0]["event"]["event_id"] == "event-1"

    assert asset_flow.status_code == 200
    assert asset_flow.json()["data"]["targets"][0]["target"]["symbol"] == "PEPE"

    assert account_alerts.status_code == 200
    assert account_alerts.json()["data"]["items"][0]["event_id"] == "event-1"
    assert account_alerts.json()["data"]["items"][0]["token_resolution_status"] == "resolved"


def test_api_exposes_notification_list_summary_and_read_state(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        runtime = client.app.state.service
        first = runtime.notifications.insert_notification(
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
        runtime.notifications.insert_notification(
            dedup_key="hot:pepe",
            rule_id="hot_quality_token_5m",
            severity="high",
            title="PEPE heat",
            body="heat score 88",
            entity_type="token",
            entity_key="token:eth:pepe",
            symbol="PEPE",
            chain="eth",
            address=PEPE,
            source_table="token_flow",
            source_id="token:eth:pepe",
            occurrence_at_ms=1_700_000_060_000,
            payload={"social_heat_score": 88},
            channels=["in_app"],
        )
        assert first is not None

        headers = {"Authorization": "Bearer secret"}
        summary = client.get("/api/notification-summary", headers=headers)
        listed = client.get("/api/notifications?limit=10", headers=headers)
        read = client.post(f"/api/notifications/{first['notification_id']}/read", headers=headers)
        unread = client.get("/api/notifications?unread_only=true&limit=10", headers=headers)
        updated_summary = client.get("/api/notification-summary", headers=headers)

    assert summary.status_code == 200
    assert summary.json()["data"]["unread_count"] == 2
    assert summary.json()["data"]["high_unread_count"] == 1
    assert summary.json()["data"]["account_unread_counts"] == {"toly": 1}

    assert listed.status_code == 200
    assert listed.json()["data"]["items"][0]["rule_id"] == "hot_quality_token_5m"
    assert listed.json()["data"]["items"][0]["payload"]["social_heat_score"] == 88
    assert listed.json()["data"]["items"][0]["channels"] == ["in_app"]

    assert read.status_code == 200
    assert read.json()["data"]["updated"] is True
    assert unread.status_code == 200
    assert [item["notification_id"] for item in unread.json()["data"]["items"]] != [first["notification_id"]]
    assert updated_summary.json()["data"]["unread_count"] == 1


def test_api_exposes_notification_delivery_audit(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        runtime = client.app.state.service
        notification = runtime.notifications.insert_notification(
            dedup_key="hot:pepe",
            rule_id="hot_quality_token_5m",
            severity="high",
            title="PEPE heat",
            body="heat score 88",
            entity_type="token",
            entity_key="token:eth:pepe",
            symbol="PEPE",
            source_table="token_flow",
            source_id="token:eth:pepe",
            occurrence_at_ms=1_700_000_060_000,
            payload={"social_heat_score": 88},
            channels=["in_app", "pushdeer"],
        )
        assert notification is not None
        runtime.notifications.enqueue_delivery(
            notification_id=notification["notification_id"],
            channel_id="pushdeer",
            provider="apprise",
            max_attempts=5,
            next_run_at_ms=1_700_000_060_000,
        )

        response = client.get("/api/notification-deliveries", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["items"][0]["channel_id"] == "pushdeer"
    assert body["data"]["items"][0]["provider"] == "apprise"
    assert body["data"]["items"][0]["status"] == "pending"


def test_api_exposes_empty_harness_read_models_without_404(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        headers = {"Authorization": "Bearer secret"}
        responses = [
            client.get("/api/social-events?window=1h&limit=5", headers=headers),
            client.get("/api/attention-seeds?window=1h&limit=5", headers=headers),
            client.get("/api/harness-snapshots?window=1h&horizon=6h&limit=5", headers=headers),
            client.get("/api/harness-outcomes?window=1h&horizon=6h&limit=5", headers=headers),
            client.get("/api/harness-credits?window=1h&horizon=6h&limit=5", headers=headers),
            client.get("/api/harness-health", headers=headers),
            client.get("/api/harness-score-buckets?horizon=6h", headers=headers),
        ]

    assert [response.status_code for response in responses] == [200, 200, 200, 200, 200, 200, 200]
    assert responses[0].json()["data"]["items"] == []
    assert responses[1].json()["data"]["items"] == []
    assert responses[2].json()["data"]["items"] == []
    assert responses[3].json()["data"]["items"] == []
    assert responses[4].json()["data"]["items"] == []
    assert responses[5].json()["data"]["snapshots_24h"] == 0
    assert responses[6].json()["data"]["items"][2]["bucket"] == "-0.4 to 0.4"


def test_api_exposes_trading_attention_pulse_without_harness_chains(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        event = make_token_event("event-attention-pulse", symbol="PEPE", address=PEPE, text=f"$PEPE ignition {PEPE}")
        client.app.state.service.ingest.ingest_event(event, is_watched=True)

        response = client.get(
            "/api/signal-lab/pulse",
            params={"window": "1h", "scope": "matched", "limit": 5},
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["summary"]["direct_token"] == 1
    assert data["items"][0]["kind"] == "direct_token"
    assert data["items"][0]["linked_tokens"][0]["symbol"] == "PEPE"


def test_api_asset_flow_scope_filters_watched_mentions(tmp_path):
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
        all_flow = client.get("/api/token-radar", params={"window": "5m", "scope": "all"}, headers=headers)
        watched_flow = client.get("/api/token-radar", params={"window": "5m", "scope": "matched"}, headers=headers)

    assert all_flow.status_code == 200
    assert {item["target"]["symbol"] for item in all_flow.json()["data"]["targets"]} == {"PEPE", "BONK"}

    assert watched_flow.status_code == 200
    assert watched_flow.json()["data"]["scope"] == "matched"
    assert [item["target"]["symbol"] for item in watched_flow.json()["data"]["targets"]] == ["PEPE"]


def test_api_target_posts_returns_full_post_pages_and_requires_target_identity(tmp_path):
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

        asset_flow = client.get(
            "/api/token-radar",
            params={"window": "5m", "limit": 5, "scope": "all"},
            headers={"Authorization": "Bearer secret"},
        ).json()["data"]["targets"][0]
        target_type = asset_flow["target"]["target_type"]
        target_id = asset_flow["target"]["target_id"]

        missing = client.get("/api/target-posts?window=5m", headers={"Authorization": "Bearer secret"})
        first_page = client.get(
            "/api/target-posts",
            params={"target_type": target_type, "target_id": target_id, "window": "5m", "scope": "all", "limit": 2},
            headers={"Authorization": "Bearer secret"},
        )
        second_page = client.get(
            "/api/target-posts",
            params={
                "target_type": target_type,
                "target_id": target_id,
                "window": "5m",
                "scope": "all",
                "limit": 2,
                "cursor": first_page.json()["data"]["next_cursor"],
            },
            headers={"Authorization": "Bearer secret"},
        )

    assert missing.status_code == 400
    assert missing.json() == {"ok": False, "error": "target_required", "field": "target_id"}
    assert first_page.status_code == 200
    first_body = first_page.json()["data"]
    assert first_body["total_count"] == 3
    assert first_body["returned_count"] == 2
    assert first_body["has_more"] is True
    assert first_body["query"]["target_type"] == target_type
    assert first_body["query"]["target_id"] == target_id
    assert first_body["items"][0]["post_quality"]["score_version"] == "token_target_post_quality_v1"
    assert first_body["items"][0]["post_quality"]["contributions"]
    assert "score" not in first_body["items"][0]
    assert second_page.status_code == 200
    assert second_page.json()["data"]["returned_count"] == 1


def test_api_target_posts_rejects_malformed_cursor(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        response = client.get(
            "/api/target-posts",
            params={
                "target_type": "Asset",
                "target_id": "asset:eip155:1:erc20:0xpepe",
                "window": "5m",
                "cursor": "abcde",
            },
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 400
    assert response.json() == {"ok": False, "error": "invalid_cursor"}


def test_api_target_social_timeline_returns_buckets_authors_and_posts(tmp_path):
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

        asset_flow = client.get(
            "/api/token-radar",
            params={"window": "5m", "limit": 5, "scope": "all"},
            headers={"Authorization": "Bearer secret"},
        ).json()["data"]["targets"][0]
        target_type = asset_flow["target"]["target_type"]
        target_id = asset_flow["target"]["target_id"]

        missing = client.get("/api/target-social-timeline?window=5m", headers={"Authorization": "Bearer secret"})
        response = client.get(
            "/api/target-social-timeline",
            params={"target_type": target_type, "target_id": target_id, "window": "5m", "scope": "all", "limit": 2},
            headers={"Authorization": "Bearer secret"},
        )

    assert missing.status_code == 400
    assert missing.json() == {"ok": False, "error": "target_required", "field": "target_id"}
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["query"]["bucket"] == "30s"
    assert data["query"]["target_type"] == target_type
    assert data["query"]["target_id"] == target_id
    assert data["summary"]["posts"] == 2
    assert data["buckets"]
    assert data["authors"]
    assert data["returned_count"] == 2
    assert data["has_more"] is True


def test_api_target_social_timeline_rejects_manual_bucket_param(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        response = client.get(
            "/api/target-social-timeline",
            params={"target_type": "Asset", "target_id": "asset:eip155:1:erc20:0xpepe", "window": "5m", "bucket": "1m"},
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 400
    assert response.json() == {"ok": False, "error": "unsupported_query_param", "field": "bucket"}


def test_api_rejects_removed_1m_window(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        response = client.get(
            "/api/token-radar",
            params={"window": "1m", "limit": 5, "scope": "all"},
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 400
    assert response.json() == {"ok": False, "error": "invalid_window", "field": "window"}


def test_api_target_posts_requires_target_identity(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        response = client.get(
            "/api/target-posts",
            params={"window": "5m"},
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 400
    assert response.json() == {"ok": False, "error": "target_required", "field": "target_id"}


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


def test_api_rejects_removed_narrative_product_surfaces(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        headers = {"Authorization": "Bearer secret"}
        narrative_flow = client.get("/api/narrative-flow?window=1h&limit=5", headers=headers)
        account_narratives = client.get("/api/account-narratives?window=24h&limit=5", headers=headers)
        seeds = client.get("/api/narrative-seeds?window=24h&limit=5", headers=headers)
        flow = client.get("/api/narrative-token-flow?seed_id=seed&window=1h&limit=5", headers=headers)
        frontier = client.get("/api/attention-frontier?window=1h&limit=5", headers=headers)

    assert narrative_flow.status_code == 404
    assert account_narratives.status_code == 404
    assert seeds.status_code == 404
    assert flow.status_code == 404
    assert frontier.status_code == 404
