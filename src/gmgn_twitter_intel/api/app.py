from __future__ import annotations

import asyncio
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from ..collector.direct_ws import DirectGmgnWebSocketClient
from ..collector.service import CollectorService
from ..market.okx_cex_client import OkxCexClient
from ..market.okx_dex_client import OkxDexClient
from ..pipeline.asset_market_sync_worker import AssetMarketSyncWorker
from ..pipeline.asset_resolution_worker import AssetResolutionWorker
from ..pipeline.enrichment_worker import EnrichmentWorker
from ..pipeline.harness_ops_worker import HarnessOpsWorker
from ..pipeline.ingest_service import IngestService
from ..pipeline.llm_client import OpenAIChatEnrichmentClient
from ..pipeline.notification_delivery import NotificationDeliveryWorker
from ..pipeline.notification_rules import NotificationRuleEngine
from ..pipeline.notification_worker import NotificationWorker
from ..retrieval.account_alert_service import AccountAlertService
from ..retrieval.asset_flow_service import AssetFlowService
from ..retrieval.harness_service import HarnessService
from ..settings import Settings, load_settings
from ..storage.enrichment_repository import EnrichmentRepository
from ..storage.entity_repository import EntityRepository
from ..storage.evidence_repository import EvidenceRepository
from ..storage.harness_repository import HarnessRepository
from ..storage.market_observation_repository import MarketObservationRepository
from ..storage.notification_repository import NotificationRepository
from ..storage.postgres_client import create_pool, postgres_health_check, with_password_from_file
from ..storage.repository_session import PooledRepository, repository_session
from ..storage.signal_repository import SignalRepository
from ..storage.token_repository import TokenRepository
from ..storage.token_signal_repository import TokenSignalRepository
from .http import ApiBadRequest, ApiUnauthorized, api_bad_request_response, api_unauthorized_response, create_api_router
from .ws import PublicWebSocketHub


@dataclass(slots=True)
class CliRuntime:
    settings: Settings
    db_pool: object
    evidence: object
    entities: object
    signals: object
    tokens: object
    market_observations: object
    enrichment: object
    harness: object
    notifications: object
    token_signals: object
    read_evidence: object
    read_entities: object
    read_signals: object
    read_tokens: object
    read_enrichment: object
    read_harness: object
    read_notifications: object
    read_token_signals: object
    ingest: IngestService
    hub: PublicWebSocketHub
    collector: CollectorService
    start_collector: bool
    enrichment_worker: EnrichmentWorker | None = None
    harness_ops_worker: HarnessOpsWorker | None = None
    notification_worker: NotificationWorker | None = None
    notification_delivery_worker: NotificationDeliveryWorker | None = None
    asset_market_sync_worker: AssetMarketSyncWorker | None = None
    asset_resolution_worker: AssetResolutionWorker | None = None
    collector_task: asyncio.Task | None = None
    supervisor_task: asyncio.Task | None = None
    enrichment_task: asyncio.Task | None = None
    harness_ops_task: asyncio.Task | None = None
    notification_task: asyncio.Task | None = None
    notification_delivery_task: asyncio.Task | None = None
    asset_market_sync_task: asyncio.Task | None = None
    asset_resolution_task: asyncio.Task | None = None

    def repositories(self):
        return repository_session(self.db_pool)


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
        _start_runtime_tasks(runtime)
        app.state.service = runtime
        logger.info(
            "Starting GMGN Twitter Intel | "
            f"handles={','.join(resolved_settings.handles) or 'all'} "
            f"channels={','.join(resolved_settings.upstream_channels)} "
            "storage=postgresql"
        )
        try:
            yield
        finally:
            await _stop_runtime(runtime)

    app = FastAPI(title="GMGN Twitter Intel", lifespan=lifespan)
    app.add_exception_handler(ApiUnauthorized, api_unauthorized_response)
    app.add_exception_handler(ApiBadRequest, api_bad_request_response)
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


class _PooledIngestStore:
    def __init__(self, db_pool: object):
        self.db_pool = db_pool

    def insert_raw_frame(self, **kwargs) -> bool:
        with repository_session(self.db_pool) as repos:
            return repos.evidence.insert_raw_frame(**kwargs)

    def ingest_event(self, event, *, is_watched: bool):
        with repository_session(self.db_pool) as repos:
            ingest = IngestService(
                evidence=repos.evidence,
                entities=repos.entities,
                signals=repos.signals,
                enrichment=repos.enrichment,
                assets=repos.assets,
            )
            return ingest.ingest_event(event, is_watched=is_watched)


