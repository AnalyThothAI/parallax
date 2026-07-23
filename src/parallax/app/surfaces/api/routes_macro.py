from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from parallax.app.surfaces.api import schemas as api_schemas
from parallax.app.surfaces.api.dependencies import _authenticated_runtime, _now_ms
from parallax.app.surfaces.api.exceptions import ApiBadRequest
from parallax.app.surfaces.api.responses import _validated_json
from parallax.domains.macro_intel.services.macro_cross_asset_rules import resolve_market_cutoff
from parallax.domains.macro_intel.services.macro_series_view import (
    UnsupportedMacroConceptError,
    UnsupportedMacroSeriesWindowError,
    build_macro_series_view,
    macro_series_query_bounds,
    validate_macro_series_concepts,
    validate_macro_series_window,
)

router = APIRouter()

_JOB_READ_STATES = frozenset({"pending", "running", "retryable", "blocked", "failed"})


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


@router.get(
    "/macro/daily-judgment",
    response_model=api_schemas.ApiEnvelope[api_schemas.DailyMacroJudgmentReadData],
)
def daily_macro_judgment(
    request: Request,
    session_date: Annotated[date | None, Query()] = None,
) -> JSONResponse:
    runtime = _authenticated_macro_runtime(request)
    _validate_daily_judgment_query_params(request)
    with runtime.repositories() as repos:
        payload = _daily_judgment_payload(
            repos.daily_macro_judgments,
            requested_session=session_date,
            now_ms=_now_ms(),
        )
    status_code = 503 if payload["state"] == "missing" else 200
    envelope_payload: dict[str, Any] = {
        "ok": payload["state"] != "missing",
        "data": payload,
    }
    if payload["state"] == "missing":
        envelope_payload["error"] = "daily_macro_judgment_missing"
    return _validated_json(
        api_schemas.ApiEnvelope[api_schemas.DailyMacroJudgmentReadData],
        envelope_payload,
        status_code=status_code,
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


def _validate_daily_judgment_query_params(request: Request) -> None:
    for name in request.query_params:
        if name != "session_date":
            raise ApiBadRequest("unsupported_query_param", field=name)


def _daily_judgment_payload(
    repository: Any,
    *,
    requested_session: date | None,
    now_ms: int,
) -> dict[str, Any]:
    current_session = resolve_market_cutoff(computed_at_ms=now_ms)
    target_session = requested_session or current_session
    publication = repository.publication_record(target_session)
    target_job = repository.job_record(target_session)
    if publication is not None:
        state = "current" if target_session == current_session else "historical"
        return {
            "target_session_date": target_session,
            "state": state,
            "is_current": state == "current",
            "publication": _publication_payload(repository, publication),
            "target_job": _job_payload(target_job),
        }
    if requested_session is None:
        latest = repository.latest_publication_record()
        if latest is not None:
            return {
                "target_session_date": target_session,
                "state": "stale",
                "is_current": False,
                "publication": _publication_payload(repository, latest),
                "target_job": _job_payload(target_job),
            }
    job_status = str(target_job["status"]) if target_job is not None else "missing"
    state = job_status if job_status in _JOB_READ_STATES else "missing"
    return {
        "target_session_date": target_session,
        "state": cast(
            Literal["pending", "running", "retryable", "blocked", "failed", "missing"],
            state,
        ),
        "is_current": False,
        "publication": None,
        "target_job": _job_payload(target_job),
    }


def _publication_payload(repository: Any, row: dict[str, Any]) -> dict[str, Any]:
    session_date = row["session_date"]
    return {
        "session_date": session_date,
        "market_cutoff_ms": row["market_cutoff_ms"],
        "evidence_pack_hash": row["evidence_pack_hash"],
        "judgment": row["judgment_json"],
        "memo_text": row["memo_text"],
        "review": row["review_json"],
        "agent_audit": row["agent_audit_json"],
        "model_name": row["model_name"],
        "prompt_version": row["prompt_version"],
        "schema_version": row["schema_version"],
        "workflow_version": row["workflow_version"],
        "renderer_version": row["renderer_version"],
        "published_at_ms": row["published_at_ms"],
        "evidence_pack": row["evidence_pack_json"],
        "compiler_version": row["compiler_version"],
        "selection_policy_version": row["selection_policy_version"],
        "sealed_at_ms": row["sealed_at_ms"],
        "outcomes": repository.outcomes_for_session(session_date),
    }


def _job_payload(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "session_date": row["session_date"],
        "market_cutoff_ms": row["market_cutoff_ms"],
        "status": row["status"],
        "attempt_count": row["attempt_count"],
        "max_attempts": row["max_attempts"],
        "due_at_ms": row["due_at_ms"],
        "reviewer_disposition": row["reviewer_disposition"],
        "last_error": row["last_error"],
        "updated_at_ms": row["updated_at_ms"],
    }


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
