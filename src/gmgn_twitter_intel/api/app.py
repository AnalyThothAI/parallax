from __future__ import annotations

import asyncio
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from threading import RLock

from fastapi import FastAPI, WebSocket
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from ..collector.direct_ws import DirectGmgnWebSocketClient
from ..collector.service import CollectorService
from ..market.gmgn_openapi_client import GmgnOpenApiClient
from ..pipeline.enrichment_worker import EnrichmentWorker
from ..pipeline.ingest_service import IngestService
from ..pipeline.llm_client import OpenAIChatEnrichmentClient
from ..pipeline.token_market_enricher import TokenMarketEnricher
from ..settings import Settings, load_settings
from ..storage.enrichment_repository import EnrichmentRepository
from ..storage.entity_repository import EntityRepository
from ..storage.evidence_repository import EvidenceRepository
from ..storage.signal_repository import SignalRepository
from ..storage.sqlite_client import connect_sqlite
from ..storage.sqlite_schema import migrate
from ..storage.token_repository import TokenRepository
from .http import ApiUnauthorized, api_unauthorized_response, create_api_router
from .ws import PublicWebSocketHub


@dataclass(slots=True)
class CliRuntime:
    settings: Settings
    evidence: EvidenceRepository
    entities: EntityRepository
    signals: SignalRepository
    tokens: TokenRepository
    enrichment: EnrichmentRepository
    read_evidence: EvidenceRepository
    read_entities: EntityRepository
    read_signals: SignalRepository
    read_tokens: TokenRepository
    read_enrichment: EnrichmentRepository
    ingest: IngestService
    hub: PublicWebSocketHub
    collector: CollectorService
    start_collector: bool
    enrichment_worker: EnrichmentWorker | None = None
    gmgn_client: GmgnOpenApiClient | None = None
    collector_task: asyncio.Task | None = None
    supervisor_task: asyncio.Task | None = None
    enrichment_task: asyncio.Task | None = None


def create_app(
    settings: Settings | None = None,
    *,
    start_collector: bool = True,
    frontend_dist: str | Path | None = None,
) -> FastAPI:
    resolved_settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        runtime = _build_runtime(resolved_settings, start_collector=start_collector)
        app.state.service = runtime
        logger.info(
            "Starting GMGN Twitter Intel | "
            f"handles={','.join(resolved_settings.handles) or 'all'} "
            f"channels={','.join(resolved_settings.upstream_channels)} "
            f"sqlite={resolved_settings.sqlite_path}"
        )
        try:
            yield
        finally:
            await _stop_runtime(runtime)

    app = FastAPI(title="GMGN Twitter Intel", lifespan=lifespan)
    app.add_exception_handler(ApiUnauthorized, api_unauthorized_response)
    app.include_router(create_api_router(_readiness_payload))

    @app.get("/healthz", response_class=PlainTextResponse)
    async def healthz() -> str:
        return "ok\n"

    @app.get("/readyz")
    async def readyz() -> JSONResponse:
        runtime = app.state.service
        payload, status_code = _readiness_payload(runtime)
        return JSONResponse(payload, status_code=status_code)

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await app.state.service.hub.handle(websocket)

    _mount_frontend(app, frontend_dist=frontend_dist)

    return app


def _mount_frontend(app: FastAPI, *, frontend_dist: str | Path | None) -> None:
    dist = _frontend_dist_dir(frontend_dist)
    if dist is None:
        return

    assets = dist / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="frontend-assets")

    if (dist / "favicon.svg").exists():
        async def frontend_favicon() -> FileResponse:
            return FileResponse(dist / "favicon.svg")

        app.add_api_route("/favicon.svg", frontend_favicon, include_in_schema=False)

    async def frontend_index() -> FileResponse:
        return FileResponse(dist / "index.html")

    app.add_api_route("/", frontend_index, include_in_schema=False)
    app.add_api_route("/app", frontend_index, include_in_schema=False)
    app.add_api_route("/app/{path:path}", frontend_index, include_in_schema=False)


