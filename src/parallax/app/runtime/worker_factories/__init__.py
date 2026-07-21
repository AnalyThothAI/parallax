from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from parallax.app.runtime.db_pool_bundle import DBPoolBundle
from parallax.app.runtime.providers_wiring import WiredProviders
from parallax.app.runtime.telemetry import TelemetryRegistry
from parallax.app.runtime.worker_base import WorkerBase
from parallax.app.runtime.worker_manifest import worker_names
from parallax.app.runtime.worker_result import WorkerResult
from parallax.app.surfaces.api.ws import PublicWebSocketHub
from parallax.platform.config.settings import Settings


@dataclass(frozen=True, slots=True)
class WorkerFactoryContext:
    settings: Settings
    db: DBPoolBundle
    telemetry: TelemetryRegistry
    providers: WiredProviders
    hub: PublicWebSocketHub
    collector: WorkerBase
    collector_enabled: bool
    collector_start_requested: bool
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
    collector_start_requested: bool = True,
) -> dict[str, WorkerBase]:
    ctx = WorkerFactoryContext(
        settings=settings,
        db=db,
        telemetry=telemetry,
        providers=providers,
        hub=hub,
        collector=collector,
        collector_enabled=collector_enabled,
        collector_start_requested=collector_start_requested,
        wake_bus=wake_bus,
    )
    specs = worker_factory_specs()
    _validate_factory_specs(specs)
    manifest_worker_names = worker_names()
    constructed: dict[str, WorkerBase] = {}
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
    for name in manifest_worker_names:
        if name not in constructed:
            constructed[name] = _missing_worker_sentinel(ctx, name)
    return constructed


class _SentinelWorker(WorkerBase):
    def __init__(
        self,
        *,
        name: str,
        settings: Any,
        db: Any,
        telemetry: Any,
        effective_status: str,
        unavailable_reason: str | None = None,
    ) -> None:
        super().__init__(name=name, settings=settings, db=db, telemetry=telemetry)
        self._effective_status = effective_status
        self._unavailable_reason = unavailable_reason

    async def run_once(self) -> WorkerResult:
        return WorkerResult(skipped=1, notes={"reason": self.effective_status})


class DisabledWorker(_SentinelWorker):
    def __init__(self, *, name: str, settings: Any, db: Any, telemetry: Any) -> None:
        super().__init__(
            name=name,
            settings=settings,
            db=db,
            telemetry=telemetry,
            effective_status="disabled",
        )


class IntentionallyNotStartedWorker(_SentinelWorker):
    def __init__(self, *, name: str, settings: Any, db: Any, telemetry: Any) -> None:
        super().__init__(
            name=name,
            settings=settings,
            db=db,
            telemetry=telemetry,
            effective_status="intentionally_not_started",
        )


class UnavailableWorker(_SentinelWorker):
    def __init__(self, *, name: str, settings: Any, db: Any, telemetry: Any, reason: str) -> None:
        super().__init__(
            name=name,
            settings=settings,
            db=db,
            telemetry=telemetry,
            effective_status="unavailable",
            unavailable_reason=_redacted_reason(reason),
        )


def _missing_worker_sentinel(ctx: WorkerFactoryContext, name: str) -> WorkerBase:
    if not _worker_config_enabled(ctx.settings, name):
        return disabled_worker(ctx, name)
    return unavailable_worker(ctx, name, "factory_not_constructed")


def disabled_worker(ctx: WorkerFactoryContext, name: str) -> WorkerBase:
    return DisabledWorker(
        name=name,
        settings=_worker_settings(ctx.settings, name, enabled=False),
        db=ctx.db,
        telemetry=ctx.telemetry,
    )


def intentionally_not_started_worker(ctx: WorkerFactoryContext, name: str) -> WorkerBase:
    return IntentionallyNotStartedWorker(
        name=name,
        settings=_worker_settings(ctx.settings, name, enabled=False),
        db=ctx.db,
        telemetry=ctx.telemetry,
    )


def unavailable_worker(ctx: WorkerFactoryContext, name: str, reason: str) -> WorkerBase:
    return UnavailableWorker(
        name=name,
        settings=_worker_settings(ctx.settings, name, enabled=True),
        db=ctx.db,
        telemetry=ctx.telemetry,
        reason=reason,
    )


def _worker_config_enabled(settings: Settings, name: str) -> bool:
    config = getattr(settings.workers, name)
    return bool(config.enabled)


