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

from gmgn_twitter_intel.app.runtime.providers_wiring import WiredProviders, wire_providers
from gmgn_twitter_intel.app.runtime.repository_session import PooledRepository, repository_session
from gmgn_twitter_intel.app.surfaces.api.http import (
    ApiBadRequest,
    ApiUnauthorized,
    api_bad_request_response,
    api_unauthorized_response,
    create_api_router,
)
from gmgn_twitter_intel.app.surfaces.api.ws import PublicWebSocketHub
from gmgn_twitter_intel.domains.account_quality.read_models.account_alert_service import AccountAlertService
from gmgn_twitter_intel.domains.asset_market.runtime.asset_market_sync_worker import AssetMarketSyncWorker
from gmgn_twitter_intel.domains.asset_market.runtime.dex_market_stream_worker import DexMarketStreamWorker
from gmgn_twitter_intel.domains.asset_market.runtime.message_market_observation_worker import (
    MessageMarketObservationWorker,
)
from gmgn_twitter_intel.domains.asset_market.runtime.token_discovery_worker import TokenDiscoveryWorker
from gmgn_twitter_intel.domains.closed_loop_harness.interfaces import HarnessRepository, HarnessService
from gmgn_twitter_intel.domains.closed_loop_harness.runtime.harness_ops_worker import HarnessOpsWorker
from gmgn_twitter_intel.domains.evidence.repositories.entity_repository import EntityRepository
from gmgn_twitter_intel.domains.evidence.repositories.evidence_repository import EvidenceRepository
from gmgn_twitter_intel.domains.evidence.services.ingest_service import IngestService
from gmgn_twitter_intel.domains.ingestion.runtime.collector_service import CollectorService
from gmgn_twitter_intel.domains.notifications.repositories.notification_repository import NotificationRepository
from gmgn_twitter_intel.domains.notifications.runtime.notification_delivery import NotificationDeliveryWorker
from gmgn_twitter_intel.domains.notifications.runtime.notification_worker import NotificationWorker
from gmgn_twitter_intel.domains.notifications.services.notification_rules import NotificationRuleEngine
from gmgn_twitter_intel.domains.pulse_lab.runtime.pulse_candidate_worker import (
    PulseCandidateWorker,
    PulseTriggerThresholds,
)
from gmgn_twitter_intel.domains.pulse_lab.services.pulse_candidate_gate import PulseGateThresholds
from gmgn_twitter_intel.domains.social_enrichment.interfaces import EnrichmentRepository
from gmgn_twitter_intel.domains.social_enrichment.runtime.enrichment_worker import EnrichmentWorker
from gmgn_twitter_intel.domains.token_intel._constants import TOKEN_RADAR_PROJECTION_VERSION
from gmgn_twitter_intel.domains.token_intel.interfaces import SignalRepository
from gmgn_twitter_intel.domains.token_intel.read_models.asset_flow_service import AssetFlowService
from gmgn_twitter_intel.domains.token_intel.runtime.token_radar_projection_worker import TokenRadarProjectionWorker
from gmgn_twitter_intel.platform.config.settings import Settings, load_settings
from gmgn_twitter_intel.platform.db.postgres_client import create_pool, postgres_health_check, with_password_from_file
from gmgn_twitter_intel.platform.db.postgres_migrations import latest_migration_version


