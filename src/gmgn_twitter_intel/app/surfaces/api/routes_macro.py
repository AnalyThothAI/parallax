from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from gmgn_twitter_intel.app.surfaces.api.dependencies import _authenticated_runtime
from gmgn_twitter_intel.app.surfaces.api.exceptions import ApiBadRequest
from gmgn_twitter_intel.app.surfaces.api.responses import _json
from gmgn_twitter_intel.domains.macro_intel._constants import (
    MACRO_CORE_CONCEPTS,
    MACRO_VIEW_PROJECTION_VERSION,
)
from gmgn_twitter_intel.domains.macro_intel.services.macro_asset_correlation import (
    ASSET_CORRELATION_WINDOWS,
    DEFAULT_ASSET_CORRELATION_CONCEPTS,
    OPTIONAL_ASSET_CORRELATION_CONCEPTS,
    SUPPORTED_ASSET_CORRELATION_CONCEPTS,
    build_macro_asset_correlation,
    correlation_query_bounds,
)
from gmgn_twitter_intel.domains.macro_intel.services.macro_module_catalog import (
    UnsupportedMacroModuleError,
    get_macro_module_config,
)
from gmgn_twitter_intel.domains.macro_intel.services.macro_module_views import build_macro_module_view
from gmgn_twitter_intel.domains.macro_intel.services.macro_series_view import (
    UnsupportedMacroConceptError,
    UnsupportedMacroSeriesWindowError,
    build_macro_series_view,
    macro_series_query_bounds,
    validate_macro_series_concepts,
    validate_macro_series_window,
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


@router.get("/macro/series")
def macro_series(
    request: Request,
    concept_keys: Annotated[str, Query()],
    window: Annotated[str, Query()] = "60d",
    _token: Annotated[str | None, Query(alias="token")] = None,
) -> JSONResponse:
    runtime = _authenticated_runtime(request)
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
    return _json(
        {
            "ok": True,
            "data": build_macro_series_view(
                concept_keys=resolved_concept_keys,
                observations=observations,
                window=resolved_window,
            ),
        }
    )


@router.get("/macro/modules/{module_id:path}")
def macro_module(request: Request, module_id: str) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    try:
        config = get_macro_module_config(module_id)
    except UnsupportedMacroModuleError as exc:
        raise ApiBadRequest(exc.code, field="module_id") from exc
    with runtime.repositories() as repos:
        snapshot = repos.macro_intel.latest_snapshot(projection_version=MACRO_VIEW_PROJECTION_VERSION)
        observations = repos.macro_intel.latest_observations(limit=250, concept_keys=_module_concepts(config))
        latest_import_run = repos.macro_intel.latest_import_run()
        cex_board = _cex_board(repos, module_id)
    return _json(
        {
            "ok": True,
            "data": build_macro_module_view(
                module_id,
                snapshot=snapshot,
                observations=observations,
                latest_import_run=latest_import_run,
                cex_board=cex_board,
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


def _validate_series_query_params(request: Request) -> None:
    supported = {"concept_keys", "token", "window"}
    for name in request.query_params:
        if name not in supported:
            raise ApiBadRequest("unsupported_query_param", field=name)


def _series_concept_keys(concept_keys: str) -> tuple[str, ...]:
    raw_concepts = str(concept_keys or "").strip()
    if not raw_concepts:
        raise ApiBadRequest("missing_concept_keys", field="concept_keys")
    concept_keys = tuple(dict.fromkeys(part.strip() for part in raw_concepts.split(",") if part.strip()))
    try:
        return validate_macro_series_concepts(concept_keys)
    except UnsupportedMacroConceptError as exc:
        raise ApiBadRequest(exc.code, field="concept_keys") from exc


def _series_window(window: str) -> str:
    window = str(window or "60d").strip()
    try:
        return validate_macro_series_window(window)
    except UnsupportedMacroSeriesWindowError as exc:
        raise ApiBadRequest(exc.code, field="window") from exc


def _module_concepts(config: Any) -> tuple[str, ...]:
    return tuple(dict.fromkeys((*config.required_concepts, *config.optional_concepts)))


def _cex_board(repos: Any, module_id: str) -> dict[str, Any] | None:
    if module_id != "assets/crypto-derivatives":
        return None
    board_repo = getattr(repos, "cex_oi_radar", None)
    if board_repo is None:
        return None
    board = board_repo.latest_board(limit=20)
    run = board.get("run") if isinstance(board, dict) else None
    rows = board.get("rows") if isinstance(board, dict) else []
    notes = (run or {}).get("notes_json") if isinstance(run, dict) else None
    return {
        "status": (run or {}).get("status") if isinstance(run, dict) else "missing",
        "degraded_reasons": notes.get("degraded_reasons", []) if isinstance(notes, dict) else [],
        "observed_at_ms": (run or {}).get("finished_at_ms") if isinstance(run, dict) else None,
        "rows": rows if isinstance(rows, list) else [],
    }


__all__ = ["router"]