def _build_runtime(settings: Settings, *, start_collector: bool) -> CliRuntime:
    if not settings.ws_token:
        raise ValueError("ws_token is required in config.yaml")
    dsn = with_password_from_file(settings.postgres_dsn, settings.postgres_password_file)
    db_pool = create_pool(
        dsn,
        min_size=settings.postgres_pool_min_size,
        max_size=settings.postgres_pool_max_size,
        connect_timeout_seconds=settings.postgres_connect_timeout_seconds,
    )
    with db_pool.connection() as conn:
        startup_db = postgres_health_check(conn)
    if not startup_db.get("ok"):
        db_pool.close()
        raise RuntimeError(f"postgres health check failed: {startup_db}")
    evidence = PooledRepository(db_pool, EvidenceRepository)
    entities = PooledRepository(db_pool, EntityRepository)
    signals = PooledRepository(db_pool, SignalRepository)
    tokens = PooledRepository(db_pool, TokenRepository)
    market_observations = PooledRepository(db_pool, MarketObservationRepository)
    enrichment = PooledRepository(db_pool, EnrichmentRepository)
    harness = PooledRepository(db_pool, HarnessRepository)
    notifications = PooledRepository(db_pool, NotificationRepository)
    token_signals = PooledRepository(db_pool, TokenSignalRepository)
    read_evidence = evidence
    read_entities = entities
    read_signals = signals
    read_tokens = tokens
    read_enrichment = enrichment
    read_harness = harness
    read_notifications = notifications
    read_token_signals = token_signals
    ingest = _PooledIngestStore(db_pool)
    hub = PublicWebSocketHub(
        token=settings.ws_token,
        repository_session=lambda: repository_session(db_pool),
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
        db_pool=db_pool,
        evidence=evidence,
        entities=entities,
        signals=signals,
        tokens=tokens,
        market_observations=market_observations,
        enrichment=enrichment,
        harness=harness,
        notifications=notifications,
        token_signals=token_signals,
        read_evidence=read_evidence,
        read_entities=read_entities,
        read_signals=read_signals,
        read_tokens=read_tokens,
        read_enrichment=read_enrichment,
        read_harness=read_harness,
        read_notifications=read_notifications,
        read_token_signals=read_token_signals,
        ingest=ingest,
        hub=hub,
        collector=collector,
        start_collector=start_collector,
    )
    runtime.harness_ops_worker = HarnessOpsWorker(
        repository_session=lambda: repository_session(db_pool),
    )
    if settings.notifications.enabled:
        runtime.notification_worker = NotificationWorker(
            repository_session=lambda: repository_session(db_pool),
            rule_engine_factory=lambda repos: _notification_rule_engine(settings, repos),
            publisher=hub,
            delivery_channels=settings.notifications.channels,
            poll_interval=settings.notifications.poll_interval_seconds,
        )
        if any(
            channel.enabled and (channel.provider == "log" or channel.url)
            for channel in settings.notifications.channels.values()
        ):
            runtime.notification_delivery_worker = NotificationDeliveryWorker(
                channels=settings.notifications.channels,
                repository_session=lambda: repository_session(db_pool),
                poll_interval=settings.notifications.poll_interval_seconds,
            )
    if start_collector and (settings.okx_cex_sync_enabled or settings.okx_dex_configured):
        okx_cex_client = (
            OkxCexClient(
                base_url=settings.okx_cex_base_url,
                timeout_seconds=settings.okx_timeout_seconds,
            )
            if settings.okx_cex_sync_enabled
            else None
        )
        okx_dex_price_client = (
            OkxDexClient(
                base_url=settings.okx_dex_base_url,
                api_key=settings.okx_dex_api_key,
                secret_key=settings.okx_dex_secret_key,
                passphrase=settings.okx_dex_passphrase,
                timeout_seconds=settings.okx_timeout_seconds,
            )
            if settings.okx_dex_configured
            else None
        )
        runtime.asset_market_sync_worker = AssetMarketSyncWorker(
            client=okx_cex_client,
            dex_client=okx_dex_price_client,
            repository_session=lambda: repository_session(db_pool),
            inst_types=settings.okx_cex_inst_types,
            interval_seconds=settings.okx_cex_sync_interval_seconds,
        )
    if settings.okx_dex_configured:
        okx_dex_client = OkxDexClient(
            base_url=settings.okx_dex_base_url,
            api_key=settings.okx_dex_api_key,
            secret_key=settings.okx_dex_secret_key,
            passphrase=settings.okx_dex_passphrase,
            timeout_seconds=settings.okx_timeout_seconds,
        )
        runtime.asset_resolution_worker = AssetResolutionWorker(
            client=okx_dex_client,
            repository_session=lambda: repository_session(db_pool),
            chain_indexes=settings.okx_dex_chain_indexes,
            poll_interval=5.0,
        )
    if settings.llm_configured:
        client = OpenAIChatEnrichmentClient(
            api_key=settings.llm_api_key or "",
            model=settings.llm_model or "",
            base_url=settings.llm_base_url,
            timeout_seconds=settings.llm_timeout_seconds,
        )
        runtime.enrichment_worker = EnrichmentWorker(
            client=client,
            publisher=hub,
            repository_session=lambda: repository_session(db_pool),
            poll_interval=settings.enrichment_poll_interval,
        )
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
    return runtime


