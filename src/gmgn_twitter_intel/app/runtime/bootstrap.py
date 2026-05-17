from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass, fields, is_dataclass
from threading import Thread
from types import SimpleNamespace
from typing import Any

from gmgn_twitter_intel.app.runtime.db_pool_bundle import DBPoolBundle
from gmgn_twitter_intel.app.runtime.llm_gateway import LLMGateway
from gmgn_twitter_intel.app.runtime.providers_wiring import WiredProviders, wire_providers
from gmgn_twitter_intel.app.runtime.repository_session import PooledRepository
from gmgn_twitter_intel.app.runtime.telemetry import TelemetryRegistry
from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_registry import CANONICAL_WORKER_NAMES
from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.app.runtime.worker_scheduler import WorkerScheduler
from gmgn_twitter_intel.app.surfaces.api.ws import PublicWebSocketHub
from gmgn_twitter_intel.domains.account_quality.read_models.account_alert_service import AccountAlertService
from gmgn_twitter_intel.domains.asset_market.read_models.token_profile_read_model import TokenProfileReadModel
from gmgn_twitter_intel.domains.asset_market.runtime.asset_profile_refresh_worker import AssetProfileRefreshWorker
from gmgn_twitter_intel.domains.asset_market.runtime.event_anchor_backfill_worker import EventAnchorBackfillWorker
from gmgn_twitter_intel.domains.asset_market.runtime.live_price_gateway import LivePriceGateway
from gmgn_twitter_intel.domains.asset_market.runtime.market_tick_poll_worker import MarketTickPollWorker
from gmgn_twitter_intel.domains.asset_market.runtime.market_tick_stream_worker import MarketTickStreamWorker
from gmgn_twitter_intel.domains.asset_market.runtime.resolution_refresh_worker import ResolutionRefreshWorker
from gmgn_twitter_intel.domains.asset_market.runtime.token_capture_tier_worker import TokenCaptureTierWorker
from gmgn_twitter_intel.domains.asset_market.services.event_market_capture import (
    EventMarketCaptureService,
    TickLookup,
)
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
from gmgn_twitter_intel.domains.pulse_lab.runtime.pulse_candidate_worker import PulseCandidateWorker
from gmgn_twitter_intel.domains.social_enrichment.interfaces import EnrichmentRepository
from gmgn_twitter_intel.domains.social_enrichment.runtime.enrichment_worker import EnrichmentWorker
from gmgn_twitter_intel.domains.token_intel._constants import TOKEN_RADAR_PROJECTION_VERSION
from gmgn_twitter_intel.domains.token_intel.interfaces import SignalRepository
from gmgn_twitter_intel.domains.token_intel.read_models.asset_flow_service import AssetFlowService
from gmgn_twitter_intel.domains.token_intel.runtime.token_radar_projection_worker import TokenRadarProjectionWorker
from gmgn_twitter_intel.domains.watchlist_intel.runtime.handle_summary_worker import HandleSummaryWorker
from gmgn_twitter_intel.domains.watchlist_intel.services.handle_summary_service import HandleSummaryTriggerConfig
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
    harness: Any | None = None
    notifications: Any | None = None
    read_evidence: Any | None = None
    read_entities: Any | None = None
    read_signals: Any | None = None
    read_enrichment: Any | None = None
    read_harness: Any | None = None
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
    harness = PooledRepository(db.api_pool, HarnessRepository)
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
    runtime_workers = _construct_workers(
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
        harness=harness,
        notifications=notifications,
        read_evidence=evidence,
        read_entities=entities,
        read_signals=signals,
        read_enrichment=enrichment,
        read_harness=harness,
        read_notifications=notifications,
        ingest=ingest,
        stock_quote_provider=providers.marketlane.stock_quote_provider,
    )
    if worker_collector_enabled:
        factory = providers.ingestion.upstream_client_factory
        collector.upstream_client = factory(collector.handle_frame) if factory is not None else None
    return runtime


