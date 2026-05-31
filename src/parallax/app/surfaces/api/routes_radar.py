from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from parallax.app.surfaces.api import schemas as api_schemas
from parallax.app.surfaces.api.dependencies import _authenticated_runtime, _now_ms, _worker_object
from parallax.app.surfaces.api.exceptions import ApiBadRequest
from parallax.app.surfaces.api.responses import _json
from parallax.app.surfaces.api.validators import (
    _limit,
    _scope,
    _target_type,
    _token_radar_venue,
    _window,
)
from parallax.domains.asset_market.read_models.token_profile_read_model import TokenProfileReadModel
from parallax.domains.narrative_intel.read_models.narrative_read_model import NarrativeReadModel
from parallax.domains.token_intel.read_models.asset_flow_service import AssetFlowService
from parallax.domains.token_intel.read_models.stocks_radar_service import StocksRadarService

router = APIRouter()


@router.get("/token-radar", response_model=api_schemas.ApiEnvelope[api_schemas.TokenRadarData])
def token_radar(
    request: Request,
    window: Annotated[str, Query()] = "1h",
    limit: Annotated[int, Query()] = 20,
    scope: Annotated[str, Query()] = "all",
    venue: Annotated[str, Query()] = "all",
) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    parsed_window = _window(window)
    parsed_scope = _scope(scope)
    parsed_venue = _token_radar_venue(venue)
    data = _token_radar_data(
        runtime,
        window=parsed_window,
        limit=_limit(limit),
        scope=parsed_scope,
        venue=parsed_venue,
        now_ms=_now_ms(),
    )
    return _json(
        {"ok": True, "data": {"window": parsed_window, "scope": parsed_scope, "venue": parsed_venue, **data}}
    )


@router.get("/stocks-radar", response_model=api_schemas.ApiEnvelope[api_schemas.StocksRadarData])
def stocks_radar(
    request: Request,
    window: Annotated[str, Query()] = "1h",
    limit: Annotated[int, Query()] = 20,
    scope: Annotated[str, Query()] = "all",
) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    parsed_window = _window(window)
    parsed_scope = _scope(scope)
    with runtime.repositories() as repos:
        data = StocksRadarService(
            conn=repos.conn,
        ).stocks_radar(
            window=parsed_window,
            limit=_limit(limit),
            scope=parsed_scope,
            now_ms=_now_ms(),
        )
    return _json({"ok": True, "data": data})


@router.get("/live-market", response_model=api_schemas.ApiEnvelope[api_schemas.LiveMarketData])
def live_market(
    request: Request,
    target_type: Annotated[str, Query()] = "",
    target_id: Annotated[str, Query()] = "",
) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    parsed_target_type = _target_type(target_type)
    if not parsed_target_type or not target_id:
        raise ApiBadRequest("target_required", field="target_id")
    gateway = _worker_object(runtime, "live_price_gateway")
    if gateway is None:
        snapshot = {"target_type": parsed_target_type, "target_id": target_id, "status": "unsupported"}
    else:
        snapshot = gateway.snapshot(target_type=parsed_target_type, target_id=target_id, now_ms=_now_ms())
    return _json({"ok": True, "data": snapshot})


def _token_radar_data(
    runtime: Any,
    *,
    window: str,
    limit: int,
    scope: str,
    venue: str,
    now_ms: int,
) -> dict[str, Any]:
    with runtime.repositories() as repos:
        profiles = TokenProfileReadModel(token_profiles=repos.token_profiles)
        data = AssetFlowService(
            token_radar=repos.token_radar,
            profiles=profiles,
        ).asset_flow(
            window=window,
            limit=limit,
            scope=scope,
            venue=venue,
            now_ms=now_ms,
        )
        hydrated = _narrative_read_model(repos).hydrate_token_radar(
            _with_top_level_targets(data),
            window=window,
            scope=scope,
            now_ms=now_ms,
        )
        return _strip_synthetic_targets(hydrated)


def _narrative_read_model(repos: Any) -> Any:
    return NarrativeReadModel(repository=repos.narratives)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _with_top_level_targets(data: dict[str, Any]) -> dict[str, Any]:
    hydrated = dict(data)
    for key in ("targets", "attention"):
        hydrated[key] = [_row_with_top_level_target(item) for item in data.get(key, [])]
    return hydrated


def _row_with_top_level_target(item: Any) -> dict[str, Any]:
    row = dict(_dict(item))
    target = _dict(row.get("target"))
    if "target_type" not in row and target.get("target_type"):
        row["_synthetic_target_type"] = True
        row["target_type"] = target.get("target_type")
    if "target_id" not in row and target.get("target_id"):
        row["_synthetic_target_id"] = True
        row["target_id"] = target.get("target_id")
    return row


def _strip_synthetic_targets(data: dict[str, Any]) -> dict[str, Any]:
    stripped = dict(data)
    for key in ("targets", "attention"):
        stripped[key] = [_strip_synthetic_target(item) for item in data.get(key, [])]
    return stripped


def _strip_synthetic_target(item: Any) -> dict[str, Any]:
    row = dict(_dict(item))
    if row.pop("_synthetic_target_type", False):
        row.pop("target_type", None)
    if row.pop("_synthetic_target_id", False):
        row.pop("target_id", None)
    return row
