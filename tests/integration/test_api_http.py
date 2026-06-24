import json
import math
import time
from dataclasses import replace
from decimal import Decimal
from hashlib import sha256

from fastapi.testclient import TestClient

from parallax.app.runtime.app import create_app
from parallax.app.runtime.worker_manifest import all_worker_manifests
from parallax.app.surfaces.api.responses import _json
from parallax.domains.account_quality.repositories.account_quality_repository import AccountQualityRepository
from parallax.domains.evidence.interfaces import Author, Content, Source, TwitterEvent
from parallax.domains.ingestion.types.gmgn_token_payload import parse_gmgn_token_payload
from parallax.platform.config.settings import Settings
from tests.postgres_test_utils import postgres_settings_storage, prepare_postgres_database

PEPE = "0x6982508145454ce325ddbe47a25d4ec3d2311933"
TOKEN_RADAR_TEST_REBUILD_OFFSET_MS = 60_000


def _pulse_factor_snapshot(
    *,
    symbol: str = "PEPE",
    target_id: str = "asset:pepe",
    score: int = 82,
    market_status: str = "fresh",
    blocked_reasons: list[str] | None = None,
) -> dict[str, object]:
    blocked = blocked_reasons or []
    market_ready = market_status == "fresh"
    market_health = "ready" if market_ready else "partial"
    observation = {
        "target_type": "Asset",
        "target_id": target_id,
        "source": "event_anchor",
        "provider": "okx" if market_ready else None,
        "pricefeed_id": None,
        "price_usd": 0.42 if market_ready else None,
        "price_quote": None,
        "quote_symbol": "USD" if market_ready else None,
        "price_basis": "usd" if market_ready else None,
        "market_cap_usd": 120_000 if market_ready else None,
        "liquidity_usd": 55_000 if market_ready else None,
        "holders": 800 if market_ready else None,
        "volume_24h_usd": 2_300_000 if market_ready else None,
        "open_interest_usd": None,
        "observed_at_ms": 1_700_000_000_000 if market_ready else None,
        "received_at_ms": 1_700_000_000_000 if market_ready else None,
        "raw_payload_hash": None,
    }
    return {
        "schema_version": "token_factor_snapshot_v3_social_attention",
        "subject": {
            "target_type": "Asset",
            "target_id": target_id,
            "target_market_type": "dex",
            "symbol": symbol,
            "chain": "sol",
        },
        "market": {
            "event_anchor": observation if market_ready else None,
            "decision_latest": {**observation, "source": "decision_latest"} if market_ready else None,
            "readiness": {
                "anchor_status": "ready" if market_ready else "missing",
                "latest_status": "live" if market_ready else "missing",
                "dex_floor_status": "ready" if market_ready else "missing_fields",
                "missing_fields": [] if market_ready else ["holders", "liquidity_usd", "market_cap_usd"],
                "stale_fields": [],
            },
        },
        "gates": {
            "eligible_for_high_alert": not blocked,
            "blocked_reasons": blocked,
            "risk_reasons": blocked,
            "max_decision": "watch" if blocked else "high_alert",
        },
        "data_health": {"identity": "ready", "market": market_health, "social": "ready", "alpha": "ready"},
        "families": {
            "social_heat": {
                "raw_score": 82,
                "score": 82,
                "weight": 0.45,
                "data_health": "ready",
                "facts": {"mentions_1h": 8, "unique_authors": 4, "watched_mentions": 1},
                "factors": {},
            },
            "social_propagation": {
                "raw_score": 78,
                "score": 78,
                "weight": 0.4,
                "data_health": "ready",
                "facts": {"independent_authors": 4},
                "factors": {},
            },
            "semantic_catalyst": {
                "raw_score": 72,
                "score": 72,
                "weight": 0.15,
                "data_health": "ready",
                "facts": {"phase": "ignition"},
                "factors": {},
            },
            "timing_risk": {
                "raw_score": 65,
                "score": 65,
                "weight": 0.0,
                "data_health": "ready",
                "facts": {"price_change_status": market_status},
                "factors": {},
            },
        },
        "normalization": {"status": "pending_cross_section"},
        "composite": {
            "rank_score": score,
            "recommended_decision": "watch",
            "family_scores": {
                "social_heat": 82,
                "social_propagation": 78,
                "semantic_catalyst": 72,
                "timing_risk": 65,
            },
        },
        "provenance": {"source_event_ids": ["event-api-1"], "computed_at_ms": 2_000},
    }


def _pulse_gate(
    *,
    pulse_status: str = "token_watch",
    score: float = 82.0,
    blocked_reasons: list[str] | None = None,
) -> dict[str, object]:
    blocked = blocked_reasons or []
    return {
        "pulse_status": pulse_status,
        "verdict": pulse_status,
        "candidate_score": score,
        "score_band": "watch",
        "gate_reasons": blocked or ["factor_snapshot_watch_gate_passed"],
        "risk_reasons": blocked,
        "hard_risks": blocked,
        "max_recommendation": "research",
        "eligible_for_high_alert": not blocked,
        "blocked_reasons": blocked,
    }


def _pulse_decision(
    summary: str = "PEPE 社交热度显著上升。",
    *,
    recommendation: str = "watchlist",
    abstain_reason: str | None = None,
) -> dict[str, object]:
    confidence = 0.0 if recommendation == "abstain" else 0.72
    return {
        "route": "meme",
        "recommendation": recommendation,
        "confidence": confidence,
        "abstain_reason": abstain_reason,
        "summary_zh": summary,
        "invalidation_conditions": ["讨论快速降温。"],
        "residual_risks": ["价格响应仍可能变化。"],
        "evidence_event_ids": ["event-api-1"],
        "supporting_evidence_refs": ["event:event-api-1"],
        "risk_evidence_refs": ["market:pf-api"],
        "data_gap_refs": [],
    }


def test_api_json_response_encodes_decimal_payloads():
    response = _json({"ok": True, "data": {"price": Decimal("1.23")}})

    assert json.loads(response.body) == {"ok": True, "data": {"price": 1.23}}


def test_api_json_response_replaces_non_finite_float_payloads_with_null():
    response = _json(
        {
            "ok": True,
            "data": {
                "score": math.nan,
                "nested": [{"value": math.inf}, {"value": -math.inf}, {"value": 1.0}],
            },
        }
    )

    assert json.loads(response.body) == {
        "ok": True,
        "data": {
            "score": None,
            "nested": [{"value": None}, {"value": None}, {"value": 1.0}],
        },
    }


