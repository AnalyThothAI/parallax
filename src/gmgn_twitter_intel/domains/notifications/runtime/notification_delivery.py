from __future__ import annotations

import asyncio
import time
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import urlparse

import httpx
from loguru import logger

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.platform.config.settings import NotificationChannelConfig

if TYPE_CHECKING:
    from gmgn_twitter_intel.app.runtime.repository_session import RepositorySession


class AppriseNotificationAdapter:
    def notify(self, *, url: str, title: str, body: str, body_format: str = "text") -> None:
        import apprise

        app = apprise.Apprise()
        if not app.add(url):
            raise RuntimeError("invalid_apprise_url")
        if not app.notify(title=title, body=body, body_format=body_format):
            raise RuntimeError("apprise_notify_failed")


class PushDeerNotificationAdapter:
    def notify_markdown(self, *, url: str, title: str, body: str) -> None:
        push_key, endpoint = _parse_pushdeer_url(url)
        response = httpx.post(
            f"{endpoint}/message/push",
            data={"pushkey": push_key, "text": title, "desp": body, "type": "markdown"},
            timeout=10.0,
        )
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        code = payload.get("code")
        if code not in (None, 0, 200):
            raise RuntimeError(f"pushdeer_notify_failed:{code}")


@dataclass(frozen=True, slots=True)
class DeliveryClaim:
    delivery: dict[str, Any]
    notification: dict[str, Any]
    channel: NotificationChannelConfig


@dataclass(frozen=True, slots=True)
class DeliveryOutcome:
    processed: bool
    failed: bool = False
    dead: bool = False
    reason: str | None = None


