from __future__ import annotations

import asyncio
import time
from typing import Any

from loguru import logger

from ..settings import NotificationChannelConfig


class AppriseNotificationAdapter:
    def notify(self, *, url: str, title: str, body: str, body_format: str = "text") -> None:
        import apprise

        app = apprise.Apprise()
        if not app.add(url):
            raise RuntimeError("invalid_apprise_url")
        if not app.notify(title=title, body=body, body_format=body_format):
            raise RuntimeError("apprise_notify_failed")


class NotificationDeliveryWorker:
    def __init__(
        self,
        *,
        repository,
        channels: dict[str, NotificationChannelConfig],
        adapter: Any | None = None,
        poll_interval: float = 5.0,
    ):
        self.repository = repository
        self.channels = channels
        self.adapter = adapter or AppriseNotificationAdapter()
        self.poll_interval = max(0.5, float(poll_interval))
        self._stopped = asyncio.Event()

    async def run(self) -> None:
        while not self._stopped.is_set():
            try:
                processed = await self.process_one()
            except Exception as exc:
                logger.exception(f"notification delivery worker loop failed: {exc}")
                processed = False
            if not processed:
                await asyncio.sleep(self.poll_interval)

    def stop(self) -> None:
        self._stopped.set()

    async def process_one(self, *, now_ms: int | None = None) -> bool:
        now = int(now_ms if now_ms is not None else _now_ms())
        delivery = self.repository.claim_next_delivery(now_ms=now)
        if delivery is None:
            return False
        notification = self.repository.notification_by_id(str(delivery["notification_id"]), subscriber_key=None)
        if notification is None:
            self.repository.fail_delivery(delivery, error="notification_not_found", now_ms=now)
            return True
        channel_id = str(delivery["channel_id"])
        channel = self.channels.get(channel_id)
        if channel is None or not channel.enabled:
            self.repository.fail_delivery(delivery, error="channel_not_configured", now_ms=now)
            return True
        if channel.provider != str(delivery["provider"]):
            self.repository.fail_delivery(delivery, error="channel_provider_mismatch", now_ms=now)
            return True
        if channel.provider == "log":
            logger.info(
                "notification delivery log "
                f"channel={channel_id} notification_id={notification['notification_id']} "
                f"title={notification['title']}"
            )
            self.repository.complete_delivery(delivery, delivered_at_ms=now)
            return True
        if not channel.url:
            self.repository.fail_delivery(delivery, error="channel_url_missing", now_ms=now)
            return True
        try:
            await asyncio.to_thread(
                self.adapter.notify,
                url=channel.url,
                title=str(notification["title"]),
                body=str(notification["body"]),
                body_format="text",
            )
        except Exception as exc:
            self.repository.fail_delivery(delivery, error=str(exc), now_ms=now)
            return True
        self.repository.complete_delivery(delivery, delivered_at_ms=now)
        return True


def _now_ms() -> int:
    return int(time.time() * 1000)