def _redacted_reason(reason: str) -> str:
    value = str(reason or "").strip().lower()
    allowed = []
    for char in value:
        if char.isalnum() or char == "_":
            allowed.append(char)
        elif char in {"-", ".", " "}:
            allowed.append("_")
    redacted = "".join(allowed).strip("_")
    return redacted or "unavailable"


def _worker_settings(settings: Settings, name: str, *, enabled: bool) -> Any:
    config = getattr(settings.workers, name)
    if config.enabled == enabled:
        return config
    try:
        model_copy = config.model_copy
    except AttributeError as exc:
        raise RuntimeError(f"worker_settings_model_copy_required:{name}") from exc
    if not callable(model_copy):
        raise RuntimeError(f"worker_settings_model_copy_required:{name}")
    return model_copy(update={"enabled": enabled})


def worker_factory_specs() -> tuple[WorkerFactorySpec, ...]:
    from parallax.app.runtime.worker_factories.asset_market import (
        WORKER_KEYS as ASSET_MARKET_KEYS,
    )
    from parallax.app.runtime.worker_factories.asset_market import (
        construct_asset_market_workers,
    )
    from parallax.app.runtime.worker_factories.cex_market_intel import (
        WORKER_KEYS as CEX_MARKET_INTEL_KEYS,
    )
    from parallax.app.runtime.worker_factories.cex_market_intel import (
        construct_cex_market_intel_workers,
    )
    from parallax.app.runtime.worker_factories.ingestion import (
        WORKER_KEYS as INGESTION_KEYS,
    )
    from parallax.app.runtime.worker_factories.ingestion import (
        construct_ingestion_workers,
    )
    from parallax.app.runtime.worker_factories.macro_intel import (
        WORKER_KEYS as MACRO_INTEL_KEYS,
    )
    from parallax.app.runtime.worker_factories.macro_intel import (
        construct_macro_intel_workers,
    )
    from parallax.app.runtime.worker_factories.narrative_intel import (
        WORKER_KEYS as NARRATIVE_INTEL_KEYS,
    )
    from parallax.app.runtime.worker_factories.narrative_intel import (
        construct_narrative_intel_workers,
    )
    from parallax.app.runtime.worker_factories.news_intel import (
        WORKER_KEYS as NEWS_INTEL_KEYS,
    )
    from parallax.app.runtime.worker_factories.news_intel import (
        construct_news_intel_workers,
    )
    from parallax.app.runtime.worker_factories.notifications import (
        WORKER_KEYS as NOTIFICATION_KEYS,
    )
    from parallax.app.runtime.worker_factories.notifications import (
        construct_notification_workers,
    )
    from parallax.app.runtime.worker_factories.token_intel import (
        WORKER_KEYS as TOKEN_INTEL_KEYS,
    )
    from parallax.app.runtime.worker_factories.token_intel import (
        construct_token_intel_workers,
    )

    return (
        WorkerFactorySpec("ingestion.py", INGESTION_KEYS, construct_ingestion_workers),
        WorkerFactorySpec("token_intel.py", TOKEN_INTEL_KEYS, construct_token_intel_workers),
        WorkerFactorySpec("asset_market.py", ASSET_MARKET_KEYS, construct_asset_market_workers),
        WorkerFactorySpec("cex_market_intel.py", CEX_MARKET_INTEL_KEYS, construct_cex_market_intel_workers),
        WorkerFactorySpec("macro_intel.py", MACRO_INTEL_KEYS, construct_macro_intel_workers),
        WorkerFactorySpec("narrative_intel.py", NARRATIVE_INTEL_KEYS, construct_narrative_intel_workers),
        WorkerFactorySpec("news_intel.py", NEWS_INTEL_KEYS, construct_news_intel_workers),
        WorkerFactorySpec("notifications.py", NOTIFICATION_KEYS, construct_notification_workers),
    )


def _validate_factory_specs(specs: tuple[WorkerFactorySpec, ...]) -> None:
    canonical = frozenset(worker_names())
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


__all__ = [
    "DisabledWorker",
    "IntentionallyNotStartedWorker",
    "UnavailableWorker",
    "WorkerFactoryContext",
    "WorkerFactorySpec",
    "construct_workers",
    "disabled_worker",
    "intentionally_not_started_worker",
    "unavailable_worker",
    "worker_factory_specs",
]