def _construct_workers(
    *,
    settings: Settings,
    db: DBPoolBundle,
    telemetry: TelemetryRegistry,
    providers: WiredProviders,
    hub: PublicWebSocketHub,
    collector: CollectorService,
    collector_enabled: bool,
    wake_bus: Any,
) -> dict[str, Any]:
    workers = settings.workers
    constructed: dict[str, WorkerBase] = {
        name: _DisabledWorker(
            name=name,
            settings=_worker_settings(settings, name, enabled=False),
            db=db,
            telemetry=telemetry,
        )
        for name in CANONICAL_WORKER_NAMES
    }
    delivery_wake = _LocalWakeWaiter()
    asset_market = providers.asset_market
    message_cex_market = getattr(asset_market, "message_cex_market", None)
    dex_quote_market = getattr(asset_market, "dex_quote_market", None)
    dex_profile_market = getattr(asset_market, "dex_profile_market", None)
    dex_discovery_market = getattr(asset_market, "dex_discovery_market", None)
    stream_dex_market = getattr(asset_market, "stream_dex_market", None)

    if collector_enabled:
        constructed["collector"] = collector
    if workers.harness_ops.enabled:
        constructed["harness_ops"] = HarnessOpsWorker(
            name="harness_ops",
            settings=workers.harness_ops,
            db=db,
            telemetry=telemetry,
        )
    if workers.token_radar_projection.enabled:
        worker_name = "token_radar_projection"
        constructed["token_radar_projection"] = TokenRadarProjectionWorker(
            name=worker_name,
            settings=workers.token_radar_projection,
            db=db,
            telemetry=telemetry,
            wake_bus=wake_bus,
            wake_waiter=db.wake_listener(worker_name, workers.token_radar_projection.wakes_on),
        )
    if workers.token_capture_tier.enabled:
        constructed["token_capture_tier"] = TokenCaptureTierWorker(
            name="token_capture_tier",
            settings=workers.token_capture_tier,
            pool_bundle=db,
            telemetry=telemetry,
            batch_size=workers.token_capture_tier.batch_size,
            ws_limit=workers.token_capture_tier.ws_limit,
            poll_limit=workers.token_capture_tier.poll_limit,
        )
    if workers.market_tick_stream.enabled and stream_dex_market is not None:
        constructed["market_tick_stream"] = MarketTickStreamWorker(
            name="market_tick_stream",
            settings=workers.market_tick_stream,
            pool_bundle=db,
            telemetry=telemetry,
            stream_dex_market=stream_dex_market,
            wake_emitter=wake_bus,
            subscription_limit=workers.market_tick_stream.subscription_limit,
        )
    if workers.market_tick_poll.enabled and (message_cex_market is not None or dex_quote_market is not None):
        constructed["market_tick_poll"] = MarketTickPollWorker(
            name="market_tick_poll",
            settings=workers.market_tick_poll,
            pool_bundle=db,
            telemetry=telemetry,
            providers=asset_market,
            wake_emitter=wake_bus,
            batch_size=workers.market_tick_poll.batch_size,
        )
    if workers.event_anchor_backfill.enabled and (message_cex_market is not None or dex_quote_market is not None):
        constructed["event_anchor_backfill"] = EventAnchorBackfillWorker(
            name="event_anchor_backfill",
            settings=workers.event_anchor_backfill,
            pool_bundle=db,
            telemetry=telemetry,
            providers=asset_market,
            wake_emitter=wake_bus,
            batch_size=workers.event_anchor_backfill.batch_size,
            concurrency=workers.event_anchor_backfill.concurrency,
            min_age_ms=workers.event_anchor_backfill.min_age_ms,
        )
    if workers.pulse_candidate.enabled and settings.pulse_agent_configured:
        worker_name = "pulse_candidate"
        constructed["pulse_candidate"] = PulseCandidateWorker(
            name=worker_name,
            settings=workers.pulse_candidate,
            db=db,
            telemetry=telemetry,
            decision_client=providers.pulse_lab.decision_provider,
            wake_waiter=db.wake_listener(worker_name, workers.pulse_candidate.wakes_on),
        )
    if (
        workers.handle_summary.enabled
        and settings.watchlist_handle_summary_configured
        and providers.watchlist_intel.summary_provider is not None
    ):
        constructed["handle_summary"] = HandleSummaryWorker(
            name="handle_summary",
            settings=workers.handle_summary,
            db=db,
            telemetry=telemetry,
            provider=providers.watchlist_intel.summary_provider,
            handles=settings.handles,
        )
    if settings.notifications.enabled and workers.notification_rule.enabled:
        constructed["notification_rule"] = NotificationWorker(
            name="notification_rule",
            settings=workers.notification_rule,
            db=db,
            telemetry=telemetry,
            rule_engine_factory=lambda repos: _notification_rule_engine(settings, repos),
            publisher=hub,
            delivery_channels=settings.notifications.channels,
            delivery_max_attempts=workers.notification_delivery.max_attempts,
            delivery_wake=delivery_wake,
        )
    if (
        settings.notifications.enabled
        and workers.notification_delivery.enabled
        and any(
            channel.enabled and (channel.provider == "log" or channel.url)
            for channel in settings.notifications.channels.values()
        )
    ):
        constructed["notification_delivery"] = NotificationDeliveryWorker(
            name="notification_delivery",
            settings=workers.notification_delivery,
            db=db,
            telemetry=telemetry,
            channels=settings.notifications.channels,
            wake_waiter=delivery_wake,
        )
    if workers.asset_profile_refresh.enabled and dex_profile_market is not None:
        constructed["asset_profile_refresh"] = AssetProfileRefreshWorker(
            name="asset_profile_refresh",
            settings=workers.asset_profile_refresh,
            db=db,
            telemetry=telemetry,
            dex_profile_market=dex_profile_market,
        )
    if workers.resolution_refresh.enabled and dex_discovery_market is not None:
        constructed["resolution_refresh"] = ResolutionRefreshWorker(
            name="resolution_refresh",
            settings=workers.resolution_refresh,
            db=db,
            telemetry=telemetry,
            dex_discovery_market=dex_discovery_market,
            dex_quote_market=dex_quote_market,
            chain_ids=workers.resolution_refresh.chain_ids,
            wake_bus=wake_bus,
        )
    if workers.live_price_gateway.enabled:
        constructed["live_price_gateway"] = LivePriceGateway(
            name="live_price_gateway",
            pool_bundle=db,
            telemetry=telemetry,
            providers=asset_market,
            interval_seconds=workers.live_price_gateway.interval_seconds,
            projection_version=TOKEN_RADAR_PROJECTION_VERSION,
            on_live_market_update=hub.publish,
        )
    if workers.enrichment.enabled and settings.llm_configured:
        constructed["enrichment"] = EnrichmentWorker(
            name="enrichment",
            settings=workers.enrichment,
            db=db,
            telemetry=telemetry,
            client=providers.social_enrichment.event_enrichment,
            publisher=hub,
            watchlist_summary_config=HandleSummaryTriggerConfig(
                signal_threshold=workers.handle_summary.signal_threshold,
                time_threshold_ms=workers.handle_summary.time_threshold_ms,
                min_interval_ms=workers.handle_summary.min_interval_ms,
                input_limit=workers.handle_summary.input_limit,
                window_days=workers.handle_summary.window_days,
                max_attempts=workers.handle_summary.max_attempts,
            )
            if workers.handle_summary.enabled
            else None,
        )

    result: dict[str, WorkerBase] = {}
    for name, worker in constructed.items():
        if isinstance(worker, WorkerBase):
            result[name] = worker
            continue
        raise TypeError(f"worker:{name}:expected WorkerBase, got {type(worker).__name__}")
    return result


