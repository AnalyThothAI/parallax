from __future__ import annotations

from datetime import date, datetime
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
from gmgn_twitter_intel.domains.macro_intel.services.macro_gap_payloads import build_macro_data_gaps
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
        publication_state = repos.macro_intel.macro_series_publication_state(MACRO_VIEW_PROJECTION_VERSION)
        currentness = _macro_currentness(snapshot=snapshot, publication_state=publication_state)
    return _json({"ok": True, "data": _public_macro(snapshot, currentness=currentness)})


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
        publication_state = repos.macro_intel.macro_series_publication_state(MACRO_VIEW_PROJECTION_VERSION)
        currentness = _macro_currentness(snapshot=snapshot, publication_state=publication_state)
        cex_board = _cex_board(repos, module_id)
    return _json(
        {
            "ok": True,
            "data": build_macro_module_view(
                module_id,
                snapshot=snapshot,
                observations=observations,
                facts_max_observed_at=currentness["facts_max_observed_at"],
                projection_lag_days=currentness["projection_lag_days"],
                projection_behind_facts=bool(currentness["projection_behind_facts"]),
                cex_board=cex_board,
            ),
        }
    )


def _public_macro(snapshot: dict[str, Any] | None, *, currentness: dict[str, Any]) -> dict[str, Any]:
    if snapshot is None:
        return {
            "snapshot": None,
            "currentness": currentness,
            "panels": {},
            "indicators": {},
            "triggers": [],
            "data_gaps": build_macro_data_gaps(["macro_view_snapshot_missing"]),
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
        "currentness": currentness,
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
    publication = board.get("publication") if isinstance(board, dict) else None
    state = board.get("state") if isinstance(board, dict) else None
    rows = board.get("rows") if isinstance(board, dict) else []
    return {
        "status": (publication or {}).get("status") if isinstance(publication, dict) else "missing",
        "degraded_reasons": [],
        "observed_at_ms": (publication or {}).get("published_at_ms")
        if isinstance(publication, dict)
        else (state or {}).get("current_published_at_ms")
        if isinstance(state, dict)
        else None,
        "rows": rows if isinstance(rows, list) else [],
    }


def _macro_currentness(
    *,
    snapshot: dict[str, Any] | None,
    publication_state: dict[str, Any] | None,
) -> dict[str, Any]:
    facts_max_observed_at = _to_date(_snapshot_latest_observed_at(snapshot))
    snapshot_asof = _to_date(snapshot.get("asof_date") if snapshot else None)
    return {
        "publication_status": (publication_state or {}).get("latest_attempt_status"),
        "publication_row_count": (publication_state or {}).get("row_count"),
        "publication_finished_at_ms": (publication_state or {}).get("latest_attempt_finished_at_ms"),
        "facts_max_observed_at": _date_string(facts_max_observed_at),
        "projection_lag_days": _projection_lag_days(facts_max_observed_at, snapshot_asof),
        "projection_behind_facts": (
            facts_max_observed_at is not None and (snapshot_asof is None or snapshot_asof < facts_max_observed_at)
        ),
    }


def _snapshot_latest_observed_at(snapshot: dict[str, Any] | None) -> object:
    coverage = snapshot.get("source_coverage_json") if snapshot else None
    if isinstance(coverage, dict) and coverage.get("latest_observed_at") is not None:
        return coverage.get("latest_observed_at")
    return snapshot.get("asof_date") if snapshot else None


def _projection_lag_days(facts_max_observed_at: date | None, snapshot_asof: date | None) -> int | None:
    if facts_max_observed_at is None or snapshot_asof is None:
        return None
    return max(0, (facts_max_observed_at - snapshot_asof).days)


def _date_string(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _to_date(value: object) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        return date.fromisoformat(value)
    return None


__all__ = ["router"]
