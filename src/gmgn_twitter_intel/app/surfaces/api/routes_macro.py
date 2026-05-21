from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from gmgn_twitter_intel.app.surfaces.api.dependencies import _authenticated_runtime
from gmgn_twitter_intel.app.surfaces.api.exceptions import ApiBadRequest
from gmgn_twitter_intel.app.surfaces.api.responses import _json
from gmgn_twitter_intel.domains.macro_intel._constants import MACRO_CORE_CONCEPTS, MACRO_VIEW_PROJECTION_VERSION
from gmgn_twitter_intel.domains.macro_intel.services.macro_asset_correlation import (
    ASSET_CORRELATION_WINDOWS,
    DEFAULT_ASSET_CORRELATION_CONCEPTS,
    OPTIONAL_ASSET_CORRELATION_CONCEPTS,
    SUPPORTED_ASSET_CORRELATION_CONCEPTS,
    build_macro_asset_correlation,
    correlation_query_bounds,
)

router = APIRouter()


@router.get("/macro")
def macro(request: Request) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    with runtime.repositories() as repos:
        snapshot = repos.macro_intel.latest_snapshot(projection_version=MACRO_VIEW_PROJECTION_VERSION)
    return _json({"ok": True, "data": _public_macro(snapshot)})


@router.get("/macro/assets/correlation")
def macro_asset_correlation(request: Request) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    _validate_correlation_query_params(request)
    window = _correlation_window(request)
    assets, optional_assets = _correlation_assets(request)
    bounds = correlation_query_bounds(window)
    with runtime.repositories() as repos:
        observations = repos.macro_intel.observations_for_concepts(
            concept_keys=assets,
            lookback_days=bounds["lookback_days"],
            limit_per_series=bounds["limit_per_series"],
        )
    return _json(
        {
            "ok": True,
            "data": build_macro_asset_correlation(
                observations,
                assets=assets,
                optional_assets=optional_assets,
                window=window,
            ),
        }
    )


def _public_macro(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    if snapshot is None:
        return {
            "snapshot": None,
            "panels": {},
            "indicators": {},
            "triggers": [],
            "data_gaps": ["macro_view_snapshot_missing"],
            "source_coverage": {
                "observed_concept_count": 0,
                "required_concept_count": len(MACRO_CORE_CONCEPTS),
                "coverage_ratio": 0.0,
            },
            "features": {},
            "chain": {},
            "scenario": {},
            "scorecard": {},
        }
    return {
        "snapshot": {
            "snapshot_id": snapshot["snapshot_id"],
            "projection_version": snapshot["projection_version"],
            "asof_date": snapshot["asof_date"],
            "status": snapshot["status"],
            "regime": snapshot["regime"],
            "overall_score": snapshot.get("overall_score"),
            "computed_at_ms": snapshot["computed_at_ms"],
        },
        "panels": snapshot.get("panels_json") or {},
        "indicators": snapshot.get("indicators_json") or {},
        "triggers": snapshot.get("triggers_json") or [],
        "data_gaps": snapshot.get("data_gaps_json") or [],
        "source_coverage": snapshot.get("source_coverage_json") or {},
        "features": snapshot.get("features_json") or {},
        "chain": snapshot.get("chain_json") or {},
        "scenario": snapshot.get("scenario_json") or {},
        "scorecard": snapshot.get("scorecard_json") or {},
    }


def _validate_correlation_query_params(request: Request) -> None:
    supported = {"assets", "token", "window"}
    for name in request.query_params:
        if name not in supported:
            raise ApiBadRequest("unsupported_query_param", field=name)


def _correlation_window(request: Request) -> str:
    window = str(request.query_params.get("window") or "60d").strip()
    if window not in ASSET_CORRELATION_WINDOWS:
        raise ApiBadRequest("invalid_window", field="window")
    return window


def _correlation_assets(request: Request) -> tuple[tuple[str, ...], tuple[str, ...]]:
    raw_assets = request.query_params.get("assets")
    if raw_assets is None or not raw_assets.strip():
        return (
            (*DEFAULT_ASSET_CORRELATION_CONCEPTS, *OPTIONAL_ASSET_CORRELATION_CONCEPTS),
            OPTIONAL_ASSET_CORRELATION_CONCEPTS,
        )
    assets = tuple(dict.fromkeys(part.strip() for part in raw_assets.split(",") if part.strip()))
    if not assets:
        raise ApiBadRequest("invalid_assets", field="assets")
    supported = set(SUPPORTED_ASSET_CORRELATION_CONCEPTS)
    if any(asset not in supported for asset in assets):
        raise ApiBadRequest("unsupported_asset", field="assets")
    return assets, ()


__all__ = ["router"]
