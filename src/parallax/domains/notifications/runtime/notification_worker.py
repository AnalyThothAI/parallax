from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from parallax.app.runtime.worker_base import WorkerBase
from parallax.app.runtime.worker_result import WorkerResult
from parallax.domains.notifications.types import NotificationCandidate

if TYPE_CHECKING:
    from parallax.app.runtime.repository_session import RepositorySession
    from parallax.domains.notifications.repositories.notification_repository import (
        NotificationRepository,
    )
    from parallax.platform.config.settings import NotificationChannelConfig

SEVERITY_RANK = {"info": 0, "warning": 1, "high": 2, "critical": 3}


@dataclass(frozen=True, slots=True)
class NotificationProcessResult:
    created: list[dict[str, Any]]
    external_deliveries_enqueued: bool


class NotificationWorker(WorkerBase):
    def __init__(
        self,
        *,
        name: str,
        settings: Any,
        db: Any,
        telemetry: Any,
        rule_engine: Any = None,
        publisher: Any = None,
        delivery_channels: dict[str, NotificationChannelConfig] | None = None,
        rule_engine_factory: Callable[[Any], Any] | None = None,
        delivery_max_attempts: int = 5,
        delivery_wake: Any | None = None,
    ) -> None:
        super().__init__(name=name, settings=settings, db=db, telemetry=telemetry)
        self.rule_engine_factory = rule_engine_factory
        self.rule_engine = rule_engine
        self.publisher = publisher
        self.delivery_channels = delivery_channels or {}
        self.delivery_max_attempts = max(1, int(delivery_max_attempts))
        self.delivery_wake = delivery_wake
        self.batch_limit = max(1, int(getattr(settings, "batch_size", 50) or 50))

    async def run_once(self, *, now_ms: int | None = None) -> WorkerResult:
        result = await self._process_once(now_ms=now_ms)
        created_count = len(result.created)
        return WorkerResult(
            processed=created_count,
            skipped=0 if created_count else 1,
            notes={
                "created": created_count,
                "external_deliveries_enqueued": result.external_deliveries_enqueued,
            },
        )

    async def process_once(self, *, now_ms: int | None = None) -> list[dict[str, Any]]:
        result = await self._process_once(now_ms=now_ms)
        return result.created

    async def _process_once(self, *, now_ms: int | None = None) -> NotificationProcessResult:
        now = int(now_ms if now_ms is not None else _now_ms())
        result = await asyncio.to_thread(self._process_once_sync, now_ms=now)
        if self.publisher is not None:
            for row in result.created:
                await self.publisher.publish({"type": "notification", "notification": row})
        if result.external_deliveries_enqueued and self.delivery_wake is not None:
            wake = getattr(self.delivery_wake, "wake", None)
            if wake is not None:
                wake()
        return result

    def _process_once_sync(self, *, now_ms: int) -> NotificationProcessResult:
        with self._repository_session() as repos, _unit_of_work_if_available(repos):
            rule_engine = self.rule_engine_factory(repos) if self.rule_engine_factory is not None else self.rule_engine
            candidates = list(rule_engine.evaluate(now_ms=now_ms))
            created: list[dict[str, Any]] = []
            external_deliveries_enqueued = False
            for candidate in candidates:
                row = self._insert_candidate_with_repository(repos.notifications, candidate)
                if row is None:
                    continue
                external_deliveries_enqueued = (
                    self._enqueue_external_deliveries_with_repository(repos.notifications, row, candidate)
                    or external_deliveries_enqueued
                )
                created.append(row)
                if len(created) >= self.batch_limit:
                    break
            if not _has_unit_of_work(repos):
                _commit_if_available(getattr(repos, "notifications", None))
        return NotificationProcessResult(
            created=created,
            external_deliveries_enqueued=external_deliveries_enqueued,
        )

    @staticmethod
    def _insert_candidate_with_repository(
        repository: NotificationRepository, candidate: NotificationCandidate
    ) -> dict[str, Any] | None:
        result: dict[str, Any] | None = repository.insert_notification(
            dedup_key=candidate.dedup_key,
            rule_id=candidate.rule_id,
            severity=candidate.severity,
            title=candidate.title,
            body=candidate.body,
            entity_type=candidate.entity_type,
            entity_key=candidate.entity_key,
            author_handle=candidate.author_handle,
            symbol=candidate.symbol,
            chain=candidate.chain,
            address=candidate.address,
            event_id=candidate.event_id,
            source_table=candidate.source_table,
            source_id=candidate.source_id,
            occurrence_at_ms=candidate.occurrence_at_ms,
            payload=candidate.payload,
            channels=candidate.channels,
            commit=False,
        )
        return result

    def _enqueue_external_deliveries_with_repository(
        self,
        repository: NotificationRepository,
        row: dict[str, Any],
        candidate: NotificationCandidate,
    ) -> bool:
        enqueued = False
        for channel_id in _delivery_channels(row, candidate):
            if channel_id == "in_app":
                continue
            channel = self.delivery_channels.get(channel_id)
            if channel is None or not channel.enabled:
                continue
            if channel.provider in {"apprise", "pushdeer"} and not channel.url:
                continue
            if SEVERITY_RANK.get(candidate.severity, 0) < SEVERITY_RANK.get(channel.min_severity, 1):
                continue
            delivery = repository.enqueue_delivery(
                notification_id=str(row["notification_id"]),
                channel_id=channel_id,
                provider=channel.provider,
                max_attempts=self.delivery_max_attempts,
                commit=False,
            )
            enqueued = delivery is not None or enqueued
        return enqueued

    def _repository_session(self) -> AbstractContextManager[RepositorySession]:
        return cast(
            "AbstractContextManager[RepositorySession]",
            self.db.worker_session(
                self.name,
                statement_timeout_seconds=getattr(self.settings, "statement_timeout_seconds", None),
            ),
        )


def _now_ms() -> int:
    return int(time.time() * 1000)


def _commit_if_available(repository: Any) -> None:
    conn = getattr(repository, "conn", None)
    commit = getattr(conn, "commit", None)
    if commit is not None:
        commit()


def _has_unit_of_work(repos: Any) -> bool:
    return getattr(repos, "unit_of_work", None) is not None


def _unit_of_work_if_available(repos: Any) -> AbstractContextManager[Any]:
    unit_of_work = getattr(repos, "unit_of_work", None)
    if unit_of_work is None:
        return nullcontext()
    return cast("AbstractContextManager[Any]", unit_of_work())


def _delivery_channels(row: dict[str, Any], candidate: NotificationCandidate) -> tuple[str, ...]:
    row_channels = row.get("channels_json")
    if isinstance(row_channels, list):
        channels = tuple(str(channel).strip() for channel in row_channels if str(channel).strip())
        return channels or ("in_app",)
    return candidate.channels
