from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from parallax.app.runtime.db_pool_bundle import DBPoolBundle
from parallax.app.runtime.provider_wiring.types import (
    AssetMarketProviders,
    NewsIntelProviders,
    WiredProviders,
)
from parallax.app.runtime.telemetry import TelemetryRegistry
from parallax.app.runtime.worker_manifest import worker_names
from parallax.domains.ingestion.providers import EventPublisherProtocol
from parallax.platform.config.settings import Settings
from parallax.platform.runtime.worker_base import WorkerBase
from parallax.platform.runtime.worker_result import WorkerResult


@dataclass(frozen=True, slots=True)
class WorkerFactoryContext:
    settings: Settings
    db: DBPoolBundle
    telemetry: TelemetryRegistry
    asset_market: AssetMarketProviders | None
    news_intel: NewsIntelProviders | None
    hub: EventPublisherProtocol | None
    collector: WorkerBase | None
    collector_enabled: bool
    collector_start_requested: bool


WorkerFactory = Callable[[WorkerFactoryContext], Mapping[str, WorkerBase]]


def construct_workers(
    *,
    settings: Settings,
    db: DBPoolBundle,
    telemetry: TelemetryRegistry,
    providers: WiredProviders,
    hub: EventPublisherProtocol,
    collector: WorkerBase,
    collector_enabled: bool,
    collector_start_requested: bool = True,
) -> dict[str, WorkerBase]:
    ctx = WorkerFactoryContext(
        settings=settings,
        db=db,
        telemetry=telemetry,
        asset_market=providers.asset_market,
        news_intel=providers.news_intel,
        hub=hub,
        collector=collector,
        collector_enabled=collector_enabled,
        collector_start_requested=collector_start_requested,
    )
    constructed: dict[str, WorkerBase] = {}
    for factory in worker_factories():
        for name, worker in factory(ctx).items():
            if name in constructed:
                raise ValueError(f"worker_composition_duplicate:{name}")
            if not isinstance(worker, WorkerBase):
                raise TypeError(f"worker_composition_invalid:{name}:{type(worker).__name__}")
            constructed[name] = worker

    canonical_names = worker_names()
    canonical = frozenset(canonical_names)
    actual = frozenset(constructed)
    if actual != canonical:
        missing = sorted(canonical - actual)
        unknown = sorted(actual - canonical)
        raise RuntimeError(f"worker_composition_mismatch:missing={missing}:unknown={unknown}")
    return {name: constructed[name] for name in canonical_names}


def construct_worker(
    *,
    worker_name: str,
    settings: Settings,
    db: DBPoolBundle,
    telemetry: TelemetryRegistry,
    asset_market: AssetMarketProviders | None,
    news_intel: NewsIntelProviders | None,
    hub: EventPublisherProtocol | None,
    collector: WorkerBase | None,
    collector_enabled: bool,
    collector_start_requested: bool = False,
) -> WorkerBase:
    """Construct one worker from the same domain factories used by bootstrap."""
    ctx = WorkerFactoryContext(
        settings=settings,
        db=db,
        telemetry=telemetry,
        asset_market=asset_market,
        news_intel=news_intel,
        hub=hub,
        collector=collector,
        collector_enabled=collector_enabled,
        collector_start_requested=collector_start_requested,
    )
    candidates = [worker for factory in worker_factories() if (worker := factory(ctx).get(worker_name)) is not None]
    if len(candidates) != 1:
        raise RuntimeError(f"worker_composition_expected_one:{worker_name}:{len(candidates)}")
    return candidates[0]


class InactiveWorker(WorkerBase):
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
        self._inactive_status = str(effective_status)
        self._inactive_reason = str(unavailable_reason) if unavailable_reason else None

    @property
    def effective_status(self) -> str:
        return self._inactive_status

    @property
    def unavailable_reason(self) -> str | None:
        return self._inactive_reason

    async def run_once(self) -> WorkerResult:
        return WorkerResult(skipped=1, notes={"reason": self.effective_status})


def disabled_worker(ctx: WorkerFactoryContext, name: str) -> WorkerBase:
    return InactiveWorker(
        name=name,
        settings=_worker_settings(ctx.settings, name, enabled=False),
        db=ctx.db,
        telemetry=ctx.telemetry,
        effective_status="disabled",
    )


def intentionally_not_started_worker(ctx: WorkerFactoryContext, name: str) -> WorkerBase:
    return InactiveWorker(
        name=name,
        settings=_worker_settings(ctx.settings, name, enabled=False),
        db=ctx.db,
        telemetry=ctx.telemetry,
        effective_status="intentionally_not_started",
    )


def unavailable_worker(ctx: WorkerFactoryContext, name: str, reason: str) -> WorkerBase:
    return InactiveWorker(
        name=name,
        settings=_worker_settings(ctx.settings, name, enabled=True),
        db=ctx.db,
        telemetry=ctx.telemetry,
        effective_status="unavailable",
        unavailable_reason=_redacted_reason(reason),
    )


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


def worker_factories() -> tuple[WorkerFactory, ...]:
    from parallax.app.runtime.worker_factories.asset_market import (
        construct_asset_market_workers,
    )
    from parallax.app.runtime.worker_factories.ingestion import (
        construct_ingestion_workers,
    )
    from parallax.app.runtime.worker_factories.macro_intel import (
        construct_macro_intel_workers,
    )
    from parallax.app.runtime.worker_factories.news_intel import (
        construct_news_intel_workers,
    )
    from parallax.app.runtime.worker_factories.notifications import (
        construct_notification_workers,
    )
    from parallax.app.runtime.worker_factories.token_intel import (
        construct_token_intel_workers,
    )

    return (
        construct_ingestion_workers,
        construct_token_intel_workers,
        construct_asset_market_workers,
        construct_macro_intel_workers,
        construct_news_intel_workers,
        construct_notification_workers,
    )


__all__ = [
    "InactiveWorker",
    "WorkerFactoryContext",
    "construct_worker",
    "construct_workers",
    "disabled_worker",
    "intentionally_not_started_worker",
    "unavailable_worker",
    "worker_factories",
]
