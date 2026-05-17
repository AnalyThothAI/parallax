from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass, fields, is_dataclass
from threading import Thread
from typing import Any

from gmgn_twitter_intel.app.runtime.db_pool_bundle import DBPoolBundle
from gmgn_twitter_intel.app.runtime.llm_gateway import LLMGateway
from gmgn_twitter_intel.app.runtime.providers_wiring import WiredProviders, wire_providers
from gmgn_twitter_intel.app.runtime.repository_session import PooledRepository
from gmgn_twitter_intel.app.runtime.telemetry import TelemetryRegistry
from gmgn_twitter_intel.app.runtime.worker_factories import construct_workers
from gmgn_twitter_intel.app.runtime.worker_scheduler import WorkerScheduler
from gmgn_twitter_intel.app.surfaces.api.ws import PublicWebSocketHub
from gmgn_twitter_intel.domains.asset_market.services.event_market_capture import (
    EventMarketCaptureService,
    TickLookup,
)
from gmgn_twitter_intel.domains.evidence.repositories.entity_repository import EntityRepository
from gmgn_twitter_intel.domains.evidence.repositories.evidence_repository import EvidenceRepository
from gmgn_twitter_intel.domains.evidence.services.ingest_service import IngestService
from gmgn_twitter_intel.domains.ingestion.runtime.collector_service import CollectorService
from gmgn_twitter_intel.domains.notifications.repositories.notification_repository import NotificationRepository
from gmgn_twitter_intel.domains.social_enrichment.interfaces import EnrichmentRepository
from gmgn_twitter_intel.domains.token_intel.interfaces import SignalRepository
from gmgn_twitter_intel.platform.config.settings import Settings
from gmgn_twitter_intel.platform.db.postgres_client import postgres_health_check
from gmgn_twitter_intel.platform.db.postgres_migrations import latest_migration_version


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
    evidence: Any | None = None
    entities: Any | None = None
    signals: Any | None = None
    enrichment: Any | None = None
    notifications: Any | None = None
    read_evidence: Any | None = None
    read_entities: Any | None = None
    read_signals: Any | None = None
    read_enrichment: Any | None = None
    read_notifications: Any | None = None
    ingest: Any | None = None
    stock_quote_provider: Any | None = None

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
    providers: WiredProviders | None = None
    try:
        db = DBPoolBundle.create(settings, telemetry=telemetry)
        with db.api_pool.connection() as conn:
            startup_db = postgres_health_check(conn, expected_migration_version=latest_migration_version())
        if not startup_db.get("ok"):
            raise RuntimeError(f"postgres health check failed: {startup_db}")

        if settings.llm_configured or settings.pulse_agent_configured or settings.watchlist_handle_summary_configured:
            llm_gateway = LLMGateway.create(settings)
        providers = wire_providers(
            settings,
            start_collector=start_collector,
            llm_gateway=llm_gateway,
            db_pool=db.tool_pool,
        )
        runtime = _assemble_runtime(
            settings=settings,
            db=db,
            telemetry=telemetry,
            providers=providers,
            start_collector=start_collector,
            llm_gateway=llm_gateway,
        )
    except Exception as exc:
        if providers is not None:
            for error in _cleanup_provider_roots_sync(providers):
                exc.add_note(f"provider cleanup failed: {type(error).__name__}: {error}")
        if llm_gateway is not None:
            for error in _cleanup_provider_roots_sync(llm_gateway):
                exc.add_note(f"llm gateway cleanup failed: {type(error).__name__}: {error}")
        if db is not None:
            _close_db_pools(db.api_pool, db.worker_pool, db.tool_pool, db.wake_pool)
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
) -> Runtime:
    workers = settings.workers
    worker_collector_enabled = bool(
        start_collector and workers.collector.enabled and providers.ingestion.upstream_client_factory is not None
    )
    evidence = PooledRepository(db.api_pool, EvidenceRepository)
    entities = PooledRepository(db.api_pool, EntityRepository)
    signals = PooledRepository(db.api_pool, SignalRepository)
    enrichment = PooledRepository(db.api_pool, EnrichmentRepository)
    notifications = PooledRepository(db.api_pool, NotificationRepository)
    ingest = _PooledIngestStore(db, providers=providers.asset_market)
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
        evidence=evidence,
        entities=entities,
        signals=signals,
        enrichment=enrichment,
        notifications=notifications,
        read_evidence=evidence,
        read_entities=entities,
        read_signals=signals,
        read_enrichment=enrichment,
        read_notifications=notifications,
        ingest=ingest,
        stock_quote_provider=providers.marketlane.stock_quote_provider,
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
        now_ms: Any = None,
    ):
        self.db = db
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
            ingest = _ingest_service_for_repos(repos)
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
            ingest = _ingest_service_for_repos(repos)
            return ingest.commit_prepared_event(prepared, resolutions=resolutions, captures=captures)

    def event_token_resolutions(self, event_id: str) -> list[dict[str, Any]]:
        with self.db.worker_session("collector") as repos:
            return repos.event_tokens.for_event(str(event_id))