@dataclass(slots=True)
class CliRuntime:
    settings: Settings
    providers: WiredProviders
    db_pool: object
    evidence: object
    entities: object
    signals: object
    enrichment: object
    harness: object
    notifications: object
    read_evidence: object
    read_entities: object
    read_signals: object
    read_enrichment: object
    read_harness: object
    read_notifications: object
    ingest: IngestService
    hub: PublicWebSocketHub
    collector: CollectorService
    start_collector: bool
    enrichment_worker: EnrichmentWorker | None = None
    harness_ops_worker: HarnessOpsWorker | None = None
    notification_worker: NotificationWorker | None = None
    notification_delivery_worker: NotificationDeliveryWorker | None = None
    asset_market_sync_worker: AssetMarketSyncWorker | None = None
    message_market_observation_worker: MessageMarketObservationWorker | None = None
    token_discovery_worker: TokenDiscoveryWorker | None = None
    dex_market_stream_worker: DexMarketStreamWorker | None = None
    token_radar_projection_worker: TokenRadarProjectionWorker | None = None
    pulse_candidate_worker: PulseCandidateWorker | None = None
    collector_task: asyncio.Task | None = None
    supervisor_task: asyncio.Task | None = None
    enrichment_task: asyncio.Task | None = None
    harness_ops_task: asyncio.Task | None = None
    notification_task: asyncio.Task | None = None
    notification_delivery_task: asyncio.Task | None = None
    asset_market_sync_task: asyncio.Task | None = None
    message_market_observation_task: asyncio.Task | None = None
    token_discovery_task: asyncio.Task | None = None
    dex_market_stream_task: asyncio.Task | None = None
    token_radar_projection_task: asyncio.Task | None = None
    pulse_candidate_task: asyncio.Task | None = None

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
    app.add_api_route("/signal-lab", frontend_index, include_in_schema=False)
    app.add_api_route("/signal-lab/{path:path}", frontend_index, include_in_schema=False)
    app.add_api_route("/token", frontend_index, include_in_schema=False)
    app.add_api_route("/token/{path:path}", frontend_index, include_in_schema=False)


