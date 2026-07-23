from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from parallax.app.surfaces.api import schemas as api_schemas
from parallax.app.surfaces.api.dependencies import _authenticated_runtime
from parallax.app.surfaces.api.exceptions import ApiBadRequest
from parallax.app.surfaces.api.responses import _validated_json
from parallax.domains.macro_intel.services.macro_series_view import (
    UnsupportedMacroConceptError,
    UnsupportedMacroSeriesWindowError,
    build_macro_series_view,
    macro_series_query_bounds,
    validate_macro_series_concepts,
    validate_macro_series_window,
)

router = APIRouter()


@router.get(
    "/macro/overview",
    response_model=api_schemas.ApiEnvelope[api_schemas.MacroOverviewData],
)
def macro_overview(request: Request) -> JSONResponse:
    runtime = _authenticated_macro_runtime(request)
    with runtime.repositories() as repos:
        page = repos.macro_intel.snapshot_page("overview")
    return _macro_page_response(api_schemas.ApiEnvelope[api_schemas.MacroOverviewData], page)


@router.get(
    "/macro/cross-asset",
    response_model=api_schemas.ApiEnvelope[api_schemas.MacroCrossAssetData],
)
def macro_cross_asset(request: Request) -> JSONResponse:
    runtime = _authenticated_macro_runtime(request)
    with runtime.repositories() as repos:
        page = repos.macro_intel.snapshot_page("cross_asset")
    return _macro_page_response(api_schemas.ApiEnvelope[api_schemas.MacroCrossAssetData], page)


@router.get(
    "/macro/rates-inflation",
    response_model=api_schemas.ApiEnvelope[api_schemas.MacroRatesInflationData],
)
def macro_rates_inflation(request: Request) -> JSONResponse:
    runtime = _authenticated_macro_runtime(request)
    with runtime.repositories() as repos:
        page = repos.macro_intel.snapshot_page("rates_inflation")
    return _macro_page_response(api_schemas.ApiEnvelope[api_schemas.MacroRatesInflationData], page)


@router.get(
    "/macro/growth-labor",
    response_model=api_schemas.ApiEnvelope[api_schemas.MacroGrowthLaborData],
)
def macro_growth_labor(request: Request) -> JSONResponse:
    runtime = _authenticated_macro_runtime(request)
    with runtime.repositories() as repos:
        page = repos.macro_intel.snapshot_page("growth_labor")
    return _macro_page_response(api_schemas.ApiEnvelope[api_schemas.MacroGrowthLaborData], page)


@router.get(
    "/macro/liquidity-funding",
    response_model=api_schemas.ApiEnvelope[api_schemas.MacroLiquidityFundingData],
)
def macro_liquidity_funding(request: Request) -> JSONResponse:
    runtime = _authenticated_macro_runtime(request)
    with runtime.repositories() as repos:
        page = repos.macro_intel.snapshot_page("liquidity_funding")
    return _macro_page_response(api_schemas.ApiEnvelope[api_schemas.MacroLiquidityFundingData], page)


@router.get(
    "/macro/credit",
    response_model=api_schemas.ApiEnvelope[api_schemas.MacroCreditData],
)
def macro_credit(request: Request) -> JSONResponse:
    runtime = _authenticated_macro_runtime(request)
    with runtime.repositories() as repos:
        page = repos.macro_intel.snapshot_page("credit")
    return _macro_page_response(api_schemas.ApiEnvelope[api_schemas.MacroCreditData], page)


@router.get("/macro/series", response_model=api_schemas.ApiEnvelope[api_schemas.MacroSeriesData])
def macro_series(
    request: Request,
    concept_keys: Annotated[str, Query()],
    window: Annotated[str, Query()] = "60d",
) -> JSONResponse:
    runtime = _authenticated_macro_runtime(request)
    _validate_series_query_params(request)
    resolved_window = _series_window(window)
    resolved_concept_keys = _series_concept_keys(concept_keys)
    bounds = macro_series_query_bounds(resolved_window)
    with runtime.repositories() as repos:
        observations = repos.macro_intel.observations_for_concepts(
            concept_keys=resolved_concept_keys,
            lookback_days=bounds["lookback_days"],
            limit_per_series=bounds["limit_per_series"],
        )
    return _validated_json(
        api_schemas.ApiEnvelope[api_schemas.MacroSeriesData],
        {
            "ok": True,
            "data": build_macro_series_view(
                concept_keys=resolved_concept_keys,
                observations=observations,
                window=resolved_window,
            ),
        },
    )


def _macro_page_response[T: api_schemas.ApiSchema](
    envelope: type[api_schemas.ApiEnvelope[T]],
    page: dict[str, Any] | None,
) -> JSONResponse:
    if page is None:
        return _validated_json(
            envelope,
            {"ok": False, "error": "macro_projection_missing"},
            status_code=503,
        )
    return _validated_json(envelope, {"ok": True, "data": page})


def _authenticated_macro_runtime(request: Request) -> Any:
    runtime = _authenticated_runtime(request, allow_query_token=False)
    if "token" in request.query_params:
        raise ApiBadRequest("unsupported_query_param", field="token")
    return runtime


def _validate_series_query_params(request: Request) -> None:
    supported = {"concept_keys", "window"}
    for name in request.query_params:
        if name not in supported:
            raise ApiBadRequest("unsupported_query_param", field=name)


def _series_concept_keys(concept_keys: str) -> tuple[str, ...]:
    raw_concepts = str(concept_keys or "").strip()
    if not raw_concepts:
        raise ApiBadRequest("missing_concept_keys", field="concept_keys")
    normalized = tuple(dict.fromkeys(part.strip() for part in raw_concepts.split(",") if part.strip()))
    try:
        return validate_macro_series_concepts(normalized)
    except UnsupportedMacroConceptError as exc:
        raise ApiBadRequest(exc.code, field="concept_keys") from exc


def _series_window(window: str) -> str:
    normalized = str(window or "60d").strip()
    try:
        return validate_macro_series_window(normalized)
    except UnsupportedMacroSeriesWindowError as exc:
        raise ApiBadRequest(exc.code, field="window") from exc
