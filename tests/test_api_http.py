import time
from dataclasses import replace

from fastapi.testclient import TestClient

from gmgn_twitter_intel.api.app import create_app
from gmgn_twitter_intel.collector.gmgn_token_payload import parse_gmgn_token_payload
from gmgn_twitter_intel.models import Author, Content, Source, TwitterEvent
from gmgn_twitter_intel.pipeline.harness_snapshot_builder import HarnessSnapshotBuilder
from gmgn_twitter_intel.pipeline.social_event_extraction import AnchorTerm, SocialEventExtraction, SocialTokenCandidate
from gmgn_twitter_intel.settings import Settings
from tests.test_token_signal_repository import snapshot_payload

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


def test_api_exposes_token_signal_snapshot_outcome_and_evaluation_reads(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        runtime = client.app.state.service
        runtime.evidence.insert_event(make_event("event-1"), is_watched=True)
        runtime.token_signals.create_snapshot(**snapshot_payload(snapshot_id="snapshot-api"))
        runtime.token_signals.record_outcome(
            outcome_id="outcome-api",
            snapshot_id="snapshot-api",
            horizon="6h",
            status="settled",
            entry_snapshot_id="entry",
            exit_snapshot_id="exit",
            benchmark_snapshot_ids=[],
            entry_price=1.0,
            exit_price=1.03,
            benchmark_return=0.0,
            actual_return=0.03,
            abnormal_return=0.03,
            realized_vol=0.06,
            normalized_outcome=0.5,
            market_coverage_status="ready",
            settled_at_ms=1_700_021_600_000,
        )
        runtime.token_signals.upsert_evaluation(
            evaluation_id="evaluation-api",
            horizon="6h",
            window="5m",
            scope="all",
            score_version="social_opportunity_v2",
            bucket_label="55-69",
            bucket_min=55,
            bucket_max=69,
            snapshot_count=1,
            settled_count=1,
            settlement_coverage=1.0,
            avg_actual_return=0.03,
            avg_abnormal_return=0.03,
            avg_normalized_outcome=0.5,
            directional_hit_rate=1.0,
            wilson_low=0.2,
            wilson_high=1.0,
            generated_at_ms=1_700_021_700_000,
        )

        snapshots = client.get("/api/token-signal-snapshots", headers={"Authorization": "Bearer secret"})
        outcomes = client.get("/api/token-signal-outcomes", headers={"Authorization": "Bearer secret"})
        evaluations = client.get("/api/token-signal-evaluations", headers={"Authorization": "Bearer secret"})

    assert snapshots.status_code == 200
    assert snapshots.json()["data"]["items"][0]["score_versions"]["opportunity"] == "social_opportunity_v2"
    assert outcomes.status_code == 200
    assert outcomes.json()["data"]["items"][0]["normalized_outcome"] == 0.5
    assert evaluations.status_code == 200
    assert evaluations.json()["data"]["items"][0]["bucket_label"] == "55-69"


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
        event = make_token_event("event-1", symbol="PEPE", address=PEPE, text=f"$PEPE ignition {PEPE}")
        client.app.state.service.ingest.ingest_event(event, is_watched=True)
        HarnessSnapshotBuilder(client.app.state.service.harness).materialize(
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
        token_flow = client.get("/api/token-flow?window=5m&limit=5", headers=headers)
        account_alerts = client.get("/api/account-alerts?window=24h&limit=5", headers=headers)

    assert recent.status_code == 200
    assert recent.json()["data"]["events"][0]["event_id"] == "event-1"
    assert "token_attributions" in recent.json()["data"]["items"][0]
    assert recent.json()["data"]["items"][0]["harness"]["social_event"]["event_id"] == "event-1"
    assert "enrichment" not in recent.json()["data"]["items"][0]

    assert search.status_code == 200
    assert search.json()["data"]["items"][0]["event"]["event_id"] == "event-1"

    assert token_flow.status_code == 200
    assert token_flow.json()["data"]["items"][0]["identity"]["symbol"] == "PEPE"

    assert account_alerts.status_code == 200
    assert account_alerts.json()["data"]["items"][0]["event_id"] == "event-1"
    assert account_alerts.json()["data"]["items"][0]["token_resolution_status"] == "resolved_ca"


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


def test_api_exposes_signal_lab_chains_product_read_model(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        event = make_token_event("event-signal-chain", symbol="PEPE", address=PEPE, text=f"$PEPE ignition {PEPE}")
        client.app.state.service.ingest.ingest_event(event, is_watched=True)
        HarnessSnapshotBuilder(client.app.state.service.harness).materialize(
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
                summary_zh="PEPE ignition 形成 Signal Chain。",
                raw_response={"ok": True},
            ),
            run_id="run-signal-chain",
            model_version="fake-model",
        )

        response = client.get(
            "/api/signal-lab/chains",
            params={"window": "1h", "horizon": "6h", "scope": "matched", "limit": 5},
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["query"] == {
        "window": "1h",
        "horizon": "6h",
        "scope": "matched",
        "stage": None,
        "asset": None,
        "handle": None,
        "q": None,
    }
    assert data["summary"]["frozen"] == 1
    assert data["returned_count"] == 1
    assert data["items"][0]["chain_id"].startswith("snapshot:")
    assert data["items"][0]["lineage"]["event_id"] == "event-signal-chain"
    assert data["items"][0]["lineage"]["seed_id"]
    assert data["items"][0]["lineage"]["snapshot_id"]


def test_api_signal_lab_chains_cursor_paginates_read_model(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        base_ms = int(time.time() * 1000)
        for index in range(2):
            event = make_token_event(
                f"event-signal-page-{index}",
                symbol="PEPE",
                address=PEPE,
                text=f"$PEPE signal page {index}",
                received_at_ms=base_ms - index * 1_000,
            )
            client.app.state.service.ingest.ingest_event(event, is_watched=True)
            HarnessSnapshotBuilder(client.app.state.service.harness).materialize(
                event=event.to_dict(),
                extraction=SocialEventExtraction(
                    is_signal_event=True,
                    event_type="meme_phrase_seed",
                    source_action="posted",
                    subject=f"PEPE page {index}",
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
                    summary_zh=f"PEPE page {index} 形成 Signal Chain。",
                    raw_response={"ok": True},
                ),
                run_id=f"run-signal-page-{index}",
                model_version="fake-model",
            )

        first_page = client.get(
            "/api/signal-lab/chains",
            params={"window": "1h", "horizon": "6h", "scope": "matched", "limit": 1},
            headers={"Authorization": "Bearer secret"},
        )
        second_page = client.get(
            "/api/signal-lab/chains",
            params={
                "window": "1h",
                "horizon": "6h",
                "scope": "matched",
                "limit": 1,
                "cursor": first_page.json()["data"]["next_cursor"],
            },
            headers={"Authorization": "Bearer secret"},
        )

    assert first_page.status_code == 200
    assert second_page.status_code == 200
    first = first_page.json()["data"]
    second = second_page.json()["data"]
    assert first["has_more"] is True
    assert first["next_cursor"] == "1"
    assert first["items"][0]["lineage"]["event_id"] == "event-signal-page-0"
    assert second["has_more"] is False
    assert second["next_cursor"] is None
    assert second["items"][0]["lineage"]["event_id"] == "event-signal-page-1"


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
            params={"token_id": token_id, "window": "5m", "scope": "all", "limit": 2},
            headers={"Authorization": "Bearer secret"},
        )

    assert missing.status_code == 400
    assert missing.json() == {"ok": False, "error": "missing_token_identity"}
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["query"]["bucket"] == "30s"
    assert data["summary"]["posts"] == 3
    assert data["buckets"]
    assert data["authors"]
    assert data["returned_count"] == 2
    assert data["has_more"] is True


def test_api_token_social_timeline_rejects_manual_bucket_param(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        response = client.get(
            "/api/token-social-timeline",
            params={"token_id": f"token:eth:{PEPE}", "window": "5m", "bucket": "1m"},
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 400
    assert response.json() == {"ok": False, "error": "unsupported_query_param", "field": "bucket"}


def test_api_rejects_removed_1m_window(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        response = client.get(
            "/api/token-flow",
            params={"window": "1m", "limit": 5, "scope": "all"},
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 400
    assert response.json() == {"ok": False, "error": "invalid_window", "field": "window"}


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