def _frontend_dist_dir(frontend_dist: str | Path | None = None) -> Path | None:
    candidates: list[Path] = []
    if frontend_dist is not None:
        candidates.append(Path(frontend_dist))
    module_path = Path(__file__).resolve()
    candidates.extend(
        [
            module_path.parents[1] / "web" / "dist",
            module_path.parents[3] / "web" / "dist",
        ]
    )
    for candidate in candidates:
        if (candidate / "index.html").exists():
            return candidate
    return None


def _build_runtime(settings: Settings, *, start_collector: bool) -> CliRuntime:
    if not settings.ws_token:
        raise ValueError("ws_token is required in config.yaml")
    conn = connect_sqlite(settings.sqlite_path, read_only=False)
    migrate(conn)
    read_conn = connect_sqlite(settings.sqlite_path, read_only=True)
    evidence = EvidenceRepository(conn)
    entities = EntityRepository(conn)
    signals = SignalRepository(conn)
    tokens = TokenRepository(conn)
    enrichment = EnrichmentRepository(conn)
    read_evidence = EvidenceRepository(read_conn)
    read_entities = EntityRepository(read_conn)
    read_signals = SignalRepository(read_conn)
    read_tokens = TokenRepository(read_conn)
    read_enrichment = EnrichmentRepository(read_conn)
    write_lock = RLock()
    gmgn_client = _gmgn_client(settings)
    token_market_enricher = (
        TokenMarketEnricher(
            tokens=tokens,
            client=gmgn_client,
            evm_candidate_chains=settings.gmgn_evm_candidate_chains,
        )
        if gmgn_client is not None
        else None
    )
    ingest = IngestService(
        evidence=evidence,
        entities=entities,
        signals=signals,
        enrichment=enrichment,
        tokens=tokens,
        token_market_enricher=token_market_enricher,
        write_lock=write_lock,
    )
    hub = PublicWebSocketHub(
        token=settings.ws_token,
        evidence=read_evidence,
        entities=read_entities,
        signals=read_signals,
        enrichment=read_enrichment,
        default_replay_limit=settings.replay_limit,
    )
    collector = CollectorService(
        handles=settings.handles,
        store=ingest,
        publisher=hub,
        upstream_client=None,
    )
    runtime = CliRuntime(
        settings=settings,
        evidence=evidence,
        entities=entities,
        signals=signals,
        tokens=tokens,
        enrichment=enrichment,
        read_evidence=read_evidence,
        read_entities=read_entities,
        read_signals=read_signals,
        read_tokens=read_tokens,
        read_enrichment=read_enrichment,
        ingest=ingest,
        hub=hub,
        collector=collector,
        start_collector=start_collector,
        gmgn_client=gmgn_client,
    )
    if settings.llm_configured:
        client = OpenAIChatEnrichmentClient(
            api_key=settings.llm_api_key or "",
            model=settings.llm_model or "",
            base_url=settings.llm_base_url,
            timeout_seconds=settings.llm_timeout_seconds,
        )
        runtime.enrichment_worker = EnrichmentWorker(
            evidence=evidence,
            entities=entities,
            enrichment=enrichment,
            client=client,
            publisher=hub,
            write_lock=write_lock,
            poll_interval=settings.enrichment_poll_interval,
        )
        runtime.enrichment_task = asyncio.create_task(runtime.enrichment_worker.run())
    if start_collector:
        upstream = DirectGmgnWebSocketClient(
            app_version=settings.upstream_app_version,
            channels=list(settings.upstream_channels),
            chains=list(settings.upstream_chains),
            proxy=settings.upstream_proxy,
            reconnect_delay=settings.upstream_reconnect_delay,
            heartbeat_interval=settings.upstream_heartbeat_interval,
            idle_timeout=settings.upstream_idle_timeout,
            on_frame=collector.handle_frame,
        )
        collector.upstream_client = upstream
        runtime.collector_task = asyncio.create_task(collector.run())
        runtime.supervisor_task = asyncio.create_task(_supervise_runtime(runtime))
    return runtime


