from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import Callable, Mapping
from typing import Any, cast

from parallax.domains.news_intel.providers import NewsSourceProvider, NewsSourceProviderError
from parallax.domains.news_intel.runtime.news_projection_work import enqueue_page_reprojection
from parallax.domains.news_intel.services.news_provider_contract import (
    NewsProviderContractError,
    validate_news_provider_contract,
)
from parallax.domains.news_intel.types.source_provider import (
    NewsProviderObservation,
    NewsSourceHttpCache,
    NewsSourceSnapshot,
)
from parallax.domains.news_intel.types.text_normalization import content_hash, title_fingerprint
from parallax.platform.config.news_provider_types import RUNTIME_SUPPORTED_NEWS_PROVIDER_TYPES
from parallax.platform.config.settings import NewsFetchWorkerSettings, NewsIntelSettings
from parallax.platform.runtime.worker_base import WorkerBase
from parallax.platform.runtime.worker_result import WorkerResult

_RETENTION_INTERVAL_MS = 60 * 60 * 1_000
_SUCCESS_FETCH_RUN_RETENTION_MS = 30 * 24 * 60 * 60 * 1_000
_SUCCESS_FETCH_RUN_RETENTION_LIMIT = 1_000


class NewsFetchWorker(WorkerBase):
    def __init__(
        self,
        *,
        settings: NewsFetchWorkerSettings,
        db: Any,
        telemetry: Any,
        news_settings: NewsIntelSettings,
        feed_client: NewsSourceProvider,
        wake_waiter: Any | None = None,
        wake_emitter: Any | None = None,
        clock_ms: Callable[[], int] | None = None,
        name: str = "news_fetch",
    ) -> None:
        if db is None:
            raise RuntimeError("news_fetch_db_required")
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
        self._sources_reconciled = False
        self._terminal_source_errors: dict[str, str] = {}
        self._next_retention_prune_at_ms = 0

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
        pruned_successful_fetch_runs = 0
        retention_due = now >= self._next_retention_prune_at_ms
        should_reconcile = not self._sources_reconciled
        with self._repository_session() as repos, repos.transaction():
            try:
                contract = validate_news_provider_contract(
                    configured_sources=configured_sources,
                    supported_provider_types=RUNTIME_SUPPORTED_NEWS_PROVIDER_TYPES,
                    schema_provider_types=repos.news_sources.news_source_provider_constraint_values(),
                )
            except NewsProviderContractError as exc:
                return WorkerResult(failed=1, notes=exc.to_payload())
            if retention_due:
                pruned_successful_fetch_runs = repos.news_sources.prune_successful_fetch_runs(
                    cutoff_ms=max(0, now - _SUCCESS_FETCH_RUN_RETENTION_MS),
                    limit=_SUCCESS_FETCH_RUN_RETENTION_LIMIT,
                )
            reconciled_sources = (
                repos.news_sources.reconcile_configured_sources(
                    configured_sources,
                    now_ms=now,
                )
                if should_reconcile
                else []
            )
            changed_source_ids = [
                str(row["source_id"])
                for row in reconciled_sources
                if str(row.get("status") or "") in {"updated", "disabled"} and row.get("source_id")
            ]
            changed_item_watermarks = _metadata_changed_item_watermarks(
                repos.news_sources.list_news_item_source_watermarks_for_sources(source_ids=changed_source_ids)
                if changed_source_ids
                else []
            )
            metadata_dirty_count = enqueue_page_reprojection(
                repos,
                news_item_ids=changed_item_watermarks,
                reason="source_metadata_changed",
                now_ms=now,
                source_watermark_ms_by_news_item_id=changed_item_watermarks,
            )
            due_sources = repos.news_sources.claim_due_sources(
                now_ms=now,
                limit=self._batch_size(),
                claim_lease_ms=self._lease_ms(),
            )
        if retention_due:
            self._next_retention_prune_at_ms = now + _RETENTION_INTERVAL_MS
        if should_reconcile:
            self._sources_reconciled = True
            self._terminal_source_errors = _terminal_source_errors(reconciled_sources)
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
            notes={
                "due_sources": source_count,
                "news_provider_contract": contract,
                "degraded": bool(self._terminal_source_errors),
                "terminal_sources": dict(sorted(self._terminal_source_errors.items())),
                "pruned_successful_fetch_runs": pruned_successful_fetch_runs,
            },
        )

    def _fetch_source(self, source: dict[str, Any], *, now_ms: int) -> WorkerResult:
        source_id = str(source["source_id"])
        fetch_run_id = ""
        try:
            with self._repository_session() as repos, repos.transaction():
                fetch_run_id = repos.news_sources.start_fetch_run(
                    source_id=source_id,
                    started_at_ms=now_ms,
                )
                source_cursor = (
                    repos.news_sources.source_sync_cursor(source_id)
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
                        repos.news_sources.update_source_http_cache(
                            source_id=source_id,
                            etag=feed_result.etag,
                            last_modified=feed_result.last_modified,
                            now_ms=now_ms,
                        )
                        if feed_result.next_cursor:
                            repos.news_sources.update_source_sync_state(
                                source_id,
                                feed_result.next_cursor,
                                now_ms=now_ms,
                            )
                        repos.news_sources.finish_fetch_run(
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

                with repos.transaction():
                    counts = self._persist_entries(
                        repos,
                        source=source,
                        fetch_run_id=fetch_run_id,
                        observations=feed_result.observations,
                        fetched_at_ms=now_ms,
                    )
                    repos.news_sources.update_source_http_cache(
                        source_id=source_id,
                        etag=feed_result.etag,
                        last_modified=feed_result.last_modified,
                        now_ms=now_ms,
                    )
                    if feed_result.next_cursor:
                        repos.news_sources.update_source_sync_state(
                            source_id,
                            feed_result.next_cursor,
                            now_ms=now_ms,
                        )
                    repos.news_sources.finish_fetch_run(
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
            if written > 0 and self.wake_emitter is not None:
                self.wake_emitter.notify_news_item_written(source_id=source_id, count=written)
            return WorkerResult(processed=written)
        except NewsSourceProviderError as exc:
            if exc.terminal:
                self._mark_source_terminal(
                    source_id=source_id,
                    fetch_run_id=fetch_run_id,
                    now_ms=now_ms,
                    error=exc,
                )
            else:
                self._mark_source_failed(
                    source_id=source_id,
                    fetch_run_id=fetch_run_id,
                    now_ms=now_ms,
                    error=exc,
                    http_status=exc.status_code,
                )
            return WorkerResult(failed=1, notes={"source_id": source_id, "error": exc.error_code})
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
        source_repository = repos.news_sources
        item_repository = repos.news_items
        source_id = str(source["source_id"])
        for observation in observations:
            counts["fetched"] += 1
            provider = source_repository.upsert_provider_item(
                source_id=source_id,
                fetch_run_id=fetch_run_id,
                source_item_key=observation.source_item_key,
                canonical_url=observation.canonical_url,
                payload_hash=_payload_hash(observation.raw_payload),
                raw_payload=observation.raw_payload,
                fetched_at_ms=fetched_at_ms,
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
            news = item_repository.upsert_canonical_news_item(
                provider_item_id=provider["provider_item_id"],
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
            )
            news_item_id = str(news.get("news_item_id") or "")
            status = str(news.get("status") or provider.get("status") or "duplicate")
            if status in counts:
                counts[status] += 1
            if news_item_id and status in {"inserted", "updated"}:
                affected_item_ids = _affected_news_item_ids(news)
                dirty_news_item_ids.extend(affected_item_ids)
        dirty_item_watermarks = _written_item_watermarks(
            source_repository.list_news_item_source_watermarks(news_item_ids=dirty_news_item_ids)
            if dirty_news_item_ids
            else []
        )
        enqueue_page_reprojection(
            repos,
            news_item_ids=dirty_news_item_ids,
            reason="news_item_written",
            now_ms=fetched_at_ms,
            source_watermark_ms_by_news_item_id=dirty_item_watermarks,
        )
        return counts

    def _mark_source_failed(
        self,
        *,
        source_id: str,
        fetch_run_id: str,
        now_ms: int,
        error: Exception,
        http_status: int | None = None,
    ) -> None:
        if not fetch_run_id:
            return
        try:
            with self._repository_session() as repos, repos.transaction():
                repos.news_sources.finish_fetch_run(
                    fetch_run_id=fetch_run_id,
                    source_id=source_id,
                    status="failed",
                    finished_at_ms=now_ms,
                    fetched_count=0,
                    inserted_count=0,
                    updated_count=0,
                    duplicate_count=0,
                    http_status=http_status,
                    error=str(error),
                )
        except Exception:
            return

    def _mark_source_terminal(
        self,
        *,
        source_id: str,
        fetch_run_id: str,
        now_ms: int,
        error: NewsSourceProviderError,
    ) -> None:
        if not fetch_run_id:
            return
        with self._repository_session() as repos, repos.transaction():
            repos.news_sources.finish_fetch_run(
                fetch_run_id=fetch_run_id,
                source_id=source_id,
                status="failed",
                finished_at_ms=now_ms,
                fetched_count=0,
                inserted_count=0,
                updated_count=0,
                duplicate_count=0,
                http_status=error.status_code,
                error=error.error_code,
            )
            repos.news_sources.disable_source(
                source_id=source_id,
                error=error.error_code,
                now_ms=now_ms,
            )
        self._terminal_source_errors[source_id] = error.error_code

    def _repository_session(self) -> Any:
        return self.db.worker_session(
            self.name,
            statement_timeout_seconds=self.settings.statement_timeout_seconds,
        )

    def _batch_size(self) -> int:
        return self.settings.batch_size

    def _lease_ms(self) -> int:
        return self.settings.lease_ms


def _payload_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _terminal_source_errors(rows: list[Mapping[str, Any]]) -> dict[str, str]:
    terminal_errors: dict[str, str] = {}
    for row in rows:
        terminal_config_payload_hash = row["terminal_config_payload_hash"]
        if terminal_config_payload_hash is None:
            continue
        source_id = row["source_id"]
        error = row["last_error"]
        if not isinstance(source_id, str) or not source_id.strip():
            raise ValueError("news_fetch_terminal_source_id_required")
        if not isinstance(error, str) or not error.strip():
            raise ValueError("news_fetch_terminal_source_error_required")
        terminal_errors[source_id.strip()] = error.strip()
    return terminal_errors


def _notify_news_page_dirty(wake_emitter: Any | None, *, count: int, reason: str) -> None:
    if count <= 0 or wake_emitter is None:
        return
    wake_emitter.notify_news_page_dirty(count=int(count), reason=str(reason))


def _metadata_changed_item_watermarks(rows: list[Mapping[str, Any]]) -> dict[str, int]:
    watermarks: dict[str, int] = {}
    for row in rows:
        news_item_id = _required_metadata_dirty_text(row, "news_item_id")
        source_watermark_ms = _required_metadata_dirty_watermark(row)
        watermarks[news_item_id] = max(watermarks.get(news_item_id, 0), source_watermark_ms)
    return watermarks


def _written_item_watermarks(rows: list[Mapping[str, Any]]) -> dict[str, int]:
    watermarks: dict[str, int] = {}
    for row in rows:
        news_item_id = _required_written_item_dirty_text(row, "news_item_id")
        source_watermark_ms = _required_written_item_dirty_watermark(row)
        watermarks[news_item_id] = max(watermarks.get(news_item_id, 0), source_watermark_ms)
    return watermarks


def _required_metadata_dirty_text(row: Mapping[str, Any], field_name: str) -> str:
    try:
        value = row[field_name]
    except KeyError as exc:
        raise ValueError(f"news_fetch_metadata_dirty_{field_name}_required") from exc
    if not isinstance(value, str):
        raise ValueError(f"news_fetch_metadata_dirty_{field_name}_required")
    text = value.strip()
    if not text:
        raise ValueError(f"news_fetch_metadata_dirty_{field_name}_required")
    return text


def _required_metadata_dirty_watermark(row: Mapping[str, Any]) -> int:
    try:
        value = row["source_watermark_ms"]
    except KeyError as exc:
        raise ValueError("news_fetch_metadata_dirty_source_watermark_required") from exc
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("news_fetch_metadata_dirty_source_watermark_required")
    if value <= 0:
        raise ValueError("news_fetch_metadata_dirty_source_watermark_required")
    return int(value)


def _required_written_item_dirty_text(row: Mapping[str, Any], field_name: str) -> str:
    try:
        value = row[field_name]
    except KeyError as exc:
        raise ValueError(f"news_fetch_item_dirty_{field_name}_required") from exc
    if not isinstance(value, str):
        raise ValueError(f"news_fetch_item_dirty_{field_name}_required")
    text = value.strip()
    if not text:
        raise ValueError(f"news_fetch_item_dirty_{field_name}_required")
    return text


def _required_written_item_dirty_watermark(row: Mapping[str, Any]) -> int:
    try:
        value = row["source_watermark_ms"]
    except KeyError as exc:
        raise ValueError("news_fetch_item_dirty_source_watermark_required") from exc
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("news_fetch_item_dirty_source_watermark_required")
    if value <= 0:
        raise ValueError("news_fetch_item_dirty_source_watermark_required")
    return int(value)


def _cursor_high_watermark_ms(cursor: Mapping[str, Any]) -> int | None:
    if "high_watermark_ms" not in cursor:
        return None
    value = cursor["high_watermark_ms"]
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("news_fetch_cursor_high_watermark_ms_required")
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
        return _required_cursor_overlap_ms(source_cursor)
    return value


def _required_cursor_overlap_ms(source_cursor: Mapping[str, Any]) -> int:
    if "overlap_ms" not in source_cursor:
        raise ValueError("news_fetch_cursor_overlap_ms_required")
    value = source_cursor["overlap_ms"]
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("news_fetch_cursor_overlap_ms_required")
    return int(value)


def _fetch_policy_int(source: Mapping[str, Any], key: str) -> int | None:
    policy = _optional_fetch_policy_mapping(source.get("fetch_policy_json"), "fetch_policy_json")
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


def _optional_fetch_policy_mapping(value: Any, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    raise ValueError(f"news_fetch_{field_name}_required")


def _now_ms() -> int:
    return int(time.time() * 1000)
