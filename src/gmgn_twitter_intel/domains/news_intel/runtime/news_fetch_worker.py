from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import Callable, Iterable, Mapping
from inspect import isawaitable
from typing import Any

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.domains.news_intel.providers import NewsSourceProvider
from gmgn_twitter_intel.domains.news_intel.services.news_provider_contract import (
    NewsProviderContractError,
    validate_news_provider_contract,
)
from gmgn_twitter_intel.domains.news_intel.services.text_normalization import content_hash, title_fingerprint
from gmgn_twitter_intel.domains.news_intel.types.source_classification import PROVIDER_TYPES
from gmgn_twitter_intel.domains.news_intel.types.source_provider import (
    NewsProviderContextObservation,
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
        source_quality_windows: Iterable[str] | None = None,
        clock_ms: Callable[[], int] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.news_settings = news_settings
        self.wake_bus = wake_bus
        self.feed_client = feed_client
        self.source_quality_windows = _source_quality_windows(source_quality_windows)
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
        metadata_dirty_count = 0
        with self._repository_session() as repos, repos.conn.transaction():
            try:
                contract = validate_news_provider_contract(
                    configured_sources=configured_sources,
                    supported_provider_types=_supported_provider_types(self.feed_client),
                    schema_provider_types=_schema_provider_types(repos.news),
                )
            except NewsProviderContractError as exc:
                return WorkerResult(failed=1, notes=exc.to_payload())
            reconciled_sources = repos.news.reconcile_configured_sources(
                configured_sources,
                now_ms=now,
                commit=False,
            )
            changed_source_ids = [
                str(row["source_id"])
                for row in reconciled_sources
                if str(row.get("status") or "") == "updated" and row.get("source_id")
            ]
            changed_item_ids = (
                repos.news.list_news_item_ids_for_sources(source_ids=changed_source_ids) if changed_source_ids else []
            )
            metadata_dirty_count = _enqueue_news_item_dirty_targets(
                repos,
                news_item_ids=changed_item_ids,
                projection_names=("page",),
                reason="source_metadata_changed",
                now_ms=now,
            )
            _enqueue_source_quality_dirty_targets(
                repos,
                source_ids=changed_source_ids,
                windows=self.source_quality_windows,
                reason="source_metadata_changed",
                now_ms=now,
            )
            due_sources = repos.news.claim_due_sources(now_ms=now, limit=self._batch_size(), commit=False)
        _notify_news_page_dirty(
            self.wake_bus,
            count=metadata_dirty_count,
            reason="source_metadata_changed",
        )

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
            notes={"due_sources": source_count, "news_provider_contract": contract},
        )

    def _fetch_source(self, source: dict[str, Any], *, now_ms: int) -> WorkerResult:
        source_id = str(source["source_id"])
        fetch_run_id = ""
        try:
            with self._repository_session() as repos, repos.conn.transaction():
                fetch_run_id = repos.news.start_fetch_run(
                    source_id=source_id,
                    started_at_ms=now_ms,
                    commit=False,
                )

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
                    with repos.conn.transaction():
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
                            commit=False,
                        )
                        _enqueue_source_quality_dirty_targets(
                            repos,
                            source_ids=[source_id],
                            windows=self.source_quality_windows,
                            reason="news_fetch_run_finished",
                            now_ms=now_ms,
                        )
                    return WorkerResult(processed=0)

                with repos.conn.transaction():
                    counts = self._persist_entries(
                        repos,
                        source=source,
                        fetch_run_id=fetch_run_id,
                        observations=feed_result.observations,
                        context_observations=feed_result.context_observations,
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
                        commit=False,
                    )
                    _enqueue_source_quality_dirty_targets(
                        repos,
                        source_ids=[source_id],
                        windows=self.source_quality_windows,
                        reason="news_fetch_run_finished",
                        now_ms=now_ms,
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
        repos: Any,
        *,
        source: Mapping[str, Any],
        fetch_run_id: str,
        observations: list[NewsProviderObservation],
        context_observations: list[NewsProviderContextObservation],
        fetched_at_ms: int,
    ) -> dict[str, int]:
        counts = {"fetched": 0, "inserted": 0, "updated": 0, "duplicate": 0}
        dirty_news_item_ids: list[str] = []
        repository = repos.news
        source_id = str(source["source_id"])
        source_domain = str(source["source_domain"])
        parent_ids_by_source_key: dict[str, str] = {}
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
                provider_signal=observation.provider_signal,
                provider_token_impacts=observation.provider_token_impacts,
                commit=False,
            )
            news_item_id = str(news.get("news_item_id") or "")
            if news_item_id:
                parent_ids_by_source_key[observation.source_item_key] = news_item_id
            status = str(news.get("status") or provider.get("status") or "duplicate")
            if status in counts:
                counts[status] += 1
            if news_item_id and status in {"inserted", "updated"}:
                dirty_news_item_ids.append(news_item_id)
        _enqueue_news_item_dirty_targets(
            repos,
            news_item_ids=dirty_news_item_ids,
            projection_names=("story", "page"),
            reason="news_item_written",
            now_ms=fetched_at_ms,
        )
        context_parent_ids = self._persist_context_observations(
            repository,
            source_id=source_id,
            parent_ids_by_source_key=parent_ids_by_source_key,
            context_observations=context_observations,
            fetched_at_ms=fetched_at_ms,
        )
        _enqueue_news_item_dirty_targets(
            repos,
            news_item_ids=context_parent_ids,
            projection_names=("page", "brief_input"),
            reason="news_context_written",
            now_ms=fetched_at_ms,
        )
        return counts

    def _persist_context_observations(
        self,
        repository: Any,
        *,
        source_id: str,
        parent_ids_by_source_key: Mapping[str, str],
        context_observations: list[NewsProviderContextObservation],
        fetched_at_ms: int,
    ) -> list[str]:
        dirty_parent_ids: list[str] = []
        for context in context_observations:
            parent_news_item_id = parent_ids_by_source_key.get(context.parent_source_item_key)
            repository.upsert_news_context_item(
                context_item_id=context.context_item_id,
                source_id=source_id,
                parent_news_item_id=parent_news_item_id,
                provider_item_id=None,
                context_type=context.context_type,
                author=context.author,
                canonical_url=context.canonical_url,
                body_text=context.body_text,
                published_at_ms=context.published_at_ms,
                engagement_json=context.engagement or {},
                raw_payload_json=context.raw_payload,
                created_at_ms=fetched_at_ms,
                commit=False,
            )
            if parent_news_item_id:
                dirty_parent_ids.append(parent_news_item_id)
        return list(dict.fromkeys(dirty_parent_ids))

    def _mark_source_failed(self, *, source_id: str, fetch_run_id: str, now_ms: int, error: Exception) -> None:
        if not fetch_run_id:
            return
        try:
            with self._repository_session() as repos, repos.conn.transaction():
                repos.news.finish_fetch_run(
                    fetch_run_id=fetch_run_id,
                    source_id=source_id,
                    status="failed",
                    finished_at_ms=now_ms,
                    error=str(error),
                    commit=False,
                )
        except Exception:
            return

    def _repository_session(self) -> Any:
        return self.db.worker_session(
            self.name,
            statement_timeout_seconds=getattr(self.settings, "statement_timeout_seconds", None),
        )

    def _batch_size(self) -> int:
        return max(1, int(getattr(self.settings, "batch_size", 10)))