def _notification_rule_engine(settings: Settings, repos) -> NotificationRuleEngine:
    return NotificationRuleEngine(
        settings=settings,
        evidence=repos.evidence,
        account_alerts=AccountAlertService(repos.signals),
        asset_flow=AssetFlowService(assets=repos.assets),
        harness=HarnessService(repos.harness),
    )


def _start_runtime_tasks(runtime: CliRuntime) -> None:
    if runtime.enrichment_worker is not None and runtime.enrichment_task is None:
        runtime.enrichment_task = asyncio.create_task(runtime.enrichment_worker.run())
    if runtime.harness_ops_worker is not None and runtime.harness_ops_task is None:
        runtime.harness_ops_task = asyncio.create_task(runtime.harness_ops_worker.run())
    if runtime.notification_worker is not None and runtime.notification_task is None:
        runtime.notification_task = asyncio.create_task(runtime.notification_worker.run())
    if runtime.notification_delivery_worker is not None and runtime.notification_delivery_task is None:
        runtime.notification_delivery_task = asyncio.create_task(runtime.notification_delivery_worker.run())
    if runtime.asset_market_sync_worker is not None and runtime.asset_market_sync_task is None:
        runtime.asset_market_sync_task = asyncio.create_task(runtime.asset_market_sync_worker.run())
    if runtime.asset_resolution_worker is not None and runtime.asset_resolution_task is None:
        runtime.asset_resolution_task = asyncio.create_task(runtime.asset_resolution_worker.run())
    if runtime.start_collector:
        if runtime.collector_task is None:
            runtime.collector_task = asyncio.create_task(runtime.collector.run())
        if runtime.supervisor_task is None:
            runtime.supervisor_task = asyncio.create_task(_supervise_runtime(runtime))


async def _stop_runtime(runtime: CliRuntime) -> None:
    if runtime.enrichment_worker is not None:
        runtime.enrichment_worker.stop()
    if runtime.harness_ops_worker is not None:
        runtime.harness_ops_worker.stop()
    if runtime.notification_worker is not None:
        runtime.notification_worker.stop()
    if runtime.notification_delivery_worker is not None:
        runtime.notification_delivery_worker.stop()
    if runtime.asset_market_sync_worker is not None:
        runtime.asset_market_sync_worker.stop()
    if runtime.asset_resolution_worker is not None:
        runtime.asset_resolution_worker.stop()
    tasks = [
        task
        for task in (
            runtime.supervisor_task,
            runtime.collector_task,
            runtime.enrichment_task,
            runtime.harness_ops_task,
            runtime.notification_task,
            runtime.notification_delivery_task,
            runtime.asset_market_sync_task,
            runtime.asset_resolution_task,
        )
        if task is not None
    ]
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    await runtime.collector.stop()
    if runtime.asset_market_sync_worker is not None:
        runtime.asset_market_sync_worker.close()
    if runtime.asset_resolution_worker is not None:
        runtime.asset_resolution_worker.close()
    runtime.db_pool.close()