def _frontend_dist_dir(frontend_dist: str | Path | None = None) -> Path | None:
    candidates: list[Path] = []
    if frontend_dist is not None:
        candidates.append(Path(frontend_dist))
    module_path = Path(__file__).resolve()
    candidates.extend(
        [
            module_path.parents[2] / "web" / "dist",
            module_path.parents[4] / "web" / "dist",
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
                registry=repos.registry,
                identity_evidence=repos.identity_evidence,
                price_observations=repos.price_observations,
                token_intent_lookup=repos.token_intent_lookup,
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
        startup_db = postgres_health_check(conn, expected_migration_version=latest_migration_version())
    if not startup_db.get("ok"):
        db_pool.close()
        raise RuntimeError(f"postgres health check failed: {startup_db}")
    providers = wire_providers(settings, start_collector=start_collector)
    evidence = PooledRepository(db_pool, EvidenceRepository)
    entities = PooledRepository(db_pool, EntityRepository)
    signals = PooledRepository(db_pool, SignalRepository)
    enrichment = PooledRepository(db_pool, EnrichmentRepository)
    harness = PooledRepository(db_pool, HarnessRepository)
    notifications = PooledRepository(db_pool, NotificationRepository)
    read_evidence = evidence
    read_entities = entities
    read_signals = signals
    read_enrichment = enrichment
    read_harness = harness
    read_notifications = notifications
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
        providers=providers,
        db_pool=db_pool,
        evidence=evidence,
        entities=entities,
        signals=signals,
        enrichment=enrichment,
        harness=harness,
        notifications=notifications,
        read_evidence=read_evidence,
        read_entities=read_entities,
        read_signals=read_signals,
        read_enrichment=read_enrichment,
        read_harness=read_harness,
        read_notifications=read_notifications,
        ingest=ingest,
        hub=hub,
        collector=collector,
        start_collector=start_collector,
    )
    runtime.harness_ops_worker = HarnessOpsWorker(
        repository_session=lambda: repository_session(db_pool),
    )
    runtime.token_radar_projection_worker = TokenRadarProjectionWorker(
        repository_session=lambda: repository_session(db_pool),
    )
    if settings.pulse_agent_enabled and settings.pulse_agent_configured:
        runtime.pulse_candidate_worker = PulseCandidateWorker(
            recommendation_client=providers.pulse_lab.recommendation_provider,
            repository_session=lambda: repository_session(db_pool),
            poll_interval=settings.pulse_agent_interval_seconds,
            batch_size=settings.pulse_agent_batch_size,
            max_attempts=settings.pulse_agent_max_attempts,
            trigger_thresholds=PulseTriggerThresholds(
                min_rank_score=settings.pulse_agent_trigger_min_rank_score,
            ),
            gate_thresholds=PulseGateThresholds(
                trade_candidate_min=settings.pulse_agent_gate_trade_candidate_min,
                token_watch_min=settings.pulse_agent_gate_token_watch_min,
                high_info_rejection_min=settings.pulse_agent_gate_high_info_rejection_min,
                high_conviction_min=settings.pulse_agent_gate_high_conviction_min,
            ),
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
        runtime.asset_market_sync_worker = AssetMarketSyncWorker(
            cex_market=providers.asset_market.sync_cex_market,
            dex_market=providers.asset_market.sync_dex_market,
            repository_session=lambda: repository_session(db_pool),
            inst_types=settings.okx_cex_inst_types,
            interval_seconds=settings.okx_cex_sync_interval_seconds,
            dex_interval_seconds=settings.okx_dex_sync_interval_seconds,
            dex_stale_after_ms=int(settings.okx_dex_price_warm_stale_seconds * 1000),
            dex_hot_stale_after_ms=int(settings.okx_dex_price_hot_stale_seconds * 1000),
            dex_warm_stale_after_ms=int(settings.okx_dex_price_warm_stale_seconds * 1000),
            dex_refresh_limit=settings.okx_dex_price_refresh_limit,
        )
        runtime.message_market_observation_worker = MessageMarketObservationWorker(
            cex_market=providers.asset_market.message_cex_market,
            dex_market=providers.asset_market.message_dex_market,
            repository_session=lambda: repository_session(db_pool),
        )
    if start_collector and settings.okx_dex_configured:
        runtime.token_discovery_worker = TokenDiscoveryWorker(
            dex_market=providers.asset_market.discovery_dex_market,
            repository_session=lambda: repository_session(db_pool),
            chain_ids=providers.asset_market.discovery_chain_ids,
            interval_seconds=30.0,
        )
    if start_collector and providers.asset_market.stream_dex_market is not None:
        runtime.dex_market_stream_worker = DexMarketStreamWorker(
            stream_provider=providers.asset_market.stream_dex_market,
            repository_session=lambda: repository_session(db_pool),
            projection_version=TOKEN_RADAR_PROJECTION_VERSION,
            subscription_limit=settings.okx_dex_ws_subscription_limit,
            hot_target_ttl_seconds=settings.okx_dex_ws_hot_target_ttl_seconds,
            reconnect_delay_seconds=settings.okx_dex_ws_reconnect_delay_seconds,
            on_market_update=hub.publish,
        )
    if settings.llm_configured:
        runtime.enrichment_worker = EnrichmentWorker(
            client=providers.social_enrichment.event_enrichment,
            publisher=hub,
            repository_session=lambda: repository_session(db_pool),
            poll_interval=settings.enrichment_poll_interval,
            concurrency=settings.enrichment_concurrency,
        )
    if start_collector:
        factory = providers.ingestion.upstream_client_factory
        collector.upstream_client = factory(collector.handle_frame) if factory is not None else None
    return runtime


def _notification_rule_engine(settings: Settings, repos) -> NotificationRuleEngine:
    return NotificationRuleEngine(
        settings=settings,
        evidence=repos.evidence,
        account_alerts=AccountAlertService(repos.signals),
        asset_flow=AssetFlowService(token_radar=repos.token_radar, current_market=repos.current_market),
        harness=HarnessService(repos.harness),
        pulse=repos.pulse,
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
    if runtime.message_market_observation_worker is not None and runtime.message_market_observation_task is None:
        runtime.message_market_observation_task = asyncio.create_task(runtime.message_market_observation_worker.run())
    if runtime.token_discovery_worker is not None and runtime.token_discovery_task is None:
        runtime.token_discovery_task = asyncio.create_task(runtime.token_discovery_worker.run())
    dex_market_stream_worker = getattr(runtime, "dex_market_stream_worker", None)
    if dex_market_stream_worker is not None and getattr(runtime, "dex_market_stream_task", None) is None:
        runtime.dex_market_stream_task = asyncio.create_task(dex_market_stream_worker.run())
    if runtime.token_radar_projection_worker is not None and runtime.token_radar_projection_task is None:
        runtime.token_radar_projection_task = asyncio.create_task(runtime.token_radar_projection_worker.run())
    if runtime.pulse_candidate_worker is not None and runtime.pulse_candidate_task is None:
        runtime.pulse_candidate_task = asyncio.create_task(runtime.pulse_candidate_worker.run())
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
    if runtime.message_market_observation_worker is not None:
        runtime.message_market_observation_worker.stop()
    if runtime.token_discovery_worker is not None:
        runtime.token_discovery_worker.stop()
    dex_market_stream_worker = getattr(runtime, "dex_market_stream_worker", None)
    if dex_market_stream_worker is not None:
        dex_market_stream_worker.stop()
    if runtime.token_radar_projection_worker is not None:
        runtime.token_radar_projection_worker.stop()
    if runtime.pulse_candidate_worker is not None:
        runtime.pulse_candidate_worker.stop()
    token_radar_projection_task = runtime.token_radar_projection_task
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
            runtime.message_market_observation_task,
            runtime.token_discovery_task,
            getattr(runtime, "dex_market_stream_task", None),
            runtime.pulse_candidate_task,
        )
        if task is not None
    ]
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    if token_radar_projection_task is not None:
        try:
            await asyncio.wait_for(token_radar_projection_task, timeout=30.0)
        except TimeoutError:
            token_radar_projection_task.cancel()
            await asyncio.gather(token_radar_projection_task, return_exceptions=True)
    await runtime.collector.stop()
    if runtime.asset_market_sync_worker is not None:
        runtime.asset_market_sync_worker.close()
    if runtime.message_market_observation_worker is not None:
        runtime.message_market_observation_worker.close()
    if runtime.token_discovery_worker is not None:
        runtime.token_discovery_worker.close()
    if dex_market_stream_worker is not None:
        dex_market_stream_worker.close()
    if runtime.token_radar_projection_worker is not None:
        runtime.token_radar_projection_worker.close()
    if runtime.pulse_candidate_worker is not None:
        await runtime.pulse_candidate_worker.aclose()
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
            "concurrency": runtime.settings.enrichment_concurrency,
            "backend": "openai_agents_sdk",
            "trace_enabled": runtime.settings.llm_trace_enabled,
            "trace_export_configured": runtime.settings.llm_trace_export_configured,
            "trace_include_sensitive_data": runtime.settings.llm_trace_include_sensitive_data,
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
        "token_radar_projection": {
            "worker_running": _task_running(runtime.token_radar_projection_task),
            "last_started_at_ms": runtime.token_radar_projection_worker.last_started_at_ms
            if runtime.token_radar_projection_worker
            else None,
            "last_run_at_ms": runtime.token_radar_projection_worker.last_run_at_ms
            if runtime.token_radar_projection_worker
            else None,
            "last_result": runtime.token_radar_projection_worker.last_result
            if runtime.token_radar_projection_worker
            else None,
            "last_error": runtime.token_radar_projection_worker.last_error
            if runtime.token_radar_projection_worker
            else None,
        },
        "pulse_agent": {
            "enabled": runtime.settings.pulse_agent_enabled,
            "configured": runtime.settings.pulse_agent_configured,
            "worker_running": _task_running(runtime.pulse_candidate_task),
            "model": runtime.settings.pulse_agent_model,
            "batch_size": runtime.settings.pulse_agent_batch_size,
            "interval_seconds": runtime.settings.pulse_agent_interval_seconds,
            "max_attempts": runtime.settings.pulse_agent_max_attempts,
            "last_started_at_ms": runtime.pulse_candidate_worker.last_started_at_ms
            if runtime.pulse_candidate_worker
            else None,
            "last_run_at_ms": runtime.pulse_candidate_worker.last_run_at_ms if runtime.pulse_candidate_worker else None,
            "last_result": runtime.pulse_candidate_worker.last_result if runtime.pulse_candidate_worker else None,
            "last_error": runtime.pulse_candidate_worker.last_error if runtime.pulse_candidate_worker else None,
        },
        "asset_market_sync": {
            "okx_cex_sync_enabled": runtime.settings.okx_cex_sync_enabled,
            "worker_running": _task_running(runtime.asset_market_sync_task),
            "last_started_at_ms": runtime.asset_market_sync_worker.last_started_at_ms
            if runtime.asset_market_sync_worker
            else None,
            "last_run_at_ms": runtime.asset_market_sync_worker.last_run_at_ms
            if runtime.asset_market_sync_worker
            else None,
            "last_result": runtime.asset_market_sync_worker.last_result if runtime.asset_market_sync_worker else None,
            "last_error": runtime.asset_market_sync_worker.last_error if runtime.asset_market_sync_worker else None,
            "providers": runtime.asset_market_sync_worker.provider_states if runtime.asset_market_sync_worker else {},
        },
        "message_market_observation": {
            "worker_running": _task_running(runtime.message_market_observation_task),
            "last_started_at_ms": runtime.message_market_observation_worker.last_started_at_ms
            if runtime.message_market_observation_worker
            else None,
            "last_run_at_ms": runtime.message_market_observation_worker.last_run_at_ms
            if runtime.message_market_observation_worker
            else None,
            "last_result": runtime.message_market_observation_worker.last_result
            if runtime.message_market_observation_worker
            else None,
            "last_error": runtime.message_market_observation_worker.last_error
            if runtime.message_market_observation_worker
            else None,
        },
        "token_discovery": {
            "worker_running": _task_running(runtime.token_discovery_task),
            "last_started_at_ms": runtime.token_discovery_worker.last_started_at_ms
            if runtime.token_discovery_worker
            else None,
            "last_run_at_ms": runtime.token_discovery_worker.last_run_at_ms if runtime.token_discovery_worker else None,
            "last_result": runtime.token_discovery_worker.last_result if runtime.token_discovery_worker else None,
            "last_error": runtime.token_discovery_worker.last_error if runtime.token_discovery_worker else None,
        },
        "dex_market_stream": {
            "configured": getattr(runtime.settings, "okx_dex_ws_configured", False),
            "worker_running": _task_running(getattr(runtime, "dex_market_stream_task", None)),
            "subscription_limit": getattr(runtime.settings, "okx_dex_ws_subscription_limit", None),
            "last_started_at_ms": getattr(runtime, "dex_market_stream_worker", None).last_started_at_ms
            if getattr(runtime, "dex_market_stream_worker", None)
            else None,
            "last_run_at_ms": getattr(runtime, "dex_market_stream_worker", None).last_run_at_ms
            if getattr(runtime, "dex_market_stream_worker", None)
            else None,
            "last_result": getattr(runtime, "dex_market_stream_worker", None).last_result
            if getattr(runtime, "dex_market_stream_worker", None)
            else None,
            "last_error": getattr(runtime, "dex_market_stream_worker", None).last_error
            if getattr(runtime, "dex_market_stream_worker", None)
            else None,
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
    if runtime.message_market_observation_worker is not None and not _task_running(
        runtime.message_market_observation_task
    ):
        reasons.append("message_market_observation_worker_stopped")
    if runtime.token_discovery_worker is not None and not _task_running(runtime.token_discovery_task):
        reasons.append("token_discovery_worker_stopped")
    dex_market_stream_worker = getattr(runtime, "dex_market_stream_worker", None)
    if dex_market_stream_worker is not None and not _task_running(getattr(runtime, "dex_market_stream_task", None)):
        reasons.append("dex_market_stream_worker_stopped")
    if runtime.token_radar_projection_worker is not None and not _task_running(runtime.token_radar_projection_task):
        reasons.append("token_radar_projection_worker_stopped")
    if runtime.pulse_candidate_worker is not None and not _task_running(runtime.pulse_candidate_task):
        reasons.append("pulse_candidate_worker_stopped")
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
            return postgres_health_check(conn, expected_migration_version=latest_migration_version())
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