def _payload_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _enqueue_news_item_dirty_targets(
    repos: Any,
    *,
    news_item_ids: list[str],
    projection_names: Iterable[str],
    reason: str,
    now_ms: int,
) -> int:
    targets = [
        {"projection_name": projection_name, "target_kind": "news_item", "target_id": news_item_id}
        for projection_name in dict.fromkeys(str(name) for name in projection_names if str(name))
        for news_item_id in dict.fromkeys(str(item) for item in news_item_ids if str(item))
    ]
    if not targets:
        return 0
    return int(repos.news_projection_dirty_targets.enqueue_targets(targets, reason=reason, now_ms=now_ms, commit=False))


def _enqueue_source_quality_dirty_targets(
    repos: Any,
    *,
    source_ids: Iterable[str],
    windows: Iterable[str],
    reason: str,
    now_ms: int,
) -> int:
    targets = [
        {
            "projection_name": "source_quality",
            "target_kind": "source",
            "target_id": source_id,
            "window": window,
        }
        for source_id in dict.fromkeys(str(source_id) for source_id in source_ids if str(source_id))
        for window in _source_quality_windows(windows)
    ]
    if not targets:
        return 0
    return int(repos.news_projection_dirty_targets.enqueue_targets(targets, reason=reason, now_ms=now_ms, commit=False))


def _notify_news_page_dirty(wake_bus: Any | None, *, count: int, reason: str) -> None:
    if count <= 0 or wake_bus is None:
        return
    notify = getattr(wake_bus, "notify_news_page_dirty", None)
    if notify is None:
        return
    notify(count=int(count), reason=str(reason))


def _source_quality_windows(windows: Iterable[str] | None) -> tuple[str, ...]:
    normalized = tuple(dict.fromkeys(str(window).strip().lower() for window in (windows or ()) if str(window).strip()))
    return normalized or ("24h", "7d")


def _optional_str(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _supported_provider_types(feed_client: NewsSourceProvider) -> tuple[str, ...]:
    supported = getattr(feed_client, "supported_provider_types", None)
    if callable(supported):
        return tuple(str(value) for value in supported())
    registry = getattr(feed_client, "_registry", None)
    registry_supported = getattr(registry, "supported_provider_types", None)
    if callable(registry_supported):
        return tuple(str(value) for value in registry_supported())
    return tuple(PROVIDER_TYPES)


def _schema_provider_types(repository: Any) -> tuple[str, ...]:
    constraint_values = getattr(repository, "news_source_provider_constraint_values", None)
    if callable(constraint_values):
        return tuple(str(value) for value in constraint_values())
    return tuple(PROVIDER_TYPES)


def _now_ms() -> int:
    return int(time.time() * 1000)
