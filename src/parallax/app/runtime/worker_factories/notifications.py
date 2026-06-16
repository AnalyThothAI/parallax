from __future__ import annotations

import asyncio
from typing import Any

from parallax.app.runtime.worker_base import WorkerBase
from parallax.app.runtime.worker_factories import WorkerFactoryContext, disabled_worker
from parallax.app.runtime.worker_manifest import manifest_names_for_factory
from parallax.domains.account_quality.read_models.account_alert_service import AccountAlertService
from parallax.domains.notifications.runtime.notification_delivery import NotificationDeliveryWorker
from parallax.domains.notifications.runtime.notification_worker import NotificationWorker
from parallax.domains.notifications.services.notification_rules import NotificationRuleEngine
from parallax.platform.config.settings import Settings

WORKER_KEYS = manifest_names_for_factory("notifications.py")


def construct_notification_workers(ctx: WorkerFactoryContext) -> dict[str, WorkerBase]:
    workers = ctx.settings.workers
    constructed: dict[str, WorkerBase] = {}
    delivery_wake = _LocalWakeWaiter()
    notifications_enabled = bool(ctx.settings.notifications.enabled)
    delivery_channels_enabled = any(
        channel.enabled and (channel.provider == "log" or channel.url)
        for channel in ctx.settings.notifications.channels.values()
    )

    if not notifications_enabled:
        return {
            name: disabled_worker(ctx, name)
            for name in ("notification_rule", "notification_delivery")
            if getattr(workers, name).enabled
        }

    if workers.notification_rule.enabled:
        constructed["notification_rule"] = NotificationWorker(
            name="notification_rule",
            settings=workers.notification_rule,
            db=ctx.db,
            telemetry=ctx.telemetry,
            rule_engine_factory=lambda repos: _notification_rule_engine(ctx.settings, repos),
            publisher=ctx.hub,
            delivery_channels=ctx.settings.notifications.channels,
            delivery_max_attempts=workers.notification_delivery.max_attempts,
            delivery_wake=delivery_wake,
        )
    if workers.notification_delivery.enabled and delivery_channels_enabled:
        constructed["notification_delivery"] = NotificationDeliveryWorker(
            name="notification_delivery",
            settings=workers.notification_delivery,
            db=ctx.db,
            telemetry=ctx.telemetry,
            channels=ctx.settings.notifications.channels,
            wake_waiter=delivery_wake,
        )
    elif workers.notification_delivery.enabled:
        constructed["notification_delivery"] = disabled_worker(ctx, "notification_delivery")

    return constructed


def _notification_rule_engine(settings: Settings, repos: Any) -> NotificationRuleEngine:
    return NotificationRuleEngine(
        settings=settings,
        evidence=repos.evidence,
        account_alerts=AccountAlertService(repos.signals),
        pulse=repos.pulse_read,
        news=repos.news,
    )


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

    def close(self) -> None:
        self._event.set()
