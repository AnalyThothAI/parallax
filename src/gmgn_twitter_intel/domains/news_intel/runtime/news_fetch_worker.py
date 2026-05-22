from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import Callable, Mapping
from inspect import isawaitable
from typing import Any

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.domains.news_intel.providers import NewsSourceProvider
from gmgn_twitter_intel.domains.news_intel.services.text_normalization import content_hash, title_fingerprint
from gmgn_twitter_intel.domains.news_intel.types.source_provider import (
    NewsProviderObservation,
    NewsSourceHttpCache,
    NewsSourceSnapshot,
)


class NewsFetchWorker(WorkerBase):
    def __init__(
        self,
        *,
        news_settings: Any,
        wake_bus: Any | None,
        feed_client: NewsSourceProvider,
        clock_ms: Callable[[], int] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.news_settings = news_settings
        self.wake_bus = wake_bus
        self.feed_client = feed_client
        self.clock_ms = clock_ms or _now_ms

    async def on_close(self) -> None:
        close = getattr(self.feed_client, "close", None)
        if close is None:
            return
        result = close()
        if isawaitable(result):
            await result

    async def run_once(self) -> WorkerResult:
        return await asyncio.to_thread(self.run_once_sync)

    def run_once_sync(self, *, now_ms: int | None = None) -> WorkerResult:
        now = int(now_ms if now_ms is not None else self.clock_ms())
        configured_sources = tuple(getattr(self.news_settings, "sources", ()) or ())
        with self._repository_session() as repos:
            repos.news.reconcile_configured_sources(configured_sources, now_ms=now)
            due_sources = repos.news.claim_due_sources(now_ms=now, limit=self._batch_size())

        processed = 0
        failed = 0
        source_count = 0
        for source in due_sources:
            source_count += 1
            result = self._fetch_source(dict(source), now_ms=now)
            processed += result.processed
            failed += result.failed

        return WorkerResult(
            processed=processed,
            failed=failed,
            skipped=max(0, len(configured_sources) - source_count),
            notes={"due_sources": source_count},
        )

    def _fetch_source(self, source: dict[str, Any], *, now_ms: int) -> WorkerResult:
        source_id = str(source["source_id"])
        fetch_run_id = ""
        try:
            with self._repository_session() as repos:
                fetch_run_id = repos.news.start_fetch_run(source_id=source_id, started_at_ms=now_ms)

            snapshot = NewsSourceSnapshot.from_row(source, now_ms=now_ms)
            cache = NewsSourceHttpCache(
                etag=_optional_str(source.get("etag")),
                last_modified=_optional_str(source.get("last_modified")),
            )
            feed_result = self.feed_client.fetch(
                snapshot,
                since_ms=None,
                cursor={},
                cache=cache,
                limit=self._batch_size(),
            )

            with self._repository_session() as repos:
                if feed_result.not_modified:
                    repos.news.update_source_http_cache(
                        source_id=source_id,
                        etag=feed_result.etag,
                        last_modified=feed_result.last_modified,
                        now_ms=now_ms,
                        commit=False,
                    )
                    repos.news.finish_fetch_run(
                        fetch_run_id=fetch_run_id,
                        source_id=source_id,
                        status="success",
                        finished_at_ms=now_ms,
                        fetched_count=0,
                        inserted_count=0,
                        updated_count=0,
                        duplicate_count=0,
                        http_status=feed_result.status_code,
                    )
                    return WorkerResult(processed=0)

                counts = self._persist_entries(
                    repos.news,
                    source=source,
                    fetch_run_id=fetch_run_id,
                    observations=feed_result.observations,
                    fetched_at_ms=now_ms,
                )
                repos.news.update_source_http_cache(
                    source_id=source_id,
                    etag=feed_result.etag,
                    last_modified=feed_result.last_modified,
                    now_ms=now_ms,
                    commit=False,
                )
                repos.news.finish_fetch_run(
                    fetch_run_id=fetch_run_id,
                    source_id=source_id,
                    status="success",
                    finished_at_ms=now_ms,
                    fetched_count=counts["fetched"],
                    inserted_count=counts["inserted"],
                    updated_count=counts["updated"],
                    duplicate_count=counts["duplicate"],
                    http_status=feed_result.status_code,
                )
            written = counts["inserted"] + counts["updated"]
            if written > 0 and self.wake_bus is not None:
                self.wake_bus.notify_news_item_written(source_id=source_id, count=written)
            return WorkerResult(processed=written)
        except Exception as exc:  # pragma: no cover - failure path covered by integration/ops.
            self._mark_source_failed(source_id=source_id, fetch_run_id=fetch_run_id, now_ms=now_ms, error=exc)
            return WorkerResult(failed=1, notes={"source_id": source_id, "error": str(exc)})

    def _persist_entries(
        self,
        repository: Any,
        *,
        source: Mapping[str, Any],
        fetch_run_id: str,
        observations: list[NewsProviderObservation],
        fetched_at_ms: int,
    ) -> dict[str, int]:
        counts = {"fetched": 0, "inserted": 0, "updated": 0, "duplicate": 0}
        source_id = str(source["source_id"])
        source_domain = str(source["source_domain"])
        for observation in observations:
            counts["fetched"] += 1
            provider = repository.upsert_provider_item(
                source_id=source_id,
                fetch_run_id=fetch_run_id,
                source_item_key=observation.source_item_key,
                canonical_url=observation.canonical_url,
                payload_hash=_payload_hash(observation.raw_payload),
                raw_payload=observation.raw_payload,
                fetched_at_ms=fetched_at_ms,
                commit=False,
            )
            news = repository.upsert_news_item(
                provider_item_id=provider["provider_item_id"],
                source_id=source_id,
                source_domain=source_domain,
                canonical_url=observation.canonical_url,
                title=observation.title,
                summary=observation.summary,
                body_text=observation.body_text,
                language=observation.language,
                published_at_ms=observation.published_at_ms,
                fetched_at_ms=fetched_at_ms,
                content_hash=content_hash(
                    observation.title,
                    observation.summary,
                    observation.canonical_url,
                    body_text=observation.body_text,
                ),
                title_fingerprint=title_fingerprint(observation.title),
                now_ms=fetched_at_ms,
                commit=False,
            )
            status = str(news.get("status") or provider.get("status") or "duplicate")
            if status in counts:
                counts[status] += 1
        return counts

    def _mark_source_failed(self, *, source_id: str, fetch_run_id: str, now_ms: int, error: Exception) -> None:
        if not fetch_run_id:
            return
        try:
            with self._repository_session() as repos:
                repos.news.finish_fetch_run(
                    fetch_run_id=fetch_run_id,
                    source_id=source_id,
                    status="failed",
                    finished_at_ms=now_ms,
                    error=str(error),
                )
        except Exception:
            return

    def _repository_session(self):
        return self.db.worker_session(
            self.name,
            statement_timeout_seconds=getattr(self.settings, "statement_timeout_seconds", None),
        )

    def _batch_size(self) -> int:
        return max(1, int(getattr(self.settings, "batch_size", 10)))


def _payload_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _optional_str(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _now_ms() -> int:
    return int(time.time() * 1000)
