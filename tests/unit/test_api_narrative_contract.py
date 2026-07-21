from __future__ import annotations

import json
from contextlib import nullcontext
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from parallax.app.surfaces.api import routes_search
from parallax.app.surfaces.api.schemas import TokenCaseData, TokenRadarData
from parallax.domains.token_intel.scoring.factor_snapshot import build_token_factor_snapshot


def test_token_case_route_passes_token_radar_repository_to_read_model(monkeypatch) -> None:
    runtime = _runtime()
    factory_kwargs: list[dict[str, Any]] = []

    def service_factory(**kwargs: Any) -> Any:
        factory_kwargs.append(kwargs)
        return SimpleNamespace(dossier=lambda **_call: _token_case_payload())

    monkeypatch.setattr(routes_search, "_authenticated_runtime", lambda _request: runtime)
    monkeypatch.setattr(routes_search, "_now_ms", lambda: 1_778_562_000_000)
    monkeypatch.setattr(routes_search, "TokenCaseService", service_factory)

    response = routes_search.token_case(
        SimpleNamespace(query_params={}),
        target_type="Asset",
        target_id="asset-1",
        window="1h",
        scope="all",
        posts_limit=5,
    )

    assert _body(response)["data"]["narrative_admission"] == _admission()
    assert factory_kwargs[0]["token_radar"] is runtime.repo.token_radar


def test_public_narrative_schema_remains_admission_only() -> None:
    case = TokenCaseData.model_validate(_token_case_payload())
    radar = TokenRadarData.model_validate(_token_radar_payload(_radar_row()))

    assert case.narrative_admission.status == "admitted"
    assert case.narrative_admission.coverage.independent_authors == 4
    assert radar.targets[0].narrative_admission is not None
    assert radar.targets[0].narrative_admission.currentness.display_status == "current"
    serialized = radar.model_dump()
    assert "narrative_delta" not in serialized["targets"][0]
    assert "narrative_clusters" not in serialized["targets"][0]


def test_token_radar_schema_rejects_duplicate_public_row_fields() -> None:
    row = _radar_row()
    row["target"] = {"target_id": "asset-1"}

    with pytest.raises(ValidationError, match="target"):
        TokenRadarData.model_validate(_token_radar_payload(row))


def test_token_radar_schema_rejects_resolution_aliases() -> None:
    row = _radar_row()
    row["resolution"]["reasons"] = ["legacy"]

    with pytest.raises(ValidationError, match="reasons"):
        TokenRadarData.model_validate(_token_radar_payload(row))


def test_token_radar_schema_rejects_factor_subject_aliases_and_unknown_decisions() -> None:
    row = _radar_row()
    row["factor_snapshot"]["subject"]["chain_id"] = "eip155:1"
    row["factor_snapshot"]["composite"]["recommended_decision"] = "investigate"

    with pytest.raises(ValidationError, match=r"chain_id|recommended_decision"):
        TokenRadarData.model_validate(_token_radar_payload(row))


def _runtime() -> SimpleNamespace:
    repo = SimpleNamespace(
        token_profiles=object(),
        token_radar=object(),
        token_targets=object(),
    )
    return SimpleNamespace(repo=repo, repositories=lambda: nullcontext(repo))


def _token_radar_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "window": "1h",
        "scope": "all",
        "venue": "all",
        "targets": [row],
        "attention": [],
        "projection": _token_radar_projection(),
    }


def _token_radar_projection() -> dict[str, Any]:
    return {
        "status": "fresh",
        "version": "token_radar_v1",
        "source": "token_radar_current_rows",
        "venue": "all",
        "reason": None,
        "latest_attempt_status": "ready",
        "row_count": 1,
        "source_rows": 1,
        "source_max_received_at_ms": 1_778_562_000_000,
        "source_frontier_ms": 1_778_562_000_000,
        "computed_at_ms": 1_778_562_000_000,
        "error": None,
        "anchor_coverage": {"status": "ready", "ready": 1, "missing": 0, "total": 1},
        "quality_status": "ready",
        "degraded_reasons": [],
        "unresolved": {
            "identity_missing_count": 0,
            "nil_count": 0,
            "ambiguous_count": 0,
            "sample_symbols": [],
        },
    }


def _token_case_payload() -> dict[str, Any]:
    return {
        "target": {"target_type": "Asset", "target_id": "asset-1"},
        "profile": {"status": "pending"},
        "timeline": {"query": {"scope": "all"}},
        "posts": {"query": {"scope": "all"}, "items": []},
        "narrative_admission": _admission(),
        "market_live": {"status": "missing"},
    }


def _admission() -> dict[str, Any]:
    return {
        "status": "admitted",
        "reason": "hot_rank",
        "is_current": True,
        "computed_at_ms": 1_778_562_000_000,
        "currentness": {"display_status": "current", "reason": "hot_rank"},
        "coverage": {"source_mentions": 10, "independent_authors": 4},
        "data_gaps": [],
    }


def _radar_row() -> dict[str, Any]:
    return {
        "intent": {"intent_id": "intent-1", "event_id": "event-1", "evidence": []},
        "radar": {"rank": 1, "listed_at_ms": 1_778_562_000_000},
        "resolution": {
            "status": "EXACT",
            "target_type": "Asset",
            "target_id": "asset-1",
            "pricefeed_id": None,
            "reason_codes": [],
            "candidate_ids": [],
            "lookup_keys": [],
            "discovery": [],
        },
        "quality": {"status": "ready", "degraded_reasons": []},
        "narrative_admission": _admission(),
        "factor_snapshot": build_token_factor_snapshot(
            target={
                "target_type": "Asset",
                "target_id": "asset-1",
                "symbol": "ONE",
                "target_market_type": "dex",
                "chain": "eip155:1",
                "address": "0xabc",
                "pricefeed_id": None,
            },
            attention={},
            social_quality={},
            social_semantics={},
            market={
                "event_anchor": None,
                "decision_latest": None,
                "readiness": {
                    "anchor_status": "missing",
                    "latest_status": "missing",
                    "dex_floor_status": "missing_fields",
                    "missing_fields": [],
                    "stale_fields": [],
                },
            },
            timing={},
            source_event_ids=["event-1"],
            computed_at_ms=1_778_562_000_000,
        ),
    }


def _body(response: Any) -> dict[str, Any]:
    return json.loads(response.body.decode("utf-8"))
