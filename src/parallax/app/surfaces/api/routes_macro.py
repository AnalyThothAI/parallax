from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from parallax.app.surfaces.api import schemas as api_schemas
from parallax.app.surfaces.api.dependencies import _authenticated_runtime, _now_ms
from parallax.app.surfaces.api.exceptions import ApiBadRequest
from parallax.app.surfaces.api.responses import _validated_json
from parallax.domains.macro_intel.services.completed_session_macro import (
    resolve_completed_session,
)
from parallax.domains.macro_intel.services.macro_live_catalog import (
    MACRO_LIVE_CATALOG,
    MACRO_LIVE_VIEW_IDS,
    query_concepts_for_live_view,
)
from parallax.domains.macro_intel.services.macro_live_evidence import (
    MACRO_LIVE_WINDOWS,
    MacroLiveWindow,
    build_macro_live_evidence,
)

router = APIRouter()

_GENERATING_RUN_STATES = frozenset({"pending", "running", "retryable"})
_LIVE_VIEW_IDS = frozenset(("dashboard", *MACRO_LIVE_VIEW_IDS))
_MAX_LIVE_ROWS_PER_SERIES = 2_000
_UNCLASSIFIED_LIMIT = 50


@router.get(
    "/macro/evidence/{view_id}",
    response_model=api_schemas.ApiEnvelope[api_schemas.MacroLiveEvidenceReadData],
)
def macro_live_evidence(
    request: Request,
    view_id: str,
    window: Annotated[str, Query()] = "90d",
) -> JSONResponse:
    runtime = _authenticated_macro_runtime(request)
    _validate_live_evidence_query(request, view_id=view_id, window=window)
    resolved_view = _live_view_id(view_id)
    resolved_window = _live_window(window)
    read_at_ms = _now_ms()
    start_date = datetime.fromtimestamp(read_at_ms / 1_000, tz=UTC).date() - timedelta(
        days=MACRO_LIVE_WINDOWS[resolved_window]
    )
    concept_keys = query_concepts_for_live_view(resolved_view)
    current_session = resolve_completed_session(
        now_ms=read_at_ms,
        settle_delay_seconds=0,
    )
    with runtime.repositories() as repos:
        observations = repos.macro_intel.live_observations(
            concept_keys=concept_keys,
            start_date=start_date,
            max_rows_per_series=_MAX_LIVE_ROWS_PER_SERIES,
        )
        if resolved_view == "dashboard":
            observations.extend(
                repos.macro_intel.latest_uncatalogued_observations(
                    catalog_concept_keys=tuple(MACRO_LIVE_CATALOG),
                    limit=_UNCLASSIFIED_LIMIT,
                )
            )
        research = _compact_research_payload(
            repos.macro_research.research_state(current_session),
            session_date=current_session,
        )
    payload = build_macro_live_evidence(
        view_id=resolved_view,
        window=resolved_window,
        read_at_ms=read_at_ms,
        observations=observations,
        research=research,
    )
    return _validated_json(
        api_schemas.ApiEnvelope[api_schemas.MacroLiveEvidenceReadData],
        {"ok": True, "data": payload},
    )


@router.get(
    "/macro/research",
    response_model=api_schemas.ApiEnvelope[api_schemas.MacroResearchReadData],
)
def macro_research(
    request: Request,
    session_date: Annotated[date | None, Query()] = None,
) -> JSONResponse:
    runtime = _authenticated_macro_runtime(request)
    _validate_research_query_params(request)
    current_session = resolve_completed_session(
        now_ms=_now_ms(),
        settle_delay_seconds=0,
    )
    target_session = session_date or current_session
    with runtime.repositories() as repos:
        payload = _research_payload(
            repos.macro_research.research_state(target_session),
            requested_session=target_session,
            current_session=current_session,
        )
    return _validated_json(
        api_schemas.ApiEnvelope[api_schemas.MacroResearchReadData],
        {"ok": True, "data": payload},
    )


def _authenticated_macro_runtime(request: Request) -> Any:
    runtime = _authenticated_runtime(request, allow_query_token=False)
    if "token" in request.query_params:
        raise ApiBadRequest("unsupported_query_param", field="token")
    return runtime


def _validate_research_query_params(request: Request) -> None:
    for name in request.query_params:
        if name != "session_date":
            raise ApiBadRequest("unsupported_query_param", field=name)


