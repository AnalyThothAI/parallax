from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from gmgn_twitter_intel.app.surfaces.api import schemas as api_schemas
from gmgn_twitter_intel.app.surfaces.api.dependencies import _authenticated_runtime, _now_ms, _worker_object
from gmgn_twitter_intel.app.surfaces.api.exceptions import ApiBadRequest
from gmgn_twitter_intel.app.surfaces.api.responses import _json
from gmgn_twitter_intel.app.surfaces.api.validators import _limit, _scope, _target_type, _window
from gmgn_twitter_intel.domains.asset_market.read_models.token_profile_read_model import TokenProfileReadModel
from gmgn_twitter_intel.domains.token_intel.read_models.asset_flow_service import AssetFlowService
from gmgn_twitter_intel.domains.token_intel.read_models.stocks_radar_service import StocksRadarService

router = APIRouter()


@router.get("/token-radar", response_model=api_schemas.ApiEnvelope[api_schemas.TokenRadarData])
def token_radar(
    request: Request,
    window: Annotated[str, Query()] = "1h",
    limit: Annotated[int, Query()] = 20,
    scope: Annotated[str, Query()] = "all",
) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    parsed_window = _window(window)
    parsed_scope = _scope(scope)
    data = _token_radar_data(
        runtime,
        window=parsed_window,
        limit=_limit(limit),
        scope=parsed_scope,
        now_ms=_now_ms(),
    )
    return _json({"ok": True, "data": {"window": parsed_window, "scope": parsed_scope, **data}})


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
            quote_provider=getattr(runtime, "stock_quote_provider", None),
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
    now_ms: int,
) -> dict[str, Any]:
    with runtime.repositories() as repos:
        profiles = TokenProfileReadModel(token_profiles=repos.token_profiles)
        return AssetFlowService(
            token_radar=repos.token_radar,
            profiles=profiles,
        ).asset_flow(
            window=window,
            limit=limit,
            scope=scope,
            now_ms=now_ms,
        )
