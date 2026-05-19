from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from gmgn_twitter_intel.app.runtime.db_pool_bundle import DBPoolBundle
from gmgn_twitter_intel.app.runtime.providers_wiring import WiredProviders
from gmgn_twitter_intel.app.runtime.telemetry import TelemetryRegistry
from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_registry import CANONICAL_WORKER_NAMES
from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.app.surfaces.api.ws import PublicWebSocketHub
from gmgn_twitter_intel.platform.config.settings import Settings


@dataclass(frozen=True, slots=True)
class WorkerFactoryContext:
    settings: Settings
    db: DBPoolBundle
    telemetry: TelemetryRegistry
    providers: WiredProviders
    hub: PublicWebSocketHub
    collector: WorkerBase
    collector_enabled: bool
    wake_bus: Any


WorkerFactory = Callable[[WorkerFactoryContext], Mapping[str, WorkerBase]]


@dataclass(frozen=True, slots=True)
class WorkerFactorySpec:
    name: str
    keys: frozenset[str]
    factory: WorkerFactory


def construct_workers(
    *,
    settings: Settings,
    db: DBPoolBundle,
    telemetry: TelemetryRegistry,
    providers: WiredProviders,
    hub: PublicWebSocketHub,
    collector: WorkerBase,
    collector_enabled: bool,
    wake_bus: Any,
) -> dict[str, WorkerBase]:
    ctx = WorkerFactoryContext(
        settings=settings,
        db=db,
        telemetry=telemetry,
        providers=providers,
        hub=hub,
        collector=collector,
        collector_enabled=collector_enabled,
        wake_bus=wake_bus,
    )
    specs = worker_factory_specs()
    _validate_factory_specs(specs)
    constructed: dict[str, WorkerBase] = {
        name: _DisabledWorker(
            name=name,
            settings=_worker_settings(settings, name, enabled=False),
            db=db,
            telemetry=telemetry,
        )
        for name in CANONICAL_WORKER_NAMES
    }
    populated: set[str] = set()
    for spec in specs:
        workers = spec.factory(ctx)
        unowned = set(workers) - spec.keys
        if unowned:
            raise KeyError(f"worker_factory:{spec.name}:returned unowned workers:{sorted(unowned)}")
        for name, worker in workers.items():
            if name in populated:
                raise ValueError(f"worker:{name}:constructed by multiple factories")
            if not isinstance(worker, WorkerBase):
                raise TypeError(f"worker:{name}:expected WorkerBase, got {type(worker).__name__}")
            constructed[name] = worker
            populated.add(name)
    return constructed


class _DisabledWorker(WorkerBase):
    async def run_once(self) -> WorkerResult:
        return WorkerResult(skipped=1, notes={"reason": "disabled"})


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


def worker_factory_specs() -> tuple[WorkerFactorySpec, ...]:
    from gmgn_twitter_intel.app.runtime.worker_factories.asset_market import (
        WORKER_KEYS as ASSET_MARKET_KEYS,
    )
    from gmgn_twitter_intel.app.runtime.worker_factories.asset_market import (
        construct_asset_market_workers,
    )
    from gmgn_twitter_intel.app.runtime.worker_factories.enrichment import (
        WORKER_KEYS as ENRICHMENT_KEYS,
    )
    from gmgn_twitter_intel.app.runtime.worker_factories.enrichment import (
        construct_enrichment_workers,
    )
    from gmgn_twitter_intel.app.runtime.worker_factories.ingestion import (
        WORKER_KEYS as INGESTION_KEYS,
    )
    from gmgn_twitter_intel.app.runtime.worker_factories.ingestion import (
        construct_ingestion_workers,
    )
    from gmgn_twitter_intel.app.runtime.worker_factories.narrative_intel import (
        WORKER_KEYS as NARRATIVE_INTEL_KEYS,
    )
    from gmgn_twitter_intel.app.runtime.worker_factories.narrative_intel import (
        construct_narrative_intel_workers,
    )
    from gmgn_twitter_intel.app.runtime.worker_factories.news_intel import (
        WORKER_KEYS as NEWS_INTEL_KEYS,
    )
    from gmgn_twitter_intel.app.runtime.worker_factories.news_intel import (
        construct_news_intel_workers,
    )
    from gmgn_twitter_intel.app.runtime.worker_factories.notifications import (
        WORKER_KEYS as NOTIFICATION_KEYS,
    )
    from gmgn_twitter_intel.app.runtime.worker_factories.notifications import (
        construct_notification_workers,
    )
    from gmgn_twitter_intel.app.runtime.worker_factories.pulse import (
        WORKER_KEYS as PULSE_KEYS,
    )
    from gmgn_twitter_intel.app.runtime.worker_factories.pulse import (
        construct_pulse_workers,
    )
    from gmgn_twitter_intel.app.runtime.worker_factories.token_intel import (
        WORKER_KEYS as TOKEN_INTEL_KEYS,
    )
    from gmgn_twitter_intel.app.runtime.worker_factories.token_intel import (
        construct_token_intel_workers,
    )
    from gmgn_twitter_intel.app.runtime.worker_factories.watchlist import (
        WORKER_KEYS as WATCHLIST_KEYS,
    )
    from gmgn_twitter_intel.app.runtime.worker_factories.watchlist import (
        construct_watchlist_workers,
    )

    return (
        WorkerFactorySpec("ingestion.py", INGESTION_KEYS, construct_ingestion_workers),
        WorkerFactorySpec("token_intel.py", TOKEN_INTEL_KEYS, construct_token_intel_workers),
        WorkerFactorySpec("asset_market.py", ASSET_MARKET_KEYS, construct_asset_market_workers),
        WorkerFactorySpec("narrative_intel.py", NARRATIVE_INTEL_KEYS, construct_narrative_intel_workers),
        WorkerFactorySpec("news_intel.py", NEWS_INTEL_KEYS, construct_news_intel_workers),
        WorkerFactorySpec("pulse.py", PULSE_KEYS, construct_pulse_workers),
        WorkerFactorySpec("watchlist.py", WATCHLIST_KEYS, construct_watchlist_workers),
        WorkerFactorySpec("notifications.py", NOTIFICATION_KEYS, construct_notification_workers),
        WorkerFactorySpec("enrichment.py", ENRICHMENT_KEYS, construct_enrichment_workers),
    )


def _validate_factory_specs(specs: tuple[WorkerFactorySpec, ...]) -> None:
    canonical = frozenset(CANONICAL_WORKER_NAMES)
    owner_by_key: dict[str, str] = {}
    for spec in specs:
        unknown = spec.keys - canonical
        if unknown:
            raise KeyError(f"worker_factory:{spec.name}:unknown owned workers:{sorted(unknown)}")
        for key in spec.keys:
            previous_owner = owner_by_key.get(key)
            if previous_owner is not None:
                raise ValueError(f"worker:{key}:owned by both {previous_owner} and {spec.name}")
            owner_by_key[key] = spec.name

    owned = frozenset(owner_by_key)
    if owned != canonical:
        missing = sorted(canonical - owned)
        extra = sorted(owned - canonical)
        raise ValueError(f"worker_factory_ownership_mismatch:missing={missing}:extra={extra}")


__all__ = ["WorkerFactoryContext", "WorkerFactorySpec", "construct_workers", "worker_factory_specs"]
