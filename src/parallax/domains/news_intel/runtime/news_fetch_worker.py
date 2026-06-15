from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import Callable, Mapping
from typing import Any, cast

from parallax.app.runtime.worker_base import WorkerBase
from parallax.app.runtime.worker_result import WorkerResult
from parallax.domains.news_intel.providers import NewsSourceProvider
from parallax.domains.news_intel.runtime.news_projection_work import (
    enqueue_page_reprojection,
    enqueue_source_quality_refresh,
)
from parallax.domains.news_intel.services.news_provider_contract import (
    NewsProviderContractError,
    validate_news_provider_contract,
)
from parallax.domains.news_intel.types.news_canonical_identity import canonical_identity_for_observation
from parallax.domains.news_intel.types.source_provider import (
    NewsProviderObservation,
    NewsSourceHttpCache,
    NewsSourceSnapshot,
)
from parallax.domains.news_intel.types.text_normalization import content_hash, title_fingerprint
from parallax.platform.config.news_provider_types import RUNTIME_SUPPORTED_NEWS_PROVIDER_TYPES


class NewsFetchWorker(WorkerBase):
    def __init__(
        self,
        *,
        settings: Any,
        db: Any,
        telemetry: Any,
        news_settings: Any,
        feed_client: NewsSourceProvider,
        wake_waiter: Any | None = None,
        wake_emitter: Any | None = None,
        clock_ms: Callable[[], int] | None = None,
        name: str = "news_fetch",
    ) -> None:
        if settings is None:
            raise RuntimeError("news_fetch_settings_required")
        if db is None:
            raise RuntimeError("news_fetch_db_required")
        if news_settings is None:
            raise RuntimeError("news_fetch_news_settings_required")
        if feed_client is None:
            raise RuntimeError("news_fetch_feed_client_required")
        super().__init__(
            name=name,
            settings=settings,
            db=db,
            telemetry=telemetry,
            wake_waiter=wake_waiter,
        )
        self.news_settings = news_settings
        self.wake_emitter = wake_emitter
        self.feed_client = feed_client
        self.clock_ms = clock_ms or _now_ms

    async def on_close(self) -> None:
        close = cast(Callable[[], object | None], self.feed_client.close)
        result = close()
        if result is not None:
            raise RuntimeError("news_fetch_feed_client_close_must_be_sync")

    async def run_once(self) -> WorkerResult:
        return await asyncio.to_thread(self.run_once_sync)

    def run_once_sync(self, *, now_ms: int | None = None) -> WorkerResult:
        now = int(now_ms if now_ms is not None else self.clock_ms())
        configured_sources = tuple(self.news_settings.sources or ())
        metadata_dirty_count = 0
        with self._repository_session() as repos, repos.transaction():
            try:
                contract = validate_news_provider_contract(
                    configured_sources=configured_sources,
                    supported_provider_types=RUNTIME_SUPPORTED_NEWS_PROVIDER_TYPES,
                    schema_provider_types=repos.news.news_source_provider_constraint_values(),
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
                if str(row.get("status") or "") in {"updated", "disabled"} and row.get("source_id")
            ]
            changed_item_ids = (
                repos.news.list_news_item_ids_for_sources(source_ids=changed_source_ids) if changed_source_ids else []
            )
            metadata_dirty_count = enqueue_page_reprojection(
                repos,
                news_item_ids=changed_item_ids,
                reason="source_metadata_changed",
                now_ms=now,
                commit=False,
            )
            enqueue_source_quality_refresh(
                repos,
                source_ids=changed_source_ids,
                reason="source_metadata_changed",
                now_ms=now,
                commit=False,
            )
            due_sources = repos.news.claim_due_sources(
                now_ms=now,
                limit=self._batch_size(),
                claim_lease_ms=max(1, int(self.settings.lease_ms)),
                commit=False,
            )
        _notify_news_page_dirty(
            self.wake_emitter,
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
            with self._repository_session() as repos, repos.transaction():
                fetch_run_id = repos.news.start_fetch_run(
                    source_id=source_id,
                    started_at_ms=now_ms,
                    commit=False,
                )
                source_cursor = (
                    repos.news.source_sync_cursor(source_id)
                    if str(source.get("provider_type") or "").strip().lower() == "opennews"
                    else {}
                )

            snapshot = NewsSourceSnapshot.from_row(source, now_ms=now_ms)
            cache = NewsSourceHttpCache(
                etag=_optional_str(source.get("etag")),
                last_modified=_optional_str(source.get("last_modified")),
            )
            feed_result = self.feed_client.fetch(
                snapshot,
                since_ms=_source_fetch_since_ms(source=source, source_cursor=source_cursor, now_ms=now_ms),
                cursor=source_cursor,
                cache=cache,
                limit=self._batch_size(),
            )

            with self._repository_session() as repos:
                if feed_result.not_modified:
                    with repos.transaction():
                        repos.news.update_source_http_cache(
                            source_id=source_id,
                            etag=feed_result.etag,
                            last_modified=feed_result.last_modified,
                            now_ms=now_ms,
                            commit=False,
                        )
                        if feed_result.next_cursor:
                            repos.news.update_source_sync_state(
                                source_id,
                                feed_result.next_cursor,
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
                        enqueue_source_quality_refresh(
                            repos,
                            source_ids=[source_id],
                            reason="news_fetch_run_finished",
                            now_ms=now_ms,
                            commit=False,
                        )
                    return WorkerResult(processed=0)

                with repos.transaction():
                    counts = self._persist_entries(
                        repos,
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
                    if feed_result.next_cursor:
                        repos.news.update_source_sync_state(
                            source_id,
                            feed_result.next_cursor,
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
                    enqueue_source_quality_refresh(
                        repos,
                        source_ids=[source_id],
                        reason="news_fetch_run_finished",
                        now_ms=now_ms,
                        commit=False,
                    )
            written = counts["inserted"] + counts["updated"]
            if written > 0 and self.wake_emitter is not None:
                self.wake_emitter.notify_news_item_written(source_id=source_id, count=written)
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
        fetched_at_ms: int,
    ) -> dict[str, int]:
        counts = {"fetched": 0, "inserted": 0, "updated": 0, "duplicate": 0}
        dirty_news_item_ids: list[str] = []
        repository = repos.news
        source_id = str(source["source_id"])
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
            if str(provider.get("status") or "") == "duplicate":
                counts["duplicate"] += 1
                continue
            item_content_hash = content_hash(
                observation.title,
                observation.summary,
                body_text=observation.body_text,
            )
            item_title_fingerprint = title_fingerprint(observation.title)
            item_published_at_ms = int(
                observation.published_at_ms if observation.published_at_ms is not None else fetched_at_ms
            )
            canonical_identity = canonical_identity_for_observation(
                provider_type=str(source["provider_type"]),
                source_id=source_id,
                provider_article_id=str(provider.get("provider_article_id") or ""),
                canonical_url=observation.canonical_url,
                content_hash=item_content_hash,
                title_fingerprint=item_title_fingerprint,
                title=observation.title,
                summary=observation.summary,
                body_text=observation.body_text,
                published_at_ms=item_published_at_ms,
            )
            news = repository.upsert_canonical_news_item(
                provider_item_id=provider["provider_item_id"],
                canonical_identity=canonical_identity,
                canonical_url=observation.canonical_url,
                title=observation.title,
                summary=observation.summary,
                body_text=observation.body_text,
                language=observation.language,
                published_at_ms=observation.published_at_ms,
                fetched_at_ms=fetched_at_ms,
                content_hash=item_content_hash,
                title_fingerprint=item_title_fingerprint,
                now_ms=fetched_at_ms,
                provider_signal=observation.provider_signal,
                provider_token_impacts=observation.provider_token_impacts,
                provider_payload_status=str(
                    provider.get("incoming_provider_payload_status") or provider.get("provider_payload_status") or ""
                ),
                commit=False,
            )
            news_item_id = str(news.get("news_item_id") or "")
            status = str(news.get("status") or provider.get("status") or "duplicate")
            if status in counts:
                counts[status] += 1
            if news_item_id and status in {"inserted", "updated"}:
                affected_item_ids = _affected_news_item_ids(news)
                dirty_news_item_ids.extend(affected_item_ids)
        enqueue_page_reprojection(
            repos,
            news_item_ids=dirty_news_item_ids,
            reason="news_item_written",
            now_ms=fetched_at_ms,
            source_watermark_ms_by_news_item_id={news_item_id: fetched_at_ms for news_item_id in dirty_news_item_ids},
            commit=False,
        )
        return counts

    def _mark_source_failed(self, *, source_id: str, fetch_run_id: str, now_ms: int, error: Exception) -> None:
        if not fetch_run_id:
            return
        try:
            with self._repository_session() as repos, repos.transaction():
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
            statement_timeout_seconds=self.settings.statement_timeout_seconds,
        )

    def _batch_size(self) -> int:
        return max(1, int(self.settings.batch_size))


def _payload_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _notify_news_page_dirty(wake_emitter: Any | None, *, count: int, reason: str) -> None:
    if count <= 0 or wake_emitter is None:
        return
    wake_emitter.notify_news_page_dirty(count=int(count), reason=str(reason))


def _cursor_high_watermark_ms(cursor: Mapping[str, Any]) -> int | None:
    try:
        value = int(cursor.get("high_watermark_ms") or 0)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _source_fetch_since_ms(
    *,
    source: Mapping[str, Any],
    source_cursor: Mapping[str, Any],
    now_ms: int,
) -> int | None:
    if str(source.get("provider_type") or "").strip().lower() != "opennews":
        return None
    cursor_high_watermark_ms = _cursor_high_watermark_ms(source_cursor)
    if cursor_high_watermark_ms is not None:
        return max(0, cursor_high_watermark_ms - _fetch_policy_overlap_ms(source, source_cursor))
    max_initial_fetch_age_ms = _fetch_policy_int(source, "max_initial_fetch_age_ms")
    if max_initial_fetch_age_ms is None:
        max_initial_fetch_age_ms = _fetch_policy_int(source, "max_catchup_age_ms")
    if max_initial_fetch_age_ms is None:
        return None
    return max(0, int(now_ms) - max_initial_fetch_age_ms)


def _fetch_policy_overlap_ms(source: Mapping[str, Any], source_cursor: Mapping[str, Any]) -> int:
    value = _fetch_policy_int(source, "rest_overlap_ms")
    if value is None:
        try:
            value = int(source_cursor.get("overlap_ms") or 0)
        except (TypeError, ValueError):
            value = 0
    return max(0, int(value or 0))


def _fetch_policy_int(source: Mapping[str, Any], key: str) -> int | None:
    raw = source.get("fetch_policy_json")
    if raw is None:
        raw = source.get("fetch_policy")
    policy = _mapping(raw)
    value = policy.get(key)
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _affected_news_item_ids(news: Mapping[str, Any]) -> list[str]:
    raw_ids = news.get("affected_news_item_ids")
    item_ids = [str(item) for item in raw_ids if str(item or "")] if isinstance(raw_ids, list | tuple) else []
    if not item_ids:
        raise ValueError("canonical news upsert returned no affected_news_item_ids")
    return list(dict.fromkeys(item_ids))


def _optional_str(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, Mapping) else {}
    return {}


def _now_ms() -> int:
    return int(time.time() * 1000)