class NotificationDeliveryWorker(WorkerBase):
    def __init__(
        self,
        *,
        name: str,
        settings: Any,
        db: Any,
        telemetry: Any,
        channels: dict[str, NotificationChannelConfig],
        adapter: Any | None = None,
        pushdeer_adapter: Any | None = None,
        wake_waiter: Any | None = None,
    ):
        super().__init__(name=name, settings=settings, db=db, telemetry=telemetry, wake_waiter=wake_waiter)
        self.channels = channels
        self.adapter = adapter or AppriseNotificationAdapter()
        self.pushdeer_adapter = pushdeer_adapter or PushDeerNotificationAdapter()
        self.batch_limit = max(1, int(getattr(settings, "batch_size", 1) or 1))

    async def run_once(self, *, now_ms: int | None = None) -> WorkerResult:
        processed = 0
        failed = 0
        dead = 0
        reasons: list[str] = []
        for _ in range(self.batch_limit):
            outcome = await self._process_one(now_ms=now_ms)
            if not outcome.processed:
                if outcome.reason:
                    reasons.append(outcome.reason)
                break
            processed += 1
            if outcome.failed:
                failed += 1
            if outcome.dead:
                dead += 1
            if outcome.reason:
                reasons.append(outcome.reason)
        return WorkerResult(
            processed=processed,
            failed=failed,
            dead=dead,
            skipped=0 if processed else 1,
            notes={"reasons": reasons},
        )

    async def process_one(self, *, now_ms: int | None = None) -> bool:
        outcome = await self._process_one(now_ms=now_ms)
        return outcome.processed

    async def _process_one(self, *, now_ms: int | None = None) -> DeliveryOutcome:
        now = int(now_ms if now_ms is not None else _now_ms())
        claim = await asyncio.to_thread(self._claim_delivery_sync, now_ms=now)
        if isinstance(claim, DeliveryOutcome):
            return claim

        try:
            if claim.channel.provider == "pushdeer":
                await asyncio.to_thread(
                    lambda: self.pushdeer_adapter.notify_markdown(
                        url=cast(str, claim.channel.url),
                        title=str(claim.notification["title"]),
                        body=str(claim.notification["body"]),
                    )
                )
            else:
                await asyncio.to_thread(
                    lambda: self.adapter.notify(
                        url=cast(str, claim.channel.url),
                        title=str(claim.notification["title"]),
                        body=str(claim.notification["body"]),
                        body_format="text",
                    )
                )
        except Exception as exc:
            return await asyncio.to_thread(self._fail_delivery_sync, claim.delivery, error=str(exc), now_ms=now)
        return await asyncio.to_thread(self._complete_delivery_sync, claim.delivery, now_ms=now)

    def _claim_delivery_sync(self, *, now_ms: int) -> DeliveryClaim | DeliveryOutcome:
        with self._repository_session() as repos:
            delivery = repos.notifications.claim_next_delivery(now_ms=now_ms)
            if delivery is None:
                repos.notifications.conn.commit()
                return DeliveryOutcome(processed=False, reason="no_delivery")
            notification = repos.notifications.notification_by_id(
                str(delivery["notification_id"]),
                subscriber_key=None,
            )
            if notification is None:
                repos.notifications.fail_delivery(delivery, error="notification_not_found", now_ms=now_ms)
                return _failure_outcome(delivery, reason="notification_not_found")
            channel_id = str(delivery["channel_id"])
            channel = self.channels.get(channel_id)
            if channel is None or not channel.enabled:
                repos.notifications.fail_delivery(delivery, error="channel_not_configured", now_ms=now_ms)
                return _failure_outcome(delivery, reason="channel_not_configured")
            if channel.provider != str(delivery["provider"]):
                repos.notifications.fail_delivery(delivery, error="channel_provider_mismatch", now_ms=now_ms)
                return _failure_outcome(delivery, reason="channel_provider_mismatch")
            if channel.provider == "log":
                logger.info(
                    "notification delivery log "
                    f"channel={channel_id} notification_id={notification['notification_id']} "
                    f"title={notification['title']}"
                )
                repos.notifications.complete_delivery(delivery, delivered_at_ms=now_ms)
                return DeliveryOutcome(processed=True, reason="log")
            if not channel.url:
                repos.notifications.fail_delivery(delivery, error="channel_url_missing", now_ms=now_ms)
                return _failure_outcome(delivery, reason="channel_url_missing")
            repos.notifications.conn.commit()
            return DeliveryClaim(delivery=delivery, notification=notification, channel=channel)

    def _complete_delivery_sync(self, delivery: dict[str, Any], *, now_ms: int) -> DeliveryOutcome:
        with self._repository_session() as repos:
            repos.notifications.complete_delivery(delivery, delivered_at_ms=now_ms)
        return DeliveryOutcome(processed=True, reason="delivered")

    def _fail_delivery_sync(self, delivery: dict[str, Any], *, error: str, now_ms: int) -> DeliveryOutcome:
        with self._repository_session() as repos:
            repos.notifications.fail_delivery(delivery, error=error, now_ms=now_ms)
        return _failure_outcome(delivery, reason=error)

    def _repository_session(self) -> AbstractContextManager[RepositorySession]:
        return cast(
            "AbstractContextManager[RepositorySession]",
            self.db.worker_session(
                self.name,
                statement_timeout_seconds=getattr(self.settings, "statement_timeout_seconds", None),
            ),
        )


def _parse_pushdeer_url(url: str) -> tuple[str, str]:
    raw = str(url).strip()
    parsed = urlparse(raw)
    if parsed.scheme in {"pushdeer", "pushdeers"}:
        secure = parsed.scheme == "pushdeers"
        if parsed.path and parsed.path.strip("/"):
            push_key = parsed.path.strip("/")
            host = parsed.netloc or "api2.pushdeer.com"
            endpoint = f"{'https' if secure else 'http'}://{host}"
        else:
            push_key = parsed.netloc
            endpoint = "https://api2.pushdeer.com" if secure else "http://api2.pushdeer.com"
    elif parsed.scheme in {"http", "https"}:
        push_key = parsed.path.strip("/")
        endpoint = f"{parsed.scheme}://{parsed.netloc}"
    else:
        push_key = raw
        endpoint = "https://api2.pushdeer.com"
    if not push_key:
        raise RuntimeError("invalid_pushdeer_url")
    return push_key, endpoint.rstrip("/")


def _failure_outcome(delivery: dict[str, Any], *, reason: str) -> DeliveryOutcome:
    attempts = int(delivery.get("attempt_count") or 0)
    max_attempts = int(delivery.get("max_attempts") or 1)
    is_dead = attempts >= max_attempts
    return DeliveryOutcome(processed=True, failed=not is_dead, dead=is_dead, reason=reason)


def _now_ms() -> int:
    return int(time.time() * 1000)
