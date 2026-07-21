from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter

from parallax.app.surfaces.api import (
    routes_cex,
    routes_events,
    routes_macro,
    routes_news,
    routes_notifications,
    routes_ops,
    routes_radar,
    routes_search,
    routes_status,
    routes_token_images,
    routes_watchlist,
)


def create_api_router(readiness_payload: Callable[[Any], tuple[dict[str, Any], int]]) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["api"])
    router.include_router(routes_status.create_router(readiness_payload))
    router.include_router(routes_token_images.router)
    router.include_router(routes_events.router)
    router.include_router(routes_watchlist.router)
    router.include_router(routes_search.router)
    router.include_router(routes_radar.router)
    router.include_router(routes_cex.router)
    router.include_router(routes_macro.router)
    router.include_router(routes_news.router)
    router.include_router(routes_notifications.router)
    router.include_router(routes_ops.router)
    return router
