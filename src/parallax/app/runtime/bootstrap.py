from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping
from dataclasses import dataclass
from threading import Thread
from typing import Any

from parallax.app.runtime.db_pool_bundle import DBPoolBundle
from parallax.app.runtime.llm_gateway import LLMGateway
from parallax.app.runtime.provider_wiring.model_execution import build_agent_execution_gateway
from parallax.app.runtime.providers_wiring import WiredProviders, wire_providers
from parallax.app.runtime.repository_session import PooledRepository
from parallax.app.runtime.telemetry import TelemetryRegistry
from parallax.app.runtime.worker_factories import construct_workers
from parallax.app.runtime.worker_scheduler import WorkerScheduler
from parallax.app.surfaces.api.ws import PublicWebSocketHub
from parallax.domains.asset_market.services.event_market_capture import (
    EventMarketCaptureService,
    TickLookup,
)
from parallax.domains.evidence.repositories.entity_repository import EntityRepository
from parallax.domains.evidence.repositories.evidence_repository import EvidenceRepository
from parallax.domains.evidence.services.ingest_service import IngestService
from parallax.domains.ingestion.runtime.collector_service import CollectorService
from parallax.domains.notifications.repositories.notification_repository import NotificationRepository
from parallax.domains.token_intel.interfaces import SignalRepository
from parallax.platform.config.settings import Settings
from parallax.platform.db.postgres_client import postgres_health_check
from parallax.platform.db.postgres_migrations import latest_migration_version


@dataclass(slots=True)
class Runtime:
    settings: Settings
    db: DBPoolBundle
    telemetry: TelemetryRegistry
    providers: WiredProviders
    hub: PublicWebSocketHub
    collector: CollectorService
    start_collector: bool
    workers: Mapping[str, Any]
    scheduler: WorkerScheduler
    llm_gateway: Any | None = None
    agent_execution_gateway: Any | None = None
    evidence: Any | None = None
    entities: Any | None = None
    signals: Any | None = None
    notifications: Any | None = None
    read_evidence: Any | None = None
    read_entities: Any | None = None
    read_signals: Any | None = None
    read_notifications: Any | None = None
    ingest: Any | None = None

    def repositories(self):
        return self.db.api_session()

    @property
    def collector_status(self):
        return self.collector.status

    async def aclose(self) -> None:
        scheduler_error: Exception | None = None
        try:
            await self.scheduler.stop()
        except Exception as exc:
            scheduler_error = exc
        provider_errors = await _cleanup_runtime_providers(self)
        if scheduler_error is not None:
            if provider_errors:
                raise ExceptionGroup("runtime_close_failed", [scheduler_error, *provider_errors])
            raise scheduler_error
        if provider_errors:
            raise ExceptionGroup("provider_cleanup_failed", provider_errors)


def bootstrap(settings: Settings, *, start_collector: bool = True) -> Runtime:
    if not settings.ws_token:
        raise ValueError("ws_token is required in config.yaml")
    telemetry = TelemetryRegistry()
    db: DBPoolBundle | None = None
    llm_gateway: LLMGateway | None = None
    agent_execution_gateway: Any | None = None
    providers: WiredProviders | None = None
    try:
        db = DBPoolBundle.create(settings, telemetry=telemetry)
        with db.api_pool.connection() as conn:
            startup_db = postgres_health_check(conn, expected_migration_version=latest_migration_version())
        if not startup_db.get("ok"):
            raise RuntimeError(f"postgres health check failed: {startup_db}")

        if settings.pulse_agent_configured or settings.news_item_brief_configured:
            llm_gateway = LLMGateway.create(settings)
            agent_execution_gateway = build_agent_execution_gateway(
                settings,
                llm_gateway=llm_gateway,
                telemetry=telemetry,
            )
        providers = wire_providers(
            settings,
            start_collector=start_collector,
            agent_execution_gateway=agent_execution_gateway,
            db_pool=db.tool_pool,
        )
        runtime = _assemble_runtime(
            settings=settings,
            db=db,
            telemetry=telemetry,
            providers=providers,
            start_collector=start_collector,
            llm_gateway=llm_gateway,
            agent_execution_gateway=agent_execution_gateway,
        )
    except Exception as exc:
        for error in _cleanup_provider_roots_sync(providers, agent_execution_gateway, llm_gateway):
            exc.add_note(f"provider cleanup failed: {type(error).__name__}: {error}")
        if db is not None:
            try:
                _close_db_bundle_sync(db)
            except Exception as cleanup_exc:
                exc.add_note(f"db pool bundle cleanup failed: {type(cleanup_exc).__name__}: {cleanup_exc}")
        raise
    return runtime


