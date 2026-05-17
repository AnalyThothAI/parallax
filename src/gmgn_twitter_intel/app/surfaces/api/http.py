from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter

from gmgn_twitter_intel.app.surfaces.api import (
    routes_events,
    routes_notifications,
    routes_pulse,
    routes_radar,
    routes_search,
    routes_social_enrichment,
    routes_status,
    routes_token_image,
    routes_watchlist,
)


def create_api_router(readiness_payload: Callable[[Any], tuple[dict[str, Any], int]]) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["api"])
    router.include_router(routes_status.create_router(readiness_payload))
    router.include_router(routes_token_image.router)
    router.include_router(routes_events.router)
    router.include_router(routes_watchlist.router)
    router.include_router(routes_search.router)
    router.include_router(routes_radar.router)
    router.include_router(routes_notifications.router)
    router.include_router(routes_social_enrichment.router)
    router.include_router(routes_pulse.router)
    return router