def _readiness_payload(runtime: CliRuntime, *, now_ms: int | None = None) -> tuple[dict, int]:
    now_ms = now_ms if now_ms is not None else _now_ms()
    collector_status = runtime.collector.status.to_dict()
    db_status = _db_status(runtime)
    reasons = _unhealthy_reasons(runtime, now_ms=now_ms, db_status=db_status)
    payload = {
        "ok": not reasons,
        "reasons": reasons,
        "collector": collector_status,
        "handles": list(runtime.settings.handles),
        "store": "postgresql",
        "db": db_status,
        "enrichment": {
            "llm_configured": runtime.settings.llm_configured,
            "worker_running": _task_running(runtime.enrichment_task),
            "job_counts": _enrichment_job_counts(runtime),
        },
        "harness_ops": {
            "worker_running": _task_running(runtime.harness_ops_task),
            "last_run_at_ms": runtime.harness_ops_worker.last_run_at_ms if runtime.harness_ops_worker else None,
            "last_result": runtime.harness_ops_worker.last_result if runtime.harness_ops_worker else None,
        },
        "notifications": {
            "enabled": runtime.settings.notifications.enabled,
            "worker_running": _task_running(runtime.notification_task),
            "delivery_worker_running": _task_running(runtime.notification_delivery_task),
            "summary": _notification_summary(runtime),
        },
        "asset_resolution": {
            "okx_dex_configured": runtime.settings.okx_dex_configured,
            "worker_running": _task_running(runtime.asset_resolution_task),
            "last_run_at_ms": runtime.asset_resolution_worker.last_run_at_ms
            if runtime.asset_resolution_worker
            else None,
            "last_result": runtime.asset_resolution_worker.last_result if runtime.asset_resolution_worker else None,
        },
        "asset_market_sync": {
            "okx_cex_sync_enabled": runtime.settings.okx_cex_sync_enabled,
            "worker_running": _task_running(runtime.asset_market_sync_task),
            "last_run_at_ms": runtime.asset_market_sync_worker.last_run_at_ms
            if runtime.asset_market_sync_worker
            else None,
            "last_result": runtime.asset_market_sync_worker.last_result if runtime.asset_market_sync_worker else None,
        },
    }
    return payload, 503 if reasons else 200


def _unhealthy_reasons(runtime: CliRuntime, *, now_ms: int, db_status: dict[str, object]) -> list[str]:
    reasons = _watchdog_unhealthy_reasons(runtime, now_ms=now_ms)
    if not db_status.get("ok"):
        reasons.append("database_unhealthy")
    return reasons


def _watchdog_unhealthy_reasons(runtime: CliRuntime, *, now_ms: int) -> list[str]:
    reasons = _collector_unhealthy_reasons(runtime, now_ms=now_ms)
    if runtime.settings.llm_configured and not _task_running(runtime.enrichment_task):
        reasons.append("enrichment_worker_stopped")
    if runtime.harness_ops_worker is not None and not _task_running(runtime.harness_ops_task):
        reasons.append("harness_ops_worker_stopped")
    if runtime.settings.notifications.enabled and not _task_running(runtime.notification_task):
        reasons.append("notification_worker_stopped")
    if runtime.notification_delivery_worker is not None and not _task_running(runtime.notification_delivery_task):
        reasons.append("notification_delivery_worker_stopped")
    if runtime.asset_market_sync_worker is not None and not _task_running(runtime.asset_market_sync_task):
        reasons.append("asset_market_sync_worker_stopped")
    if runtime.settings.okx_dex_configured and not _task_running(runtime.asset_resolution_task):
        reasons.append("asset_resolution_worker_stopped")
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


def _db_status(runtime: CliRuntime) -> dict[str, object]:
    try:
        with runtime.db_pool.connection() as conn:
            return postgres_health_check(conn)
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__, "detail": str(exc)}


def _enrichment_job_counts(runtime: CliRuntime) -> dict[str, int]:
    try:
        with runtime.repositories() as repos:
            return repos.enrichment.job_counts()
    except Exception:
        return {}


def _notification_summary(runtime: CliRuntime) -> dict[str, object]:
    try:
        with runtime.repositories() as repos:
            return repos.notifications.summary(subscriber_key="local")
    except Exception:
        return {}


def _task_running(task: asyncio.Task | None) -> bool:
    return task is not None and not task.done()


async def _supervise_runtime(runtime: CliRuntime) -> None:
    interval = max(1.0, float(runtime.settings.collector_watchdog_interval))
    while True:
        await asyncio.sleep(interval)
        reasons = _watchdog_unhealthy_reasons(runtime, now_ms=_now_ms())
        if not reasons:
            continue
        logger.error(f"Collector watchdog exiting unhealthy process: reasons={reasons}")
        os._exit(1)


def _now_ms() -> int:
    return int(time.time() * 1000)
