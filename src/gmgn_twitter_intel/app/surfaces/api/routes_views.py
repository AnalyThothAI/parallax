from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from gmgn_twitter_intel.app.surfaces.api.dependencies import _authenticated_runtime
from gmgn_twitter_intel.app.surfaces.api.responses import _json

router = APIRouter(prefix="/views")


@router.get("/macro")
def macro_views(request: Request) -> JSONResponse:
    runtime = _authenticated_runtime(request)
    with runtime.repositories() as repos:
        snapshot = repos.macro_intel.latest_snapshot()
    return _json({"ok": True, "data": _public_macro_view(snapshot)})


def _public_macro_view(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    if snapshot is None:
        return {
            "snapshot": None,
            "panels": {},
            "indicators": {},
            "triggers": [],
            "data_gaps": ["macro_view_snapshot_missing"],
            "source_coverage": {"observed_series_count": 0},
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
    }


__all__ = ["router"]