def _validate_live_evidence_query(
    request: Request,
    *,
    view_id: str,
    window: str,
) -> None:
    for name in request.query_params:
        if name != "window":
            raise ApiBadRequest("unsupported_query_param", field=name)
    if view_id not in _LIVE_VIEW_IDS:
        raise ApiBadRequest("unsupported_macro_view", field="view_id")
    if window not in MACRO_LIVE_WINDOWS:
        raise ApiBadRequest("unsupported_macro_window", field="window")


def _live_view_id(
    value: str,
) -> Literal[
    "dashboard",
    "overview",
    "rates-inflation",
    "growth-labor",
    "liquidity-funding",
    "credit",
    "cross-asset",
]:
    if value not in _LIVE_VIEW_IDS:
        raise ApiBadRequest("unsupported_macro_view", field="view_id")
    return cast(
        Literal[
            "dashboard",
            "overview",
            "rates-inflation",
            "growth-labor",
            "liquidity-funding",
            "credit",
            "cross-asset",
        ],
        value,
    )


def _live_window(value: str) -> MacroLiveWindow:
    if value not in MACRO_LIVE_WINDOWS:
        raise ApiBadRequest("unsupported_macro_window", field="window")
    return cast(MacroLiveWindow, value)


def _compact_research_payload(
    row: dict[str, Any] | None,
    *,
    session_date: date,
) -> dict[str, Any]:
    artifact = row.get("artifact_json") if row is not None else None
    if isinstance(artifact, dict):
        return {
            "state": "current",
            "session_date": session_date,
            "market_cutoff_ms": artifact.get("market_cutoff_ms"),
            "title": artifact.get("title"),
            "executive_summary": artifact.get("executive_summary"),
            "evidence_gap_summaries": [
                str(gap.get("summary"))
                for gap in artifact.get("gaps", ())
                if isinstance(gap, dict) and gap.get("summary")
            ],
            "href": "/macro/research",
        }
    run_status = str(row.get("run_status") or "") if row is not None else ""
    if run_status in _GENERATING_RUN_STATES:
        state = "generating"
    elif run_status == "failed":
        state = "failed"
    else:
        state = "missing"
    return {
        "state": state,
        "session_date": session_date,
        "market_cutoff_ms": row.get("market_cutoff_ms") if row is not None else None,
        "title": None,
        "executive_summary": None,
        "evidence_gap_summaries": [],
        "href": "/macro/research",
    }


def _research_payload(
    row: dict[str, Any] | None,
    *,
    requested_session: date,
    current_session: date,
) -> dict[str, Any]:
    if row is None:
        return {
            "state": "missing",
            "requested_session_date": requested_session,
            "current_session_date": current_session,
            "publication": None,
            "run": None,
        }
    publication = _publication_payload(row)
    if publication is not None:
        state = "current" if requested_session == current_session else "historical"
    elif str(row.get("run_status") or "") in _GENERATING_RUN_STATES:
        state = "generating"
    elif str(row.get("run_status") or "") == "failed":
        state = "failed"
    else:
        state = "missing"
    return {
        "state": state,
        "requested_session_date": requested_session,
        "current_session_date": current_session,
        "publication": publication,
        "run": _run_payload(row),
    }


def _publication_payload(row: dict[str, Any]) -> dict[str, Any] | None:
    artifact = row.get("artifact_json")
    if not isinstance(artifact, dict):
        return None
    return {
        "schema_version": artifact["schema_version"],
        "session_date": artifact["session_date"],
        "market_cutoff_ms": artifact["market_cutoff_ms"],
        "title": artifact["title"],
        "executive_summary": artifact["executive_summary"],
        "sections": artifact["sections"],
        "evidence_gaps": artifact["gaps"],
        "citations": [
            {
                "citation_id": citation["citation_id"],
                "source_type": citation["source_type"],
                "source_ref": citation["source_ref"],
                "source_label": citation["source_label"],
                "available_at_ms": citation["available_at_ms"],
                "observed_at": citation.get("observed_at"),
                "published_at_ms": citation.get("published_at_ms"),
                "source_url": citation.get("url"),
                "lineage": citation.get("lineage") or {},
            }
            for citation in artifact["citations"]
        ],
        "reviewer_notes": artifact["reviewer_notes"],
        "audit": row.get("audit_json") or {},
        "published_at_ms": row.get("published_at_ms"),
    }


def _run_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "session_date": row["session_date"],
        "status": row["run_status"],
        "attempt_count": row["attempt_count"],
        "max_attempts": row["max_attempts"],
        "last_error": row.get("last_error_message") or row.get("last_error_code"),
        "updated_at_ms": row["updated_at_ms"],
    }
