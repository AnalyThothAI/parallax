from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from gmgn_twitter_intel.app.surfaces.api.exceptions import (
    ApiBadRequest,
    ApiUnauthorized,
    api_bad_request_response,
    api_unauthorized_response,
)
from gmgn_twitter_intel.app.surfaces.api.http import create_api_router


def test_signal_pulse_api_uses_fake_runtime_without_postgres():
    pulse = FakeSignalPulseReadRepository()
    app = _app(pulse)

    with TestClient(app) as client:
        response = client.get(
            "/api/signal-lab/pulse",
            params={"window": "1h", "scope": "matched", "q": "PEPE", "handle": "toly", "limit": 5},
            headers={"Authorization": "Bearer secret"},
        )
        invalid = client.get(
            "/api/signal-lab/pulse",
            params={"status": "blocked_low_information"},
            headers={"Authorization": "Bearer secret"},
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert pulse.list_calls == [
        {
            "window": "1h",
            "scope": "matched",
            "status": None,
            "limit": 5,
            "cursor": None,
            "q": "PEPE",
            "handle": "toly",
            "displayable_only": True,
        }
    ]
    assert pulse.summary_calls == [{"window": "1h", "scope": "matched", "q": "PEPE", "handle": "toly"}]
    assert data["health"]["agent_worker_running"] is True
    assert data["summary"]["token_watch"] == 1
    assert data["items"][0]["candidate_id"] == "candidate-fake"
    assert data["items"][0]["decision"]["summary_zh"] == "PEPE 社交热度显著上升。"
    assert "agent_recommendation" not in data["items"][0]
    assert data["items"][0]["factor_snapshot"]["schema_version"] == "token_factor_snapshot_v3_social_attention"
    assert "radar_score_json" not in data["items"][0]
    assert "market_context_json" not in data["items"][0]
    assert "thesis_json" not in data["items"][0]
    assert "kind" not in data["items"][0]
    assert invalid.status_code == 400
    assert invalid.json() == {"ok": False, "error": "invalid_status", "field": "status"}


def test_signal_pulse_api_defaults_to_produced_agent_window_and_scope():
    pulse = FakeSignalPulseReadRepository()
    app = _app(pulse)

    with TestClient(app) as client:
        response = client.get("/api/signal-lab/pulse", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["query"]["window"] == "1h"
    assert data["query"]["scope"] == "all"
    assert pulse.list_calls[0]["window"] == "1h"
    assert pulse.list_calls[0]["scope"] == "all"
    assert pulse.summary_calls[0] == {"window": "1h", "scope": "all", "q": None, "handle": None}


class FakeSignalPulseReadRepository:
    def __init__(self):
        self.list_calls: list[dict[str, object]] = []
        self.summary_calls: list[dict[str, object]] = []

    def list_candidates(
        self,
        window,
        scope,
        status=None,
        limit=50,
        cursor=None,
        q=None,
        handle=None,
        displayable_only=False,
    ):
        self.list_calls.append(
            {
                "window": window,
                "scope": scope,
                "status": status,
                "limit": limit,
                "cursor": cursor,
                "q": q,
                "handle": handle,
                "displayable_only": displayable_only,
            }
        )
        return {
            "items": [
                {
                    "candidate_id": "candidate-fake",
                    "candidate_type": "token_target",
                    "subject_key": "toly",
                    "target_type": "Asset",
                    "target_id": "asset:pepe",
                    "symbol": "PEPE",
                    "window": window,
                    "scope": scope,
                    "pulse_status": "token_watch",
                    "display_status": "display_token_watch",
                    "evidence_status": "complete",
                    "verdict": "token_watch",
                    "social_phase": "ignition",
                    "candidate_score": 0.84,
                    "score_band": "watch",
                    "factor_snapshot_json": _pulse_factor_snapshot(),
                    "decision_route": "meme",
                    "decision_recommendation": "watchlist",
                    "decision_confidence": 0.72,
                    "decision_abstain_reason": None,
                    "decision_stage_count": 3,
                    "decision_json": _pulse_decision(),
                    "gate_json": _pulse_gate(score=0.84),
                    "gate_reasons_json": ["fresh_attention"],
                    "risk_reasons_json": [],
                    "last_edge_events_json": ["pulse_status_changed"],
                    "evidence_event_ids_json": ["event-fake"],
                    "source_event_ids_json": ["event-fake"],
                    "evidence_packet_hash": "sha256:fake-packet",
                    "agent_run_id": "run-fake",
                    "pulse_version": "pulse-v1",
                    "gate_version": "gate-v1",
                    "prompt_version": "prompt-v1",
                    "schema_version": "schema-v1",
                    "created_at_ms": 1_000,
                    "updated_at_ms": 2_000,
                }
            ],
            "next_cursor": None,
        }

    def pulse_summary(self, window, scope, q=None, handle=None):
        self.summary_calls.append({"window": window, "scope": scope, "q": q, "handle": handle})
        return {
            "summary": {
                "trade_candidate": 0,
                "token_watch": 1,
                "risk_rejected_high_info": 0,
                "blocked_low_information": 0,
            },
            "candidate_count": 1,
            "blocked_low_information_count": 0,
            "dead_job_count": 0,
            "market_ready_rate": 1.0,
        }


class FakeRepositoryContext:
    def __init__(self, pulse_read):
        self.pulse_read = pulse_read
        self.pulse_runs = pulse_read

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeRuntime:
    def __init__(self, pulse_read):
        self.settings = type("FakeSettings", (), {"ws_token": "secret"})()
        self.pulse_read = pulse_read
        self.workers = {
            "pulse_candidate": SimpleNamespace(
                status_payload=lambda: {
                    "enabled": True,
                    "running": True,
                    "last_started_at_ms": None,
                    "last_finished_at_ms": None,
                    "last_result": None,
                    "last_error": None,
                }
            )
        }
        self.scheduler = SimpleNamespace(
            tasks={},
            status_payload=lambda: {"pulse_candidate": self.workers["pulse_candidate"].status_payload()},
            unhealthy_reasons=lambda: [],
        )

    def repositories(self):
        return FakeRepositoryContext(self.pulse_read)


def _app(pulse_read):
    app = FastAPI()
    app.add_exception_handler(ApiUnauthorized, api_unauthorized_response)
    app.add_exception_handler(ApiBadRequest, api_bad_request_response)
    app.include_router(create_api_router(lambda _: ({"ok": True}, 200)))
    app.state.service = FakeRuntime(pulse_read)
    return app


def _pulse_factor_snapshot() -> dict[str, object]:
    observation = {
        "target_type": "Asset",
        "target_id": "asset:pepe",
        "source": "event_anchor",
        "provider": "okx",
        "pricefeed_id": None,
        "price_usd": 0.42,
        "price_quote": None,
        "quote_symbol": "USD",
        "price_basis": "usd",
        "market_cap_usd": 120_000,
        "liquidity_usd": 55_000,
        "holders": 800,
        "volume_24h_usd": 2_300_000,
        "open_interest_usd": None,
        "observed_at_ms": 1_700_000_000_000,
        "received_at_ms": 1_700_000_000_000,
        "raw_payload_hash": None,
    }
    return {
        "schema_version": "token_factor_snapshot_v3_social_attention",
        "subject": {
            "target_type": "Asset",
            "target_id": "asset:pepe",
            "target_market_type": "dex",
            "symbol": "PEPE",
            "chain": "sol",
        },
        "market": {
            "event_anchor": observation,
            "decision_latest": {**observation, "source": "decision_latest"},
            "readiness": {
                "anchor_status": "ready",
                "latest_status": "live",
                "dex_floor_status": "ready",
                "missing_fields": [],
                "stale_fields": [],
            },
        },
        "gates": {
            "eligible_for_high_alert": True,
            "blocked_reasons": [],
            "risk_reasons": [],
            "max_decision": "high_alert",
        },
        "data_health": {"identity": "ready", "market": "ready", "social": "ready", "alpha": "ready"},
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
                "facts": {"price_change_status": "fresh"},
                "factors": {},
            },
        },
        "normalization": {"status": "pending_cross_section"},
        "composite": {
            "rank_score": 82,
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


def _pulse_gate(*, score: float = 82.0) -> dict[str, object]:
    return {
        "pulse_status": "token_watch",
        "verdict": "token_watch",
        "candidate_score": score,
        "score_band": "watch",
        "gate_reasons": ["factor_snapshot_watch_gate_passed"],
        "risk_reasons": [],
        "hard_risks": [],
        "max_recommendation": "research",
        "eligible_for_high_alert": True,
        "blocked_reasons": [],
    }


def _pulse_decision() -> dict[str, object]:
    return {
        "route": "meme",
        "recommendation": "watchlist",
        "confidence": 0.72,
        "abstain_reason": None,
        "summary_zh": "PEPE 社交热度显著上升。",
        "invalidation_conditions": ["讨论快速降温。"],
        "residual_risks": ["价格响应仍可能变化。"],
        "evidence_event_ids": ["event-api-1"],
    }
