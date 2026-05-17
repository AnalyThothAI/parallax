from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from gmgn_twitter_intel.app.surfaces.api import schemas as api_schemas
from gmgn_twitter_intel.app.surfaces.api.dependencies import _authenticated_runtime, _worker_running
from gmgn_twitter_intel.app.surfaces.api.responses import _json
from gmgn_twitter_intel.app.surfaces.api.validators import _csv_set, _handle_set, _horizon, _job_status, _limit, _window
from gmgn_twitter_intel.domains.account_quality.repositories.account_quality_repository import AccountQualityRepository
from gmgn_twitter_intel.domains.closed_loop_harness.interfaces import HarnessService

router = APIRouter()


@router.get("/social-events", response_model=api_schemas.ApiEnvelope[api_schemas.LooseData])
def social_events(
    request: Request,
    window: Annotated[str, Query()] = "1h",
    limit: Annotated[int, Query()] = 50,
    handles: Annotated[str, Query()] = "",
    event_types: Annotated[str, Query()] = "",
) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    with runtime.repositories() as repos:
        data = HarnessService(repos.harness).social_events(
            window=_window(window),
            limit=_limit(limit, maximum=500),
            handles=_handle_set(handles),
            event_types=_csv_set(event_types),
        )
    return _json({"ok": True, "data": data})


@router.get(
    "/social-events/by-ids",
    response_model=api_schemas.ApiEnvelope[api_schemas.SocialEventsByIdsData],
)
def social_events_by_ids(
    request: Request,
    ids: Annotated[str, Query()] = "",
) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    raw = [token.strip() for token in (ids or "").split(",") if token.strip()]
    if not raw:
        return JSONResponse(
            {"ok": False, "error": "ids_required", "field": "ids"},
            status_code=400,
        )
    if len(raw) > 200:
        return JSONResponse(
            {"ok": False, "error": "too_many_ids", "field": "ids", "limit": 200},
            status_code=400,
        )
    with runtime.repositories() as repos:
        records = repos.evidence.events_by_ids(raw)
        handles = sorted(
            {
                str(event.get("author_handle") or "").lstrip("@").lower()
                for event in records.values()
                if event.get("author_handle")
            }
        )
        watched = _watched_handle_set(repos, handles)
        events_payload = [_social_event_detail(records[event_id], watched) for event_id in raw if event_id in records]
        not_found = [event_id for event_id in raw if event_id not in records]
    return _json({"ok": True, "data": {"events": events_payload, "not_found": not_found}})


@router.get("/attention-seeds", response_model=api_schemas.ApiEnvelope[api_schemas.LooseData])
def attention_seeds(
    request: Request,
    window: Annotated[str, Query()] = "1h",
    limit: Annotated[int, Query()] = 50,
    handles: Annotated[str, Query()] = "",
) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    with runtime.repositories() as repos:
        data = HarnessService(repos.harness).attention_seeds(
            window=_window(window),
            limit=_limit(limit, maximum=500),
            handles=_handle_set(handles),
        )
    return _json({"ok": True, "data": data})


@router.get("/harness-snapshots", response_model=api_schemas.ApiEnvelope[api_schemas.LooseData])
def harness_snapshots(
    request: Request,
    window: Annotated[str, Query()] = "1h",
    horizon: Annotated[str, Query()] = "6h",
    limit: Annotated[int, Query()] = 50,
    asset: Annotated[str, Query()] = "",
) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    with runtime.repositories() as repos:
        data = HarnessService(repos.harness).snapshots(
            window=_window(window),
            horizon=_horizon(horizon),
            limit=_limit(limit, maximum=500),
            asset=asset or None,
        )
    return _json({"ok": True, "data": data})


@router.get("/harness-outcomes", response_model=api_schemas.ApiEnvelope[api_schemas.LooseData])
def harness_outcomes(
    request: Request,
    window: Annotated[str, Query()] = "1h",
    horizon: Annotated[str, Query()] = "6h",
    limit: Annotated[int, Query()] = 50,
    asset: Annotated[str, Query()] = "",
) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    with runtime.repositories() as repos:
        data = HarnessService(repos.harness).outcomes(
            window=_window(window),
            horizon=_horizon(horizon),
            limit=_limit(limit, maximum=500),
            asset=asset or None,
        )
    return _json({"ok": True, "data": data})