def _notification_rule_engine(settings: Settings, repos: Any) -> NotificationRuleEngine:
    return NotificationRuleEngine(
        settings=settings,
        evidence=repos.evidence,
        account_alerts=AccountAlertService(repos.signals),
        asset_flow=AssetFlowService(
            token_radar=repos.token_radar,
            profiles=TokenProfileReadModel(asset_profiles=repos.asset_profiles),
        ),
        harness=HarnessService(repos.harness),
        pulse=repos.pulse,
    )


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


class _DisabledWorker(WorkerBase):
    async def run_once(self) -> WorkerResult:
        return WorkerResult(skipped=1, notes={"reason": "disabled"})


class _LocalWakeWaiter:
    def __init__(self) -> None:
        self._event = asyncio.Event()

    def wake(self) -> None:
        self._event.set()

    async def async_wait(self, timeout: float) -> bool:  # noqa: ASYNC109 - mirrors WakeWaiter.async_wait(timeout).
        try:
            await asyncio.wait_for(self._event.wait(), timeout=max(0.0, float(timeout)))
        except TimeoutError:
            return False
        self._event.clear()
        return True


def _worker_settings(settings: Settings, name: str, *, enabled: bool) -> Any:
    config_name = "handle_summary" if name == "handle_summary" else name
    config = getattr(settings.workers, config_name, None)
    if config is None:
        return SimpleNamespace(enabled=enabled)
    if getattr(config, "enabled", True) == enabled:
        return config
    values = _object_values(config)
    values["enabled"] = enabled
    return SimpleNamespace(**values)


def _object_values(value: Any) -> dict[str, Any]:
    dump = getattr(value, "model_dump", None)
    if dump is not None:
        return dict(dump())
    if hasattr(value, "__dict__"):
        return dict(vars(value))
    return {"enabled": bool(getattr(value, "enabled", True))}


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