def _assemble_runtime(
    *,
    settings: Settings,
    db: DBPoolBundle,
    telemetry: TelemetryRegistry,
    providers: WiredProviders,
    start_collector: bool,
    llm_gateway: Any | None,
    agent_execution_gateway: Any | None = None,
) -> Runtime:
    workers = settings.workers
    worker_collector_enabled = bool(
        start_collector and workers.collector.enabled and providers.ingestion.upstream_client_factory is not None
    )
    evidence = PooledRepository(db.api_pool, EvidenceRepository)
    entities = PooledRepository(db.api_pool, EntityRepository)
    signals = PooledRepository(db.api_pool, SignalRepository)
    notifications = PooledRepository(
        db.api_pool,
        NotificationRepository,
        running_timeout_ms=db.notification_delivery_running_timeout_ms,
        stale_running_terminalization_batch_size=db.notification_delivery_stale_running_terminalization_batch_size,
    )
    ingest = _PooledIngestStore(
        db,
        providers=providers.asset_market,
        event_anchor_active_window_ms=workers.event_anchor_backfill.active_window_ms,
    )
    hub = PublicWebSocketHub(
        token=settings.ws_token,
        repository_session=db.api_session,
        default_replay_limit=settings.replay_limit,
    )
    collector = CollectorService(
        name="collector",
        settings=workers.collector,
        db=db,
        telemetry=telemetry,
        handles=settings.handles,
        store=ingest,
        publisher=hub,
        upstream_client=None,
    )
    wake_bus = db.wake_emitter()
    runtime_workers = construct_workers(
        settings=settings,
        db=db,
        telemetry=telemetry,
        providers=providers,
        hub=hub,
        collector=collector,
        collector_enabled=worker_collector_enabled,
        wake_bus=wake_bus,
        collector_start_requested=start_collector,
    )
    scheduler = WorkerScheduler(workers=runtime_workers, db=db)
    runtime = Runtime(
        settings=settings,
        db=db,
        telemetry=telemetry,
        providers=providers,
        hub=hub,
        collector=collector,
        start_collector=worker_collector_enabled,
        workers=runtime_workers,
        scheduler=scheduler,
        llm_gateway=llm_gateway,
        agent_execution_gateway=agent_execution_gateway,
        evidence=evidence,
        entities=entities,
        signals=signals,
        notifications=notifications,
        read_evidence=evidence,
        read_entities=entities,
        read_signals=signals,
        read_notifications=notifications,
        ingest=ingest,
    )
    if worker_collector_enabled:
        factory = providers.ingestion.upstream_client_factory
        collector.upstream_client = factory(collector.handle_frame) if factory is not None else None
    return runtime


class _PooledIngestStore:
    def __init__(
        self,
        db: DBPoolBundle,
        *,
        providers: Any,
        event_anchor_active_window_ms: int,
        now_ms: Any = None,
    ):
        self.db = db
        self.event_anchor_active_window_ms = max(1, int(event_anchor_active_window_ms))
        self._capture_service = EventMarketCaptureService(
            providers=providers,
            now_ms=now_ms or _now_ms,
        )

    def insert_raw_frame(self, **kwargs) -> bool:
        with self.db.worker_session("collector") as repos:
            return repos.evidence.insert_raw_frame(**kwargs)

    def ingest_event(self, event: Any, *, is_watched: bool):
        prepared = IngestService.prepare_event(event, is_watched=is_watched)
        market_resolutions: list[dict[str, Any]] = []
        prefetched_ticks: dict[tuple[str, str], Any] = {}
        resolutions: list[Any] = []
        with self.db.worker_session("collector") as repos:
            ingest = _ingest_service_for_repos(
                repos,
                event_anchor_active_window_ms=self.event_anchor_active_window_ms,
            )
            if ingest.event_already_exists(prepared):
                return ingest.duplicate_result(prepared)
            ingest.prepare_registry_for_resolution(prepared)
            resolutions = ingest.resolve_prepared(prepared, persist=False)
            for decision in resolutions:
                market_resolution = ingest.market_resolution_for_decision(decision)
                if market_resolution is None:
                    continue
                market_resolutions.append(market_resolution)
                prefetched_ticks[(market_resolution["target_type"], market_resolution["target_id"])] = (
                    repos.market_ticks.latest_at_or_before(
                        target_type=market_resolution["target_type"],
                        target_id=market_resolution["target_id"],
                        at_ms=_prepared_value(prepared, "event_ms"),
                        max_lag_ms=60_000,
                    )
                )

        tick_lookup = TickLookup(
            latest_at_or_before=lambda target_type, target_id, _at_ms, _max_lag_ms: prefetched_ticks.get(
                (target_type, target_id)
            )
        )
        captures = [
            self._capture_service.capture_for_event(
                event_id=market_resolution["event_id"],
                intent_id=market_resolution["intent_id"],
                resolution_id=market_resolution["resolution_id"],
                resolution=market_resolution,
                event_ms=_prepared_value(prepared, "event_ms"),
                tick_lookup=tick_lookup,
            )
            for market_resolution in market_resolutions
        ]

        with self.db.worker_session("collector") as repos:
            ingest = _ingest_service_for_repos(
                repos,
                event_anchor_active_window_ms=self.event_anchor_active_window_ms,
            )
            return ingest.commit_prepared_event(prepared, resolutions=resolutions, captures=captures)

    def event_token_resolutions(self, event_id: str) -> list[dict[str, Any]]:
        with self.db.worker_session("collector") as repos:
            return repos.event_tokens.for_event(str(event_id))