def _ingest_service_for_repos(repos: Any) -> IngestService:
    return IngestService(
        evidence=repos.evidence,
        entities=repos.entities,
        signals=repos.signals,
        enrichment=repos.enrichment,
        registry=repos.registry,
        identity_evidence=repos.identity_evidence,
        token_intent_lookup=repos.token_intent_lookup,
        token_evidence=getattr(repos, "token_evidence", None),
        token_intents=getattr(repos, "token_intents", None),
        intent_resolutions=getattr(repos, "intent_resolutions", None),
        market_ticks=getattr(repos, "market_ticks", None),
        enriched_events=getattr(repos, "enriched_events", None),
    )


def _prepared_value(prepared: Any, key: str) -> Any:
    if isinstance(prepared, dict):
        return prepared[key]
    return getattr(prepared, key)


def _now_ms() -> int:
    return int(time.time() * 1000)


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


async def _cleanup_runtime_providers(runtime: Runtime) -> list[Exception]:
    errors: list[Exception] = []
    for provider in _provider_cleanup_targets(runtime.providers, runtime.stock_quote_provider, runtime.llm_gateway):
        close = getattr(provider, "aclose", None) or getattr(provider, "close", None)
        if close is None:
            continue
        try:
            await _maybe_await(close())
        except Exception as exc:
            errors.append(exc)
    return errors


def _cleanup_provider_roots_sync(*roots: Any) -> list[Exception]:
    errors: list[Exception] = []
    for provider in _provider_cleanup_targets(*roots):
        close = getattr(provider, "aclose", None) or getattr(provider, "close", None)
        if close is None:
            continue
        try:
            result = close()
            if inspect.isawaitable(result):
                _await_sync(result)
        except Exception as exc:
            errors.append(exc)
    return errors


def _provider_cleanup_targets(*roots: Any) -> list[Any]:
    seen: set[int] = set()
    closable_seen: set[int] = set()
    targets: list[Any] = []

    def walk(value: Any) -> None:
        if value is None or isinstance(value, str | bytes | int | float | bool):
            return
        if inspect.isclass(value) or inspect.ismodule(value) or inspect.isroutine(value):
            return
        object_id = id(value)
        if object_id in seen:
            return
        seen.add(object_id)
        if _has_close_method(value) and object_id not in closable_seen:
            targets.append(value)
            closable_seen.add(object_id)
            return
        if is_dataclass(value) and not isinstance(value, type):
            for field in fields(value):
                walk(getattr(value, field.name, None))
            return
        if isinstance(value, Mapping):
            for item in value.values():
                walk(item)
            return
        if isinstance(value, list | tuple | set | frozenset):
            for item in value:
                walk(item)
            return
        values = _object_values_for_cleanup(value)
        for item in values:
            walk(item)

    for root in roots:
        walk(root)
    return targets


def _object_values_for_cleanup(value: Any) -> list[Any]:
    if hasattr(value, "__dict__"):
        return list(vars(value).values())
    slots = getattr(type(value), "__slots__", ())
    if isinstance(slots, str):
        slots = (slots,)
    return [getattr(value, slot) for slot in slots if hasattr(value, slot)]


def _has_close_method(value: Any) -> bool:
    return callable(getattr(value, "aclose", None)) or callable(getattr(value, "close", None))


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


def _close_db_pools(*pools: Any) -> None:
    for pool in pools:
        close = getattr(pool, "close", None)
        if close:
            with suppress(Exception):
                close()


def _error_text(exc: BaseException) -> str:
    text = str(exc).strip()
    return f"{type(exc).__name__}: {text}" if text else type(exc).__name__
