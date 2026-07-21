from __future__ import annotations

from typing import Any

from parallax.app.runtime.worker_factories import WorkerFactoryContext, disabled_worker, unavailable_worker
from parallax.domains.notifications.runtime.notification_delivery import NotificationDeliveryWorker
from parallax.domains.notifications.runtime.notification_worker import NotificationWorker
from parallax.domains.notifications.services.account_alert_service import AccountAlertService
from parallax.domains.notifications.services.notification_rules import NotificationRuleEngine
from parallax.platform.config.settings import Settings
from parallax.platform.runtime.worker_base import WorkerBase


def construct_notification_workers(ctx: WorkerFactoryContext) -> dict[str, WorkerBase]:
    workers = ctx.settings.workers
    constructed: dict[str, WorkerBase] = {}
    notifications_enabled = bool(ctx.settings.notifications.enabled)
    delivery_channels_enabled = any(
        channel.enabled and (channel.provider == "log" or channel.url)
        for channel in ctx.settings.notifications.channels.values()
    )

    if not notifications_enabled:
        return {
            "notification_rule": disabled_worker(ctx, "notification_rule"),
            "notification_delivery": disabled_worker(ctx, "notification_delivery"),
        }

    if not workers.notification_rule.enabled:
        constructed["notification_rule"] = disabled_worker(ctx, "notification_rule")
    elif ctx.hub is None:
        constructed["notification_rule"] = unavailable_worker(
            ctx,
            "notification_rule",
            "missing_notification_publisher",
        )
    else:
        constructed["notification_rule"] = NotificationWorker(
            name="notification_rule",
            settings=workers.notification_rule,
            db=ctx.db,
            telemetry=ctx.telemetry,
            rule_engine_factory=lambda repos: _notification_rule_engine(ctx.settings, repos),
            publisher=ctx.hub,
            delivery_channels=ctx.settings.notifications.channels,
            delivery_max_attempts=workers.notification_delivery.max_attempts,
            retention_days=ctx.settings.notifications.retention_days,
        )

    if not workers.notification_delivery.enabled:
        constructed["notification_delivery"] = disabled_worker(ctx, "notification_delivery")
    elif not delivery_channels_enabled:
        constructed["notification_delivery"] = unavailable_worker(
            ctx,
            "notification_delivery",
            "missing_notification_delivery_channel",
        )
    else:
        constructed["notification_delivery"] = NotificationDeliveryWorker(
            name="notification_delivery",
            settings=workers.notification_delivery,
            db=ctx.db,
            telemetry=ctx.telemetry,
            channels=ctx.settings.notifications.channels,
        )

    return constructed


def _notification_rule_engine(settings: Settings, repos: Any) -> NotificationRuleEngine:
    return NotificationRuleEngine(
        settings=settings,
        evidence=repos.evidence,
        account_alerts=AccountAlertService(repos.signals),
        news=repos.news_pages,
    )