async def _stop_runtime(runtime: CliRuntime) -> None:
    if runtime.enrichment_worker is not None:
        runtime.enrichment_worker.stop()
    tasks = [
        task
        for task in (runtime.supervisor_task, runtime.collector_task, runtime.enrichment_task)
        if task is not None
    ]
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    await runtime.collector.stop()
    if runtime.gmgn_client is not None:
        runtime.gmgn_client.close()
    runtime.evidence.close()
    runtime.read_evidence.close()


def _gmgn_client(settings: Settings) -> GmgnOpenApiClient | None:
    if not settings.gmgn_configured:
        return None
    return GmgnOpenApiClient(
        api_key=settings.gmgn_api_key or "",
        base_url=settings.gmgn_openapi_base_url,
        timeout_seconds=settings.gmgn_timeout_seconds,
        cache_ttl_seconds=settings.gmgn_token_info_cache_ttl_seconds,
    )


def _readiness_payload(runtime: CliRuntime, *, now_ms: int | None = None) -> tuple[dict, int]:
    now_ms = now_ms if now_ms is not None else _now_ms()
    collector_status = runtime.collector.status.to_dict()
    reasons = _unhealthy_reasons(runtime, now_ms=now_ms)
    payload = {
        "ok": not reasons,
        "reasons": reasons,
        "collector": collector_status,
        "handles": list(runtime.settings.handles),
        "store": str(runtime.settings.sqlite_path),
        "db": {"write_probe": _db_write_probe(runtime)},
        "enrichment": {
            "llm_configured": runtime.settings.llm_configured,
            "worker_running": _task_running(runtime.enrichment_task),
            "job_counts": _enrichment_job_counts(runtime),
        },
        "gmgn": {
            "openapi_configured": runtime.settings.gmgn_configured,
            "token_info_cache_ttl_seconds": runtime.settings.gmgn_token_info_cache_ttl_seconds,
        },
    }
    return payload, 503 if reasons else 200


def _unhealthy_reasons(runtime: CliRuntime, *, now_ms: int) -> list[str]:
    reasons = _collector_unhealthy_reasons(runtime, now_ms=now_ms)
    if runtime.settings.llm_configured and not _task_running(runtime.enrichment_task):
        reasons.append("enrichment_worker_stopped")
    return reasons


def _collector_unhealthy_reasons(runtime: CliRuntime, *, now_ms: int) -> list[str]:
    if not runtime.start_collector:
        return []

    task = runtime.collector_task
    if task is None:
        return ["collector_not_started"]
    if task.done():
        return ["collector_task_stopped"]

    status = runtime.collector.status
    stale_ms = int(runtime.settings.collector_stale_timeout * 1000)
    if status.last_frame_at_ms is None:
        age_ms = now_ms - int(status.started_at_ms)
        return ["no_upstream_frames"] if age_ms > stale_ms else []

    frame_age_ms = now_ms - int(status.last_frame_at_ms)
    return ["stale_upstream_frames"] if frame_age_ms > stale_ms else []


def _db_write_probe(runtime: CliRuntime) -> bool:
    try:
        return runtime.evidence.db_write_probe()
    except Exception:
        return False


def _enrichment_job_counts(runtime: CliRuntime) -> dict[str, int]:
    try:
        return runtime.read_enrichment.job_counts()
    except Exception:
        return {}


def _task_running(task: asyncio.Task | None) -> bool:
    return task is not None and not task.done()


async def _supervise_runtime(runtime: CliRuntime) -> None:
    interval = max(1.0, float(runtime.settings.collector_watchdog_interval))
    while True:
        await asyncio.sleep(interval)
        payload, status_code = _readiness_payload(runtime)
        if status_code < 500:
            continue
        logger.error(f"Collector watchdog exiting unhealthy process: reasons={payload['reasons']}")
        os._exit(1)


def _now_ms() -> int:
    return int(time.time() * 1000)