def test_token_images_serves_ready_local_file_without_auth(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        image_id = seed_ready_token_image(client, content=b"fake-png")
        response = client.get(f"/api/token-images/{image_id}")

    assert response.status_code == 200
    assert response.content == b"fake-png"
    assert response.headers["content-type"].startswith("image/png")
    assert response.headers["cache-control"] == "public, max-age=86400"


def test_token_images_rejects_invalid_image_ids(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        responses = [client.get(f"/api/token-images/{image_id}") for image_id in ("a" * 63, "A" * 64, "g" * 64)]

    assert [response.status_code for response in responses] == [404, 404, 404]


def test_token_images_returns_404_for_missing_and_error_rows(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        source_url = "https://gmgn.ai/external-res/error-token.png"
        with client.app.state.service.repositories() as repos:
            repos.token_image_assets.upsert_pending_sources(
                [
                    {
                        "source_url": source_url,
                        "source_provider": "gmgn_dex_profile",
                        "source_kind": "asset_profile.logo_url",
                        "raw_ref_json": {"source": "test"},
                    }
                ],
                now_ms=1_779_000_000_000,
            )
            repos.token_image_assets.mark_error(
                source_url,
                error="upstream failed",
                now_ms=1_779_000_000_100,
                retry_ms=30_000,
            )

        missing = client.get(f"/api/token-images/{'0' * 64}")
        error = client.get(f"/api/token-images/{_sha256(source_url)}")

    assert missing.status_code == 404
    assert error.status_code == 404


def test_token_images_returns_404_when_ready_file_is_missing(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        image_id = seed_ready_token_image(client, storage_path="missing.png", write_file=False)
        response = client.get(f"/api/token-images/{image_id}")

    assert response.status_code == 404


def test_token_images_rejects_storage_path_traversal(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        runtime = client.app.state.service
        cache_root = runtime.settings.app_home / "cache"
        cache_root.mkdir(parents=True, exist_ok=True)
        (cache_root / "outside.png").write_bytes(b"leaked")
        image_id = insert_ready_token_image_row(client, storage_path="../outside.png")

        response = client.get(f"/api/token-images/{image_id}")

    assert response.status_code == 404
    assert response.content != b"leaked"


def test_old_token_image_proxy_route_is_absent(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        response = client.get(
            "/api/token-image",
            params={"url": "https://gmgn.ai/external-res/token-alpha.png"},
        )

    assert response.status_code == 404


def seed_ready_token_image(
    client: TestClient,
    *,
    source_url: str = "https://gmgn.ai/external-res/token-alpha.png",
    storage_path: str = "token-alpha.png",
    content: bytes = b"fake-png",
    media_type: str = "image/png",
    write_file: bool = True,
) -> str:
    runtime = client.app.state.service
    cache_dir = runtime.settings.app_home / "cache" / "token-images"
    if write_file:
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / storage_path).write_bytes(content)
    with runtime.repositories() as repos:
        repos.token_image_assets.upsert_pending_sources(
            [
                {
                    "source_url": source_url,
                    "source_provider": "gmgn_dex_profile",
                    "source_kind": "asset_profile.logo_url",
                    "raw_ref_json": {"source": "test"},
                }
            ],
            now_ms=1_779_000_000_000,
        )
        row = repos.token_image_assets.mark_ready(
            source_url,
            media_type=media_type,
            file_extension=".png",
            content_sha256="a" * 64,
            byte_size=len(content),
            storage_path=storage_path,
            now_ms=1_779_000_000_100,
        )
    return str(row["image_id"])


def insert_ready_token_image_row(
    client: TestClient,
    *,
    source_url: str = "https://gmgn.ai/external-res/traversal-token.png",
    storage_path: str,
) -> str:
    image_id = _sha256(source_url)
    with client.app.state.service.repositories() as repos:
        repos.conn.execute(
            """
            INSERT INTO token_image_assets(
              image_id, source_url, source_url_hash, source_provider, source_kind, status,
              media_type, file_extension, content_sha256, byte_size, storage_path,
              public_url, raw_ref_json, failure_count, next_refresh_at_ms,
              created_at_ms, updated_at_ms
            )
            VALUES (
              %s, %s, %s, 'gmgn_dex_profile', 'asset_profile.logo_url', 'ready',
              'image/png', '.png', %s, 6, %s, %s, '{}'::jsonb, 0, %s, %s, %s
            )
            """,
            (
                image_id,
                source_url,
                image_id,
                "b" * 64,
                storage_path,
                f"/api/token-images/{image_id}",
                1_779_000_000_000,
                1_779_000_000_000,
                1_779_000_000_000,
            ),
        )
        repos.conn.commit()
    return image_id


def _sha256(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


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


def rebuild_token_radar(client: TestClient, *, now_ms: int | None = None) -> None:
    worker_entry = client.app.state.service.workers["token_radar_projection"]
    worker = getattr(worker_entry, "worker", worker_entry)
    assert worker is not None
    deadline = time.monotonic() + 10.0
    drained_once = False
    base_now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    interval_ms = (
        int(
            max(
                float(getattr(worker.settings, "interval_seconds", 1.0)),
                float(getattr(worker.settings, "cold_interval_seconds", 1.0)),
            )
            * 1000
        )
        + 1
    )
    attempt = 0
    while True:
        worker.rebuild_once(now_ms=base_now_ms + attempt * interval_ms)
        attempt += 1
        pending, leased = _token_radar_dirty_queue_counts(client)
        while leased:
            if time.monotonic() >= deadline:
                raise AssertionError("token radar projection dirty leases did not drain")
            time.sleep(0.05)
            pending, leased = _token_radar_dirty_queue_counts(client)
        if pending == 0:
            if drained_once:
                return
            drained_once = True
            continue
        if time.monotonic() >= deadline:
            raise AssertionError("token radar projection dirty queues did not drain")
        time.sleep(0.05)


def _token_radar_dirty_queue_counts(client: TestClient) -> tuple[int, int]:
    runtime = client.app.state.service
    with runtime.db.api_pool.connection() as conn:
        row = conn.execute(
            """
            SELECT
              (
                SELECT COUNT(*) FROM token_radar_source_dirty_events
              ) + (
                SELECT COUNT(*) FROM token_radar_dirty_targets
              ) AS pending,
              (
                SELECT COUNT(*) FROM token_radar_source_dirty_events WHERE lease_owner IS NOT NULL
              ) + (
                SELECT COUNT(*) FROM token_radar_dirty_targets WHERE lease_owner IS NOT NULL
              ) AS leased
            """
        ).fetchone()
    return int(row["pending"] or 0), int(row["leased"] or 0)


def seed_resolved_asset_with_event(
    client: TestClient,
    *,
    symbol: str = "HANSA",
    address: str = PEPE,
    event_id: str = "event-token-case-1",
    now_ms: int | None = None,
) -> dict[str, object]:
    event = make_token_event(
        event_id,
        symbol=symbol,
        address=address,
        text=f"${symbol} ignition {address}",
        received_at_ms=now_ms if now_ms is not None else int(time.time() * 1000),
    )
    client.app.state.service.ingest.ingest_event(event, is_watched=True)
    search = client.get(
        "/api/search",
        params={"q": f"${symbol}", "limit": 5, "window": "24h"},
        headers={"Authorization": "Bearer secret"},
    )
    assert search.status_code == 200
    candidates = search.json()["data"]["target_candidates"]
    resolved = [candidate for candidate in candidates if candidate["status"] == "resolved"]
    assert len(resolved) == 1
    return resolved[0]


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


def test_api_search_rejects_removed_filter_params(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        response = client.get("/api/search", params={"symbol": "PEPE"}, headers={"Authorization": "Bearer secret"})

    assert response.status_code == 400
    assert response.json() == {"ok": False, "error": "unsupported_query_param", "field": "symbol"}


def test_api_search_rejects_malformed_cursor(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        response = client.get(
            "/api/search",
            params={"q": "PEPE", "cursor": "not-a-cursor"},
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 400
    assert response.json() == {"ok": False, "error": "invalid_cursor"}


def test_api_status_exposes_market_tick_and_live_market_status(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        response = client.get("/api/status", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 200
    data = response.json()["data"]
    assert "_".join(("anchor", "price")) not in data
    assert "live_price_gateway" not in data
    assert "resolution_refresh" not in data
    assert "token_radar_projection" not in data
    assert "worker_lanes" in data
    workers = data["workers"]
    for name in (
        "token_capture_tier",
        "market_tick_stream",
        "market_tick_poll",
        "event_anchor_backfill",
        "live_price_gateway",
        "resolution_refresh",
        "token_radar_projection",
    ):
        assert set(workers[name]) >= {
            "enabled",
            "running",
            "last_started_at_ms",
            "last_finished_at_ms",
            "last_result",
            "last_error",
        }
    assert "event_anchor_backfill" in workers
    assert workers["event_anchor_backfill"]["enabled"] is True


def test_api_exposes_recent_search_and_signal_read_models(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        now_ms = int(time.time() * 1000)
        rebuild_now_ms = now_ms + TOKEN_RADAR_TEST_REBUILD_OFFSET_MS
        event = make_token_event(
            "event-1",
            symbol="PEPE",
            address=PEPE,
            text=f"$PEPE ignition {PEPE}",
            received_at_ms=now_ms - 1_000,
        )
        client.app.state.service.ingest.ingest_event(event, is_watched=True)
        rebuild_token_radar(client, now_ms=rebuild_now_ms)

        headers = {"Authorization": "Bearer secret"}
        recent = client.get("/api/recent?limit=5", headers=headers)
        search = client.get("/api/search", params={"q": "$PEPE", "limit": 5, "window": "24h"}, headers=headers)
        search_inspect = client.get(
            "/api/search/inspect",
            params={"q": "$PEPE", "limit": 5, "window": "24h", "scope": "all"},
            headers=headers,
        )
        asset_flow = client.get("/api/token-radar?window=5m&limit=5", headers=headers)
        account_alerts = client.get("/api/account-alerts?window=24h&limit=5", headers=headers)

    assert recent.status_code == 200
    assert recent.json()["data"]["events"][0]["event_id"] == "event-1"
    assert "token_intents" in recent.json()["data"]["items"][0]
    assert "token_resolutions" in recent.json()["data"]["items"][0]
    assert "harness" not in recent.json()["data"]["items"][0]
    assert "enrichment" not in recent.json()["data"]["items"][0]

    assert search.status_code == 200
    search_data = search.json()["data"]
    assert search_data["items"][0]["event"]["event_id"] == "event-1"
    assert search_data["page"]["returned_count"] == 1
    assert "total_count" not in search_data
    assert search_data["query"]["window"] == "24h"

    assert search_inspect.status_code == 200
    inspect_data = search_inspect.json()["data"]
    assert inspect_data["query"]["result_kind"] == "token_result"
    assert inspect_data["resolver"]["target_candidates"]
    assert inspect_data["token_result"]["posts"]["items"][0]["event_id"] == "event-1"
    assert inspect_data["token_result"]["timeline"]["market_candles"]["target_type"] == "Asset"
    assert inspect_data["token_result"]["profile"]["status"] == "pending"
    assert inspect_data["token_result"]["profile"]["provider"] is None
    assert inspect_data["token_result"]["market_live"]["status"] in {"missing", "unsupported", "ready"}
    legacy_market_field = "market_overlay"
    assert legacy_market_field not in inspect_data["token_result"]
    assert "radar_item" not in inspect_data["token_result"]
    assert "agent_brief" not in inspect_data["token_result"]
    assert inspect_data["token_result"]["discussion_digest"]["status"] in {"pending", "semantic_unavailable"}
    assert inspect_data["token_result"]["discussion_digest"]["data_gaps"]

    assert asset_flow.status_code == 200
    radar_row = asset_flow.json()["data"]["targets"][0]
    assert radar_row["target"]["symbol"] == "PEPE"
    assert radar_row["profile"]["status"] == "pending"
    assert radar_row["profile"]["provider"] is None
    assert radar_row["discussion_digest"]["status"] in {"pending", "semantic_unavailable"}
    assert radar_row["discussion_digest"]["data_gaps"]

    assert account_alerts.status_code == 200
    assert account_alerts.json()["data"]["items"][0]["event_id"] == "event-1"
    assert account_alerts.json()["data"]["items"][0]["token_resolution_status"] == "EXACT"


def test_token_radar_public_payload_excludes_unresolved_source_dirty_rows(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        now_ms = int(time.time() * 1000)
        rebuild_now_ms = now_ms + TOKEN_RADAR_TEST_REBUILD_OFFSET_MS
        runtime = client.app.state.service
        runtime.ingest.ingest_event(
            make_token_event(
                "event-pepe-diagnostics",
                symbol="PEPE",
                address=PEPE,
                text=f"$PEPE {PEPE}",
                received_at_ms=now_ms - 1_000,
            ),
            is_watched=True,
        )
        runtime.ingest.ingest_event(
            make_event(
                "event-unknown-diagnostics",
                text="$NEWTOKEN soon",
                received_at_ms=now_ms - 500,
            ),
            is_watched=True,
        )
        rebuild_token_radar(client, now_ms=rebuild_now_ms)

        response = client.get(
            "/api/token-radar",
            params={"window": "5m", "scope": "all", "limit": 20},
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 200
    data = response.json()["data"]
    public_rows = [*data["targets"], *data["attention"]]
    assert public_rows
    assert all(row["target"]["target_id"] for row in public_rows)
    assert "NEWTOKEN" not in {row["target"]["symbol"] for row in public_rows}
    assert data["projection"]["unresolved"]["identity_missing_count"] == 0
    assert "NEWTOKEN" not in data["projection"]["unresolved"]["sample_symbols"]


def test_token_radar_uses_live_market_endpoint_without_legacy_overlay(tmp_path):
    class FakeLiveGateway:
        def status_payload(self) -> dict[str, object]:
            return {"enabled": True, "running": True}

        async def stop(self) -> None:
            return None

        async def aclose(self) -> None:
            return None

        def snapshot(self, *, target_type: str, target_id: str, now_ms: int | None = None):
            return {
                "target_type": target_type,
                "target_id": target_id,
                "status": "live",
                "price_usd": 0.123,
                "price_quote": None,
                "quote_symbol": "USD",
                "price_basis": "usd",
                "market_cap_usd": 123_000,
                "liquidity_usd": 45_000,
                "holders": 321,
                "volume_24h_usd": 9_000,
                "observed_at_ms": now_ms,
                "received_at_ms": now_ms,
                "age_ms": 0,
                "provider": "test_live",
            }

    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        now_ms = int(time.time() * 1000)
        rebuild_now_ms = now_ms + TOKEN_RADAR_TEST_REBUILD_OFFSET_MS
        runtime = client.app.state.service
        runtime.ingest.ingest_event(
            make_token_event(
                "event-pepe-live-overlay",
                symbol="PEPE",
                address=PEPE,
                text=f"$PEPE {PEPE}",
                received_at_ms=now_ms - 1_000,
            ),
            is_watched=True,
        )
        runtime.scheduler.workers["live_price_gateway"] = FakeLiveGateway()
        rebuild_token_radar(client, now_ms=rebuild_now_ms)

        response = client.get(
            "/api/token-radar",
            params={"window": "5m", "scope": "all", "limit": 20},
            headers={"Authorization": "Bearer secret"},
        )

        assert response.status_code == 200
        row = response.json()["data"]["targets"][0]
        live_market = client.get(
            "/api/live-market",
            params={"target_type": row["target"]["target_type"], "target_id": row["target"]["target_id"]},
            headers={"Authorization": "Bearer secret"},
        )

    assert "live_market" not in row
    assert row["market"]["event_anchor"] is None
    assert row["market"]["decision_latest"] is None
    assert row["market"]["readiness"]["anchor_status"] == "missing"
    assert live_market.status_code == 200
    payload = live_market.json()["data"]
    assert payload["status"] == "live"
    assert payload["price_usd"] == 0.123
    assert payload["market_cap_usd"] == 123_000
    assert payload["provider"] == "test_live"


def test_stocks_radar_returns_us_equity_market_instruments_with_unavailable_quote_state(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)
    now_ms = int(time.time() * 1000)

    with TestClient(app) as client:
        runtime = client.app.state.service
        with runtime.repositories() as repos:
            repos.registry.upsert_us_equity_symbol(
                symbol="AAPL",
                exchange="NASDAQ",
                security_name="Apple Inc. Common Stock",
                instrument_type="equity",
                source="test",
                source_updated_at_ms=now_ms,
                raw_payload={"Symbol": "AAPL"},
                observed_at_ms=now_ms,
            )
            repos.registry.upsert_us_equity_symbol(
                symbol="RKLB",
                exchange="NASDAQ",
                security_name="Rocket Lab USA, Inc. Common Stock",
                instrument_type="equity",
                source="test",
                source_updated_at_ms=now_ms,
                raw_payload={"Symbol": "RKLB"},
                observed_at_ms=now_ms,
            )

        runtime.ingest.ingest_event(
            make_event("event-aapl-1", handle="toly", text="$AAPL breakout", received_at_ms=now_ms - 10_000),
            is_watched=True,
        )
        runtime.ingest.ingest_event(
            make_event("event-aapl-2", handle="elonmusk", text="$AAPL still bid", received_at_ms=now_ms - 5_000),
            is_watched=False,
        )
        runtime.ingest.ingest_event(
            make_event("event-rklb-1", handle="toly", text="$RKLB launch cadence", received_at_ms=now_ms - 3_000),
            is_watched=True,
        )
        runtime.ingest.ingest_event(
            make_token_event(
                "event-pepe-stock-radar-exclusion",
                symbol="PEPE",
                address=PEPE,
                text=f"$PEPE {PEPE}",
                received_at_ms=now_ms - 1_000,
            ),
            is_watched=True,
        )

        response = client.get(
            "/api/stocks-radar",
            params={"window": "1h", "scope": "all", "limit": 10},
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 200
    data = response.json()["data"]
    rows = data["rows"]
    symbols = {row["target"]["symbol"] for row in rows}
    assert symbols == {"AAPL", "RKLB"}
    assert all(row["target"]["target_type"] == "MarketInstrument" for row in rows)
    assert all(row["target"]["target_id"].startswith("market_instrument:us_equity:") for row in rows)
    assert "PEPE" not in symbols
    assert data["health"] == {
        "returned_count": 2,
        "quote_ready_count": 0,
        "quote_unavailable_count": 2,
    }
    by_symbol = {row["target"]["symbol"]: row for row in rows}
    assert by_symbol["AAPL"]["attention"]["mentions"] == 2
    assert by_symbol["AAPL"]["attention"]["unique_authors"] == 2
    assert by_symbol["AAPL"]["quote"]["status"] == "unavailable"
    assert by_symbol["AAPL"]["quote"]["error"] == "quote_read_model_unavailable"
    assert by_symbol["AAPL"]["quote"]["provider"] is None
    assert by_symbol["AAPL"]["row_health"] == ["quote_unavailable"]
    assert by_symbol["RKLB"]["quote"]["status"] == "unavailable"
    assert by_symbol["RKLB"]["quote"]["error"] == "quote_read_model_unavailable"
    assert by_symbol["RKLB"]["quote"]["provider_symbol"] == "RKLB"
    assert by_symbol["RKLB"]["row_health"] == ["quote_unavailable"]


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
            dedup_key="news:pepe",
            rule_id="news_high_signal",
            severity="high",
            title="PEPE news",
            body="agent news driver",
            entity_type="token",
            entity_key="token:eth:pepe",
            symbol="PEPE",
            chain="eth",
            address=PEPE,
            source_table="news_items",
            source_id="token:eth:pepe",
            occurrence_at_ms=1_700_000_060_000,
            payload={
                "decision_class": "driver",
                "agent_run_id": "run-legacy",
                "artifact_version_hash": "artifact-legacy",
                "provider_signal": {"score": 95},
                "agent_brief": {
                    "status": "ready",
                    "direction": "bullish",
                    "summary_zh": "Agent news driver.",
                    "agent_run_id": "run-legacy",
                    "artifact_version_hash": "artifact-legacy",
                },
            },
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
    assert listed.json()["data"]["items"][0]["rule_id"] == "news_high_signal"
    assert listed.json()["data"]["items"][0]["payload"]["decision_class"] == "driver"
    assert "agent_run_id" not in listed.json()["data"]["items"][0]["payload"]
    assert "artifact_version_hash" not in listed.json()["data"]["items"][0]["payload"]
    assert "provider_signal" not in listed.json()["data"]["items"][0]["payload"]
    assert "agent_run_id" not in listed.json()["data"]["items"][0]["payload"]["agent_brief"]
    assert "artifact_version_hash" not in listed.json()["data"]["items"][0]["payload"]["agent_brief"]
    assert listed.json()["data"]["items"][0]["channels"] == ["in_app"]

    assert read.status_code == 200
    assert read.json()["data"]["updated"] is True
    assert unread.status_code == 200
    assert [item["notification_id"] for item in unread.json()["data"]["items"]] != [first["notification_id"]]
    assert updated_summary.json()["data"]["unread_count"] == 1


def test_api_marks_author_notifications_read(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        runtime = client.app.state.service
        for suffix in ("1", "2"):
            runtime.notifications.insert_notification(
                dedup_key=f"activity:toly:{suffix}",
                rule_id="watched_account_activity",
                severity="info",
                title="activity",
                body="new post",
                entity_type="account",
                entity_key="account:toly",
                author_handle="toly",
                event_id=f"event-toly-{suffix}",
                source_table="events",
                source_id=f"event-toly-{suffix}",
                occurrence_at_ms=1_700_000_000_000 + int(suffix),
                payload={"event_id": f"event-toly-{suffix}"},
                channels=["in_app"],
            )
        runtime.notifications.insert_notification(
            dedup_key="activity:elon",
            rule_id="watched_account_activity",
            severity="info",
            title="activity",
            body="new post",
            entity_type="account",
            entity_key="account:elonmusk",
            author_handle="elonmusk",
            event_id="event-elon",
            source_table="events",
            source_id="event-elon",
            occurrence_at_ms=1_700_000_000_010,
            payload={"event_id": "event-elon"},
            channels=["in_app"],
        )

        headers = {"Authorization": "Bearer secret"}
        read = client.post("/api/notifications/author/toly/read", headers=headers)
        summary = client.get("/api/notification-summary", headers=headers)

    assert read.status_code == 200
    assert read.json()["data"]["updated_count"] == 2
    assert summary.status_code == 200
    assert summary.json()["data"]["unread_count"] == 1
    assert summary.json()["data"]["account_unread_counts"] == {"elonmusk": 1}


def test_api_exposes_notification_delivery_audit(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        runtime = client.app.state.service
        notification = runtime.notifications.insert_notification(
            dedup_key="news:pepe",
            rule_id="news_high_signal",
            severity="high",
            title="PEPE news",
            body="agent news driver",
            entity_type="token",
            entity_key="token:eth:pepe",
            symbol="PEPE",
            source_table="news_items",
            source_id="token:eth:pepe",
            occurrence_at_ms=1_700_000_060_000,
            payload={"decision_class": "driver"},
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


def test_api_deletes_social_enrichment_and_harness_routes(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        headers = {"Authorization": "Bearer secret"}
        deleted = [
            client.get("/api/social-events?window=1h&limit=5", headers=headers),
            client.get("/api/attention-seeds?window=1h&limit=5", headers=headers),
            client.get("/api/harness-snapshots?window=1h&horizon=6h&limit=5", headers=headers),
            client.get("/api/harness-outcomes?window=1h&horizon=6h&limit=5", headers=headers),
            client.get("/api/harness-credits?window=1h&horizon=6h&limit=5", headers=headers),
            client.get("/api/harness-health", headers=headers),
            client.get("/api/harness-score-buckets?horizon=6h", headers=headers),
        ]

    assert [response.status_code for response in deleted] == [404, 404, 404, 404, 404, 404, 404]


def test_api_exposes_signal_pulse_empty_contract_after_hard_cut(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        response = client.get(
            "/api/signal-lab/pulse",
            params={
                "window": "1h",
                "scope": "matched",
                "status": "token_watch",
                "handle": "toly",
                "q": "PEPE",
                "limit": 5,
            },
            headers={"Authorization": "Bearer secret"},
        )
        invalid_status = client.get(
            "/api/signal-lab/pulse",
            params={"status": "direct_token"},
            headers={"Authorization": "Bearer secret"},
        )
        blocked_status = client.get(
            "/api/signal-lab/pulse",
            params={"status": "blocked_low_information"},
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["query"] == {
        "window": "1h",
        "scope": "matched",
        "status": "token_watch",
        "handle": "toly",
        "q": "PEPE",
        "visibility": "public",
    }
    assert data["health"]["pulse_ready"] is False
    assert data["summary"] == {
        "trade_candidate": 0,
        "token_watch": 0,
        "risk_rejected_high_info": 0,
        "decision_route_counts": {"cex": 0, "meme": 0, "research_only": 0},
        "decision_recommendation_counts": {
            "abstain": 0,
            "high_conviction": 0,
            "ignore": 0,
            "trade_candidate": 0,
            "watchlist": 0,
        },
        "decision_abstain_reason_counts": {},
        "decision_error_count": 0,
    }
    assert data["items"] == []
    assert data["returned_count"] == 0
    assert data["has_more"] is False
    assert data["next_cursor"] is None
    assert invalid_status.status_code == 400
    assert invalid_status.json() == {"ok": False, "error": "invalid_status", "field": "status"}
    assert blocked_status.status_code == 400
    assert blocked_status.json() == {"ok": False, "error": "invalid_status", "field": "status"}


def test_api_signal_pulse_reads_pulse_candidates_after_hard_cut(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        with client.app.state.service.repositories() as repos:
            repos.pulse_candidates.upsert_candidate(
                candidate_id="candidate-api-token",
                candidate_type="token_target",
                subject_key="toly",
                target_type="Asset",
                target_id="asset:pepe",
                symbol="PEPE",
                window="1h",
                scope="matched",
                pulse_status="token_watch",
                verdict="token_watch",
                social_phase="ignition",
                candidate_score=0.84,
                score_band="watch",
                trigger_signature="trigger-api-token",
                timeline_signature="timeline-api-token",
                factor_snapshot_json=_pulse_factor_snapshot(score=84),
                gate_json=_pulse_gate(score=84.0),
                decision_route="meme",
                decision_recommendation="watchlist",
                decision_confidence=0.72,
                decision_abstain_reason=None,
                decision_stage_count=3,
                decision_json=_pulse_decision(),
                gate_reasons_json=["fresh_attention"],
                risk_reasons_json=["thin_liquidity"],
                evidence_event_ids_json=["event-api-1"],
                source_event_ids_json=["event-api-1"],
                pulse_version="pulse-v1",
                gate_version="gate-v1",
                prompt_version="prompt-v1",
                schema_version="schema-v1",
                evidence_packet_hash="sha256:candidate-api-token",
                evidence_status="complete",
                decision_status="token_watch",
                display_status="display_token_watch",
                created_at_ms=1_000,
                updated_at_ms=2_000,
            )
            repos.pulse_candidates.upsert_candidate(
                candidate_id="candidate-api-blocked",
                candidate_type="token_target",
                subject_key="toly",
                target_type="Asset",
                target_id="asset:lowinfo",
                symbol="LOW",
                window="1h",
                scope="matched",
                pulse_status="blocked_low_information",
                verdict="blocked_low_information",
                social_phase="unknown",
                candidate_score=0.1,
                score_band="blocked",
                trigger_signature="trigger-api-blocked",
                timeline_signature="timeline-api-blocked",
                factor_snapshot_json=_pulse_factor_snapshot(
                    symbol="LOW",
                    target_id="asset:lowinfo",
                    score=10,
                    blocked_reasons=["low_information"],
                ),
                gate_json=_pulse_gate(
                    pulse_status="blocked_low_information",
                    score=10.0,
                    blocked_reasons=["low_information"],
                ),
                decision_route="meme",
                decision_recommendation="abstain",
                decision_confidence=0.0,
                decision_abstain_reason="low_information",
                decision_stage_count=1,
                decision_json=_pulse_decision(
                    "信息不足。",
                    recommendation="abstain",
                    abstain_reason="low_information",
                ),
                gate_reasons_json=["low_information"],
                risk_reasons_json=["low_information"],
                evidence_event_ids_json=["event-api-2"],
                source_event_ids_json=["event-api-2"],
                pulse_version="pulse-v1",
                gate_version="gate-v1",
                prompt_version="prompt-v1",
                schema_version="schema-v1",
                created_at_ms=900,
                updated_at_ms=3_000,
            )
            repos.pulse_candidates.upsert_candidate(
                candidate_id="candidate-api-blocked-2",
                candidate_type="token_target",
                subject_key="toly",
                target_type="Asset",
                target_id="asset:lowinfo2",
                symbol="LOW2",
                window="1h",
                scope="matched",
                pulse_status="blocked_low_information",
                verdict="blocked_low_information",
                social_phase="unknown",
                candidate_score=0.1,
                score_band="blocked",
                trigger_signature="trigger-api-blocked-2",
                timeline_signature="timeline-api-blocked-2",
                factor_snapshot_json=_pulse_factor_snapshot(
                    symbol="LOW2",
                    target_id="asset:lowinfo2",
                    score=10,
                    market_status="missing",
                    blocked_reasons=["low_information"],
                ),
                gate_json=_pulse_gate(
                    pulse_status="blocked_low_information",
                    score=10.0,
                    blocked_reasons=["low_information"],
                ),
                decision_route="meme",
                decision_recommendation="abstain",
                decision_confidence=0.0,
                decision_abstain_reason="low_information",
                decision_stage_count=1,
                decision_json=_pulse_decision(
                    "信息不足。",
                    recommendation="abstain",
                    abstain_reason="low_information",
                ),
                gate_reasons_json=["low_information"],
                risk_reasons_json=["low_information"],
                evidence_event_ids_json=["event-api-3"],
                source_event_ids_json=["event-api-3"],
                pulse_version="pulse-v1",
                gate_version="gate-v1",
                prompt_version="prompt-v1",
                schema_version="schema-v1",
                created_at_ms=800,
                updated_at_ms=2_500,
            )

        response = client.get(
            "/api/signal-lab/pulse",
            params={"window": "1h", "scope": "matched", "limit": 1},
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["summary"]["token_watch"] == 1
    assert "blocked_low_information" not in data["summary"]
    assert data["health"]["pulse_ready"] is True
    assert data["health"]["candidate_count"] == 3
    assert data["health"]["blocked_low_information_count"] == 2
    assert data["health"]["market_ready_rate"] == 1.0
    assert data["returned_count"] == 1
    assert data["items"][0]["candidate_id"] == "candidate-api-token"
    assert data["items"][0]["decision"]["summary_zh"] == "PEPE 社交热度显著上升。"
    assert "agent_recommendation" not in data["items"][0]
    assert data["items"][0]["fact_card"]["market_status"] == "ready"
    assert "radar_score_json" not in data["items"][0]
    assert "market_context_json" not in data["items"][0]
    assert "thesis_json" not in data["items"][0]
    assert "kind" not in data["items"][0]


def test_api_signal_pulse_status_filter_uses_public_display_status_after_evidence_cut(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        with client.app.state.service.repositories() as repos:
            repos.pulse_candidates.upsert_candidate(
                candidate_id="candidate-display-watch",
                candidate_type="token_target",
                subject_key="risk-gate-watch",
                target_type="Asset",
                target_id="asset:watch",
                symbol="WATCH",
                window="1h",
                scope="all",
                pulse_status="risk_rejected_high_info",
                verdict="risk_rejected_high_info",
                social_phase="ignition",
                candidate_score=82.0,
                score_band="watch",
                trigger_signature="trigger-display-watch",
                timeline_signature="timeline-display-watch",
                factor_snapshot_json=_pulse_factor_snapshot(symbol="WATCH", target_id="asset:watch", score=82),
                gate_json=_pulse_gate(pulse_status="risk_rejected_high_info", score=82.0),
                decision_route="meme",
                decision_recommendation="ignore",
                decision_confidence=0.3,
                decision_abstain_reason=None,
                decision_stage_count=6,
                decision_json=_pulse_decision("WATCH 只能进入观察。", recommendation="ignore"),
                gate_reasons_json=["duplicate_text_share_high"],
                risk_reasons_json=["duplicate_text_share_high"],
                evidence_event_ids_json=["event-display-watch"],
                source_event_ids_json=["event-display-watch"],
                pulse_version="pulse-v1",
                gate_version="gate-v1",
                prompt_version="prompt-v1",
                schema_version="schema-v1",
                evidence_packet_hash="sha256:display-watch",
                evidence_status="complete",
                decision_status="token_watch",
                display_status="display_token_watch",
                created_at_ms=1_000,
                updated_at_ms=3_000,
            )
            repos.pulse_candidates.upsert_candidate(
                candidate_id="candidate-hidden-old-watch",
                candidate_type="token_target",
                subject_key="hidden-old-watch",
                target_type="Asset",
                target_id="asset:hidden",
                symbol="HIDDEN",
                window="1h",
                scope="all",
                pulse_status="token_watch",
                verdict="token_watch",
                social_phase="ignition",
                candidate_score=75.0,
                score_band="watch",
                trigger_signature="trigger-hidden-watch",
                timeline_signature="timeline-hidden-watch",
                factor_snapshot_json=_pulse_factor_snapshot(symbol="HIDDEN", target_id="asset:hidden", score=75),
                gate_json=_pulse_gate(pulse_status="token_watch", score=75.0),
                decision_route="meme",
                decision_recommendation="abstain",
                decision_confidence=0.0,
                decision_abstain_reason="data_completeness_below_hard_gate",
                decision_stage_count=2,
                decision_json=_pulse_decision("HIDDEN 证据不足。", recommendation="abstain"),
                gate_reasons_json=["fresh_attention"],
                risk_reasons_json=[],
                evidence_event_ids_json=["event-hidden-watch"],
                source_event_ids_json=["event-hidden-watch"],
                pulse_version="pulse-v1",
                gate_version="gate-v1",
                prompt_version="prompt-v1",
                schema_version="schema-v1",
                evidence_packet_hash="sha256:hidden-watch",
                evidence_status="insufficient",
                decision_status="abstain",
                display_status="hidden_insufficient_evidence",
                created_at_ms=900,
                updated_at_ms=2_500,
            )

        response = client.get(
            "/api/signal-lab/pulse",
            params={"window": "1h", "scope": "all", "status": "token_watch", "limit": 10},
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["summary"]["token_watch"] == 1
    assert data["summary"]["risk_rejected_high_info"] == 0
    assert data["returned_count"] == 1
    assert data["items"][0]["candidate_id"] == "candidate-display-watch"
    assert "pulse_status" not in data["items"][0]
    assert data["items"][0]["display_status"] == "display_token_watch"


def test_api_asset_flow_scope_filters_watched_mentions(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        now_ms = int(time.time() * 1000)
        rebuild_now_ms = now_ms + TOKEN_RADAR_TEST_REBUILD_OFFSET_MS
        watched_event = make_token_event(
            "event-watched",
            symbol="PEPE",
            address="0x6982508145454ce325ddbe47a25d4ec3d2311933",
            text="$PEPE watched",
            received_at_ms=now_ms - 1_000,
        )
        public_event = make_token_event(
            "event-public",
            symbol="BONK",
            address="0x44b28991b167582f18ba0259e0173176ca125505",
            handle="anon",
            text="$BONK public",
            received_at_ms=now_ms - 900,
        )
        client.app.state.service.ingest.ingest_event(watched_event, is_watched=True)
        client.app.state.service.ingest.ingest_event(public_event, is_watched=False)
        rebuild_token_radar(client, now_ms=rebuild_now_ms)

        headers = {"Authorization": "Bearer secret"}
        all_flow = client.get("/api/token-radar", params={"window": "5m", "scope": "all"}, headers=headers)
        watched_flow = client.get("/api/token-radar", params={"window": "5m", "scope": "matched"}, headers=headers)

    assert all_flow.status_code == 200
    assert {item["target"]["symbol"] for item in all_flow.json()["data"]["targets"]} == {"PEPE", "BONK"}

    assert watched_flow.status_code == 200
    assert watched_flow.json()["data"]["scope"] == "matched"
    assert [item["target"]["symbol"] for item in watched_flow.json()["data"]["targets"]] == ["PEPE"]


def test_api_live_market_returns_unsupported_without_live_gateway(tmp_path):
    settings = make_settings(tmp_path)
    settings.workers.live_price_gateway.enabled = False
    app = create_app(settings=settings, start_collector=False)

    with TestClient(app) as client:
        response = client.get(
            "/api/live-market",
            params={"target_type": "Asset", "target_id": "asset:missing"},
            headers={"Authorization": "Bearer secret"},
        )
        missing = client.get("/api/live-market", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["target_type"] == "Asset"
    assert data["target_id"] == "asset:missing"
    assert data["status"] == "unsupported"
    assert missing.status_code == 400
    assert missing.json() == {"ok": False, "error": "target_required", "field": "target_id"}


def test_api_token_case_returns_dossier_for_resolved_asset(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        target = seed_resolved_asset_with_event(client, symbol="HANSA")
        response = client.get(
            "/api/token-case",
            params={
                "target_type": target["target_type"],
                "target_id": target["target_id"],
                "window": "24h",
                "scope": "all",
                "posts_limit": 2,
            },
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["target"]["target_type"] == "Asset"
    assert "market_live" in body["data"]
    assert body["data"]["timeline"]["market_candles"]["target_type"] == "Asset"
    assert "radar_item" not in body["data"]
    legacy_market_field = "market_overlay"
    assert legacy_market_field not in body["data"]
    assert "agent_brief" not in body["data"]
    assert body["data"]["discussion_digest"]["status"] in {"pending", "semantic_unavailable"}
    assert body["data"]["discussion_digest"]["data_gaps"]
    assert body["data"]["posts"]["items"][0]["post_quality"]["contributions"]
    assert body["data"]["posts"]["items"][0]["semantic"]["status"] == "pending"
    assert body["data"]["posts"]["items"][0]["semantic"]["data_gaps"]


def test_api_token_case_returns_404_when_target_not_found(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        response = client.get(
            "/api/token-case",
            params={"target_type": "Asset", "target_id": "asset:solana:token:missing"},
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 404
    assert response.json() == {"ok": False, "error": "target_not_found"}


def test_api_token_case_requires_auth(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        response = client.get("/api/token-case", params={"target_type": "Asset", "target_id": "asset:x"})

    assert response.status_code == 401
    assert response.json() == {"ok": False, "error": "unauthorized"}


def test_api_token_case_rejects_invalid_window_and_scope(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        bad_window = client.get(
            "/api/token-case",
            params={"target_type": "Asset", "target_id": "asset:x", "window": "7d"},
            headers={"Authorization": "Bearer secret"},
        )
        bad_scope = client.get(
            "/api/token-case",
            params={"target_type": "Asset", "target_id": "asset:x", "scope": "private"},
            headers={"Authorization": "Bearer secret"},
        )

    assert bad_window.status_code == 400
    assert bad_window.json() == {"ok": False, "error": "invalid_window", "field": "window"}
    assert bad_scope.status_code == 400
    assert bad_scope.json() == {"ok": False, "error": "invalid_scope", "field": "scope"}


def test_api_token_case_matches_search_inspect_token_result_shape(tmp_path, monkeypatch):
    now_ms = 1_778_562_000_000
    monkeypatch.setattr("parallax.app.surfaces.api.routes_search._now_ms", lambda: now_ms)
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        target = seed_resolved_asset_with_event(client, symbol="HANSA", now_ms=now_ms - 60_000)
        token_case = client.get(
            "/api/token-case",
            params={
                "target_type": target["target_type"],
                "target_id": target["target_id"],
                "window": "24h",
                "scope": "all",
            },
            headers={"Authorization": "Bearer secret"},
        )
        inspect = client.get(
            "/api/search/inspect",
            params={"q": "$HANSA", "window": "24h", "scope": "all"},
            headers={"Authorization": "Bearer secret"},
        )

    assert token_case.status_code == 200
    assert inspect.status_code == 200
    assert inspect.json()["data"]["token_result"] == token_case.json()["data"]


def test_api_target_posts_returns_full_post_pages_and_requires_target_identity(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        base_ms = int(time.time() * 1000)
        rebuild_now_ms = base_ms + TOKEN_RADAR_TEST_REBUILD_OFFSET_MS
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
        rebuild_token_radar(client, now_ms=rebuild_now_ms)

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
    assert first_body["items"][0]["semantic"]["status"] in {"pending", "semantic_unavailable"}
    assert first_body["items"][0]["semantic"]["data_gaps"]
    assert first_body["query"]["target_id"] == target_id
    assert first_body["items"][0]["post_quality"]["score_version"] == "post_quality_v1"
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
        rebuild_now_ms = base_ms + TOKEN_RADAR_TEST_REBUILD_OFFSET_MS
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
        rebuild_token_radar(client, now_ms=rebuild_now_ms)

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
    data = body["data"]
    assert data["handles"] == ["toly", "elonmusk"]
    manifest_names = {manifest.name for manifest in all_worker_manifests()}
    assert manifest_names.issubset(data["workers"])
    assert set(data["worker_lanes"]) >= {"ingest", "projection", "agent"}
    assert "collector" not in data
    assert "enrichment" not in data
    assert "notifications" not in data

    collector = data["workers"]["collector"]
    assert collector["enabled"] is False
    assert collector["running"] is False
    assert collector["queue_depth"] is None
    assert collector["details"]["frames_received"] == 0
    assert collector["details"]["matched_twitter_events"] == 0
    assert collector["details"]["snapshot_gate_outcomes"] == data["snapshot_gate"]


def test_api_status_remains_queryable_when_readiness_is_degraded(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)

    with TestClient(app) as client:
        client.app.state.service.db.api_pool.close()
        response = client.get("/api/status", headers={"Authorization": "Bearer secret"})

    body = response.json()
    assert response.status_code == 200
    assert body["ok"] is True
    assert body["data"]["ok"] is False
    assert "database_unhealthy" in body["data"]["reasons"]


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


def _seed_displayable_candidate(
    app,
    *,
    candidate_id: str,
    display_status: str = "display_token_watch",
    decision_status: str = "token_watch",
    evidence_status: str = "complete",
) -> None:
    """Seed one displayable pulse_candidates row for HTTP-layer tests."""
    with app.state.service.repositories() as repos:
        repos.pulse_candidates.upsert_candidate(
            candidate_id=candidate_id,
            candidate_type="token_target",
            subject_key="toly",
            window="1h",
            scope="all",
            pulse_status="token_watch",
            verdict="token_watch",
            social_phase="ignition",
            candidate_score=0.82,
            score_band="watch",
            trigger_signature="trigger-sig",
            timeline_signature="timeline-sig",
            pulse_version="pulse-v1",
            gate_version="gate-v1",
            prompt_version="prompt-v1",
            schema_version="schema-v1",
            factor_snapshot_json=_pulse_factor_snapshot(),
            gate_json=_pulse_gate(score=82.0),
            decision_route="meme",
            decision_recommendation="watchlist",
            decision_confidence=0.72,
            decision_abstain_reason=None,
            decision_stage_count=3,
            decision_json=_pulse_decision("test"),
            target_type="Asset",
            target_id="asset:pepe",
            symbol="PEPE",
            gate_reasons_json=["fresh_attention"],
            risk_reasons_json=[],
            evidence_event_ids_json=["event-1"],
            source_event_ids_json=["event-1"],
            evidence_packet_hash="sha256:test-packet",
            evidence_status=evidence_status,
            decision_status=decision_status,
            display_status=display_status,
            claim_verification_json={"valid": True},
            evidence_gate_json={"evidence_status": "complete", "hard_blocked": False},
        )


def test_api_signal_pulse_by_id_returns_item(tmp_path):
    settings = make_settings(tmp_path)
    app = create_app(settings=settings, start_collector=False)
    with TestClient(app) as client:
        _seed_displayable_candidate(client.app, candidate_id="cand-real")
        response = client.get(
            "/api/signal-lab/pulse/cand-real",
            headers={"Authorization": "Bearer secret"},
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["data"]["candidate_id"] == "cand-real"
    assert "pulse_status" not in payload["data"]
    assert "stage_count" not in payload["data"]["decision"]
    assert "claim_verification" not in payload["data"]
    assert "evidence_gate" not in payload["data"]
    assert payload["data"]["display_status"] == "display_token_watch"


def test_api_signal_pulse_hidden_visibility_returns_hidden_items_and_detail(tmp_path):
    settings = make_settings(tmp_path)
    app = create_app(settings=settings, start_collector=False)
    with TestClient(app) as client:
        _seed_displayable_candidate(
            client.app,
            candidate_id="cand-hidden",
            display_status="hidden_invalid_output",
            decision_status="invalid",
        )
        list_response = client.get(
            "/api/signal-lab/pulse",
            params={"window": "1h", "scope": "all", "visibility": "hidden"},
            headers={"Authorization": "Bearer secret"},
        )
        hidden_detail = client.get(
            "/api/signal-lab/pulse/cand-hidden",
            params={"visibility": "hidden"},
            headers={"Authorization": "Bearer secret"},
        )
        public_detail = client.get(
            "/api/signal-lab/pulse/cand-hidden",
            headers={"Authorization": "Bearer secret"},
        )

    assert list_response.status_code == 200
    list_data = list_response.json()["data"]
    assert list_data["query"]["visibility"] == "hidden"
    assert list_data["returned_count"] == 1
    assert list_data["items"][0]["candidate_id"] == "cand-hidden"
    assert list_data["items"][0]["display_status"] == "hidden_invalid_output"
    assert hidden_detail.status_code == 200
    assert hidden_detail.json()["data"]["display_status"] == "hidden_invalid_output"
    assert public_detail.status_code == 404


def test_api_signal_pulse_by_id_does_not_expose_run_step_audit(tmp_path):
    settings = make_settings(tmp_path)
    app = create_app(settings=settings, start_collector=False)
    with TestClient(app) as client:
        with client.app.state.service.repositories() as repos:
            repos.pulse_jobs.enqueue_job(
                job_id="job-stages",
                candidate_id="cand-stages",
                candidate_type="token_target",
                subject_key="toly",
                target_type="Asset",
                target_id="asset:pepe",
                window="1h",
                scope="all",
                trigger_signature="trigger-sig",
                timeline_signature="timeline-sig",
                priority=1,
                status="done",
                max_attempts=3,
            )
            repos.pulse_runs.insert_agent_run(
                run_id="run-stages",
                job_id="job-stages",
                candidate_id="cand-stages",
                provider="litellm",
                model="qwen3.6",
                workflow_name="pulse-decision",
                agent_name="pulse-agent",
                artifact_version_hash="hash",
                prompt_version="prompt-v1",
                schema_version="schema-v1",
                runtime_version="runtime-v1",
                runtime_hash="runtime-hash",
                input_hash="input-hash",
                status="ok",
                outcome="completed",
                decision_route="meme",
                decision_stage_count=1,
            )
        _seed_displayable_candidate(client.app, candidate_id="cand-stages")
        with client.app.state.service.repositories() as repos:
            for stage, response_json, started_at_ms, finished_at_ms in [
                ("pulse_decision", {"confidence": 0.35, "recommendation": "trade_candidate"}, 100, 250),
            ]:
                repos.pulse_runs.insert_agent_run_step(
                    step_id=f"run-stages:{stage}:0",
                    run_id="run-stages",
                    stage=stage,
                    route="meme",
                    attempt_index=0,
                    provider="litellm",
                    model="qwen3.6",
                    prompt_version="prompt-v1",
                    schema_version="schema-v1",
                    input_json={},
                    prompt_text="",
                    response_json=response_json,
                    latency_ms=finished_at_ms - started_at_ms,
                    started_at_ms=started_at_ms,
                    finished_at_ms=finished_at_ms,
                )
        response = client.get(
            "/api/signal-lab/pulse/cand-stages",
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["candidate_id"] == "cand-stages"
    assert "agent_run_id" not in data
    assert "stages" not in data


def test_social_events_by_ids_returns_full_records(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)
    ids = ["event-watched", "event-public"]
    with TestClient(app) as client:
        _seed_social_event_batch(client.app)
        response = client.get(
            "/api/events/by-ids",
            params={"ids": ",".join(ids)},
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 200
    events = response.json()["data"]["events"]
    assert {event["event_id"] for event in events} == set(ids)
    by_handle = {event["author_handle"]: event for event in events}
    assert by_handle["watched_kol"]["author_watched"] is True
    assert by_handle["random_dude"]["author_watched"] is False
    assert by_handle["watched_kol"]["source_provider"] == "gmgn"
    assert by_handle["watched_kol"]["channel"] == "twitter_monitor_basic"


def test_social_events_by_ids_skips_missing(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)
    with TestClient(app) as client:
        _seed_social_event_batch(client.app)
        response = client.get(
            "/api/events/by-ids",
            params={"ids": "event-watched,nonexistent-id"},
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 200
    body = response.json()
    assert [event["event_id"] for event in body["data"]["events"]] == ["event-watched"]
    assert body["data"]["not_found"] == ["nonexistent-id"]


def test_social_events_by_ids_rejects_too_many(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)
    huge = ",".join(f"id-{i}" for i in range(201))
    with TestClient(app) as client:
        response = client.get(
            "/api/events/by-ids",
            params={"ids": huge},
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 400
    assert response.json()["error"] == "too_many_ids"


def test_social_events_by_ids_requires_ids(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)
    with TestClient(app) as client:
        response = client.get(
            "/api/events/by-ids",
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 400
    assert response.json()["error"] == "ids_required"


def _seed_social_event_batch(app) -> None:
    with app.state.service.repositories() as repos:
        account_quality = AccountQualityRepository(repos.conn)
        account_quality.upsert_profile(
            handle="watched_kol",
            first_seen_ms=1_700_000_000_000,
            latest_seen_ms=1_700_000_100_000,
            follower_max=12_000,
            watched_status="watched",
        )
        account_quality.upsert_profile(
            handle="random_dude",
            first_seen_ms=1_700_000_000_000,
            latest_seen_ms=1_700_000_100_000,
            follower_max=200,
            watched_status="public",
        )
        repos.evidence.insert_event(
            make_event("event-watched", handle="watched_kol", text="$PEPE watched", received_at_ms=1_700_000_000_000),
            is_watched=True,
        )
        repos.evidence.insert_event(
            make_event("event-public", handle="random_dude", text="$PEPE public", received_at_ms=1_700_000_010_000),
            is_watched=False,
        )


def test_api_signal_pulse_by_id_returns_404_when_missing(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)
    with TestClient(app) as client:
        response = client.get(
            "/api/signal-lab/pulse/ghost-id",
            headers={"Authorization": "Bearer secret"},
        )
    assert response.status_code == 404
    assert response.json() == {"ok": False, "error": "not_found", "field": "candidate_id"}


def test_api_signal_pulse_by_id_rejects_blank(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)
    with TestClient(app) as client:
        response = client.get(
            "/api/signal-lab/pulse/%20",
            headers={"Authorization": "Bearer secret"},
        )
    assert response.status_code == 400
    assert response.json() == {"ok": False, "error": "invalid_candidate_id", "field": "candidate_id"}


def test_api_signal_pulse_by_id_requires_auth(tmp_path):
    app = create_app(settings=make_settings(tmp_path), start_collector=False)
    with TestClient(app) as client:
        response = client.get("/api/signal-lab/pulse/cand-1")
    assert response.status_code == 401