@router.get("/harness-credits", response_model=api_schemas.ApiEnvelope[api_schemas.LooseData])
def harness_credits(
    request: Request,
    window: Annotated[str, Query()] = "1h",
    horizon: Annotated[str, Query()] = "6h",
    limit: Annotated[int, Query()] = 80,
    asset: Annotated[str, Query()] = "",
) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    with runtime.repositories() as repos:
        data = HarnessService(repos.harness).credits(
            window=_window(window),
            horizon=_horizon(horizon),
            limit=_limit(limit, maximum=500),
            asset=asset or None,
        )
    return _json({"ok": True, "data": data})


@router.get("/harness-weights", response_model=api_schemas.ApiEnvelope[api_schemas.LooseData])
def harness_weights(
    request: Request,
    horizon: Annotated[str, Query()] = "",
    limit: Annotated[int, Query()] = 100,
) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    with runtime.repositories() as repos:
        data = HarnessService(repos.harness).weights(
            horizon=_horizon(horizon) if horizon else None,
            limit=_limit(limit, maximum=500),
        )
    return _json({"ok": True, "data": data})


@router.get("/harness-health", response_model=api_schemas.ApiEnvelope[api_schemas.LooseData])
def harness_health(request: Request) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    with runtime.repositories() as repos:
        job_counts = repos.enrichment.job_counts()
        data = HarnessService(repos.harness).health(
            llm_configured=bool(runtime.settings.llm_configured),
            extractor_running=_worker_running(runtime, "enrichment"),
            pending_jobs=int(job_counts.get("pending", 0)),
            schema_success_rate=repos.enrichment.job_success_rate(),
        )
        data["dead_jobs"] = int(job_counts.get("dead", 0))
        data["failed_jobs"] = int(job_counts.get("failed", 0))
        data["harness_ops_running"] = _worker_running(runtime, "harness_ops")
    return _json({"ok": True, "data": data})


@router.get(
    "/harness-score-buckets",
    response_model=api_schemas.ApiEnvelope[api_schemas.LooseData],
)
def harness_score_buckets(
    request: Request,
    horizon: Annotated[str, Query()] = "",
) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    with runtime.repositories() as repos:
        data = HarnessService(repos.harness).score_buckets(
            horizon=_horizon(horizon) if horizon else None,
        )
    return _json({"ok": True, "data": data})


@router.get(
    "/enrichment-jobs",
    response_model=api_schemas.ApiEnvelope[api_schemas.EnrichmentJobsData],
)
def enrichment_jobs(
    request: Request,
    limit: Annotated[int, Query()] = 50,
    status: Annotated[str | None, Query()] = None,
) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    parsed_status = _job_status(status)
    with runtime.repositories() as repos:
        items = repos.enrichment.list_jobs(limit=_limit(limit, maximum=500), status=parsed_status)
        counts = repos.enrichment.job_counts()
    return _json(
        {
            "ok": True,
            "data": {
                "items": items,
                "counts": counts,
            },
        }
    )


def _watched_handle_set(repos: Any, handles: list[str]) -> set[str]:
    if not handles:
        return set()
    try:
        profiles = AccountQualityRepository(repos.conn).profiles_by_handles(handles)
    except Exception:
        return set()
    return {
        handle for handle, profile in profiles.items() if (profile or {}).get("watched_status") in {"active", "watched"}
    }


def _social_event_detail(event: dict[str, Any], watched: set[str]) -> dict[str, Any]:
    author = _dict(event.get("author"))
    source = _dict(event.get("source"))
    handle = str(event.get("author_handle") or author.get("handle") or "").lstrip("@").lower() or None
    followers = event.get("author_followers", author.get("followers"))
    return {
        "event_id": str(event["event_id"]),
        "timestamp_ms": int(event.get("timestamp_ms") or event.get("received_at_ms") or 0),
        "source_provider": event.get("source_provider") or source.get("provider") or "",
        "channel": event.get("channel") or source.get("channel") or "",
        "action": event.get("action") or "",
        "author_handle": handle,
        "author_name": event.get("author_name") or author.get("name"),
        "author_followers": int(followers) if followers is not None else None,
        "author_watched": bool(handle and handle in watched),
        "text_clean": event.get("text_clean") or event.get("text") or _dict(event.get("content")).get("text"),
        "canonical_url": event.get("canonical_url"),
    }


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