def _ingest_service_for_repos(
    repos: Any,
    *,
    event_anchor_active_window_ms: int,
) -> IngestService:
    return IngestService(
        evidence=repos.evidence,
        entities=repos.entities,
        signals=repos.signals,
        registry=repos.registry,
        identity_evidence=repos.identity_evidence,
        token_intent_lookup=repos.token_intent_lookup,
        token_evidence=repos.token_evidence,
        token_intents=repos.token_intents,
        intent_resolutions=repos.intent_resolutions,
        discovery=repos.discovery,
        market_ticks=repos.market_ticks,
        market_tick_current_dirty_targets=repos.market_tick_current_dirty_targets,
        enriched_events=repos.enriched_events,
        event_anchor_jobs=repos.event_anchor_jobs,
        token_radar_source_dirty_events=repos.token_radar_source_dirty_events,
        event_anchor_active_window_ms=event_anchor_active_window_ms,
    )


def _prepared_value(prepared: Any, key: str) -> Any:
    if isinstance(prepared, dict):
        return prepared[key]
    return getattr(prepared, key)


def _now_ms() -> int:
    return int(time.time() * 1000)


async def _cleanup_runtime_providers(runtime: Runtime) -> list[Exception]:
    errors: list[Exception] = []
    try:
        await runtime.providers.aclose()
    except Exception as exc:
        errors.append(exc)
    if runtime.agent_execution_gateway is not None:
        try:
            await runtime.agent_execution_gateway.aclose()
        except Exception as exc:
            errors.append(exc)
    if runtime.llm_gateway is not None:
        try:
            await runtime.llm_gateway.aclose()
        except Exception as exc:
            errors.append(exc)
    return errors


def _cleanup_provider_roots_sync(
    providers: WiredProviders | None,
    agent_execution_gateway: Any | None,
    llm_gateway: LLMGateway | None,
) -> list[Exception]:
    errors: list[Exception] = []
    if providers is not None:
        try:
            _await_sync(providers.aclose())
        except Exception as exc:
            errors.append(exc)
    if agent_execution_gateway is not None:
        try:
            _await_sync(agent_execution_gateway.aclose())
        except Exception as exc:
            errors.append(exc)
    if llm_gateway is not None:
        try:
            _await_sync(llm_gateway.aclose())
        except Exception as exc:
            errors.append(exc)
    return errors


def _close_db_bundle_sync(db: DBPoolBundle) -> None:
    _await_sync(db.aclose())


def _await_sync(awaitable: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)
    result: dict[str, Any] = {}

    def runner() -> None:
        try:
            result["value"] = asyncio.run(awaitable)
        except Exception as exc:
            result["error"] = exc

    thread = Thread(target=runner)
    thread.start()
    thread.join()
    if "error" in result:
        raise result["error"]
    return result.get("value")


def _error_text(exc: BaseException) -> str:
    text = str(exc).strip()
    return f"{type(exc).__name__}: {text}" if text else type(exc).__name__
