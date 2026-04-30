from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI, WebSocket
from fastapi.responses import PlainTextResponse
from loguru import logger

from ..collector.direct_ws import DirectGmgnWebSocketClient
from ..collector.service import CollectorService
from ..settings import Settings, load_settings
from ..storage.lancedb_client import build_lancedb_client
from ..storage.runtime_bootstrap import bootstrap_lancedb
from ..storage.tweet_repository import TweetRepository
from .ws import PublicWebSocketHub


@dataclass(slots=True)
class CliRuntime:
    settings: Settings
    store: TweetRepository
    hub: PublicWebSocketHub
    collector: CollectorService
    collector_task: asyncio.Task | None = None


def create_app(settings: Settings | None = None, *, start_collector: bool = True) -> FastAPI:
    resolved_settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        runtime = _build_runtime(resolved_settings, start_collector=start_collector)
        app.state.service = runtime
        logger.info(
            "Starting GMGN Twitter CLI | "
            f"handles={','.join(resolved_settings.handles) or 'all'} "
            f"channels={','.join(resolved_settings.upstream_channels)} "
            f"lancedb={resolved_settings.lancedb_path}"
        )
        try:
            yield
        finally:
            await _stop_runtime(runtime)

    app = FastAPI(title="GMGN Twitter CLI", lifespan=lifespan)

    @app.get("/healthz", response_class=PlainTextResponse)
    async def healthz() -> str:
        return "ok\n"

    @app.get("/readyz")
    async def readyz() -> dict:
        runtime = app.state.service
        health_counts = runtime.store.health_counts()
        return {
            "collector": runtime.collector.status.to_dict(),
            "handles": list(runtime.settings.handles),
            "store": str(runtime.settings.lancedb_path),
            "store_counts": runtime.store.event_counts(),
            "entity_backlog": {
                "unresolved_entities": health_counts["unresolved_entities"],
            },
            "embedding_backlog": {
                "pending": health_counts["pending_embeddings"],
            },
            "provider_status": {
                "embedding": "hash",
                "sentiment": runtime.settings.sentiment_backend,
            },
        }

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await app.state.service.hub.handle(websocket)

    return app


def _build_runtime(settings: Settings, *, start_collector: bool) -> CliRuntime:
    client = build_lancedb_client(settings.lancedb_path, embedding_dim=settings.embedding_dim)
    bootstrap_lancedb(client)
    store = TweetRepository(client)
    hub = PublicWebSocketHub(token=settings.ws_token, store=store, default_replay_limit=settings.replay_limit)
    collector = CollectorService(
        handles=settings.handles,
        store=store,
        publisher=hub,
        upstream_client=None,
    )
    runtime = CliRuntime(settings=settings, store=store, hub=hub, collector=collector)
    if start_collector:
        upstream = DirectGmgnWebSocketClient(
            app_version=settings.upstream_app_version,
            channels=list(settings.upstream_channels),
            chains=list(settings.upstream_chains),
            proxy=settings.upstream_proxy,
            reconnect_delay=settings.upstream_reconnect_delay,
            heartbeat_interval=settings.upstream_heartbeat_interval,
            on_frame=collector.handle_frame,
        )
        collector.upstream_client = upstream
        runtime.collector_task = asyncio.create_task(collector.run())
    return runtime


async def _stop_runtime(runtime: CliRuntime) -> None:
    tasks = [task for task in (runtime.collector_task,) if task is not None]
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    await runtime.collector.stop()
    runtime.store.close()
