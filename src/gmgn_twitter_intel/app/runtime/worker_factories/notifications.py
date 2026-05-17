from __future__ import annotations

import asyncio
from typing import Any

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_factories import WorkerFactoryContext
from gmgn_twitter_intel.domains.account_quality.read_models.account_alert_service import AccountAlertService
from gmgn_twitter_intel.domains.asset_market.read_models.token_profile_read_model import TokenProfileReadModel
from gmgn_twitter_intel.domains.closed_loop_harness.interfaces import HarnessService
from gmgn_twitter_intel.domains.notifications.runtime.notification_delivery import NotificationDeliveryWorker
from gmgn_twitter_intel.domains.notifications.runtime.notification_worker import NotificationWorker
from gmgn_twitter_intel.domains.notifications.services.notification_rules import NotificationRuleEngine
from gmgn_twitter_intel.domains.token_intel.read_models.asset_flow_service import AssetFlowService
from gmgn_twitter_intel.platform.config.settings import Settings

WORKER_KEYS = frozenset({"notification_delivery", "notification_rule"})


def construct_notification_workers(ctx: WorkerFactoryContext) -> dict[str, WorkerBase]:
    workers = ctx.settings.workers
    constructed: dict[str, WorkerBase] = {}
    delivery_wake = _LocalWakeWaiter()

    if ctx.settings.notifications.enabled and workers.notification_rule.enabled:
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
    if (
        ctx.settings.notifications.enabled
        and workers.notification_delivery.enabled
        and any(
            channel.enabled and (channel.provider == "log" or channel.url)
            for channel in ctx.settings.notifications.channels.values()
        )
    ):
        constructed["notification_delivery"] = NotificationDeliveryWorker(
            name="notification_delivery",
            settings=workers.notification_delivery,
            db=ctx.db,
            telemetry=ctx.telemetry,
            channels=ctx.settings.notifications.channels,
            wake_waiter=delivery_wake,
        )

    return constructed


def _notification_rule_engine(settings: Settings, repos: Any) -> NotificationRuleEngine:
    return NotificationRuleEngine(
        settings=settings,
        evidence=repos.evidence,
        account_alerts=AccountAlertService(repos.signals),
        asset_flow=AssetFlowService(
            token_radar=repos.token_radar,
            profiles=TokenProfileReadModel(token_profiles=repos.token_profiles),
        ),
        harness=HarnessService(repos.harness),
        pulse=repos.pulse_read,
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
