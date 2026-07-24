from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from tracefold.news.ingest.canonical_identity import (
    PROVIDER_GLOBAL_ARTICLE_ID_TYPES,
    provider_global_article_key,
)
from tracefold.news.ingest.repository_support import (
    _compact_error,
    _json,
    _json_dict,
    _merge_provider_payload_status,
    _news_source_config_payload_hash,
    _normalized_news_source_config_payload,
    _optional_fetch_run_extra_json,
    _optional_fetch_run_http_status,
    _optional_source_config_payload_hash,
    _positive_optional_int,
    _provider_article_id,
    _provider_article_id_from_global_key,
    _provider_payload_status,
    _provider_published_at_ms,
    _quoted_constraint_values,
    _required_fetch_run_completion_status,
    _required_fetch_run_count,
    _required_fetch_run_finished_at_ms,
    _required_positive_news_item_source_watermark,
    _required_returning_row,
    _required_source_sync_cursor_nonnegative_int,
    _source_material_changed,
    _source_payload,
    _source_status_payload,
)
from tracefold.news.ingest.source_config import NewsSourceConfig
from tracefold.news.projection.constants import NEWS_PAGE_PROJECTION_VERSION
from tracefold.platform.postgres.write_contract import expect_mutation_count, mutation_count
from tracefold.platform.validation import require_nonnegative_int, require_positive_int


class NewsSourceRepository:
    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def news_source_provider_constraint_values(self) -> tuple[str, ...]:
        row = self.conn.execute(
            """
            SELECT pg_get_constraintdef(oid) AS constraint_def
             FROM pg_constraint
             WHERE conname = %s
               AND conrelid = 'news_sources'::regclass
             ORDER BY oid DESC
             LIMIT 1
            """,
            ("news_sources_provider_type_check",),
        ).fetchone()
        if row is None:
            return ()
        return _quoted_constraint_values(str(row["constraint_def"] or ""))

    def upsert_source(
        self,
        *,
        source_id: str,
        provider_type: str,
        feed_url: str,
        source_domain: str,
        source_name: str,
        source_role: str = "observed_source",
        trust_tier: str = "standard",
        managed_by_config: bool = True,
        enabled: bool = True,
        refresh_interval_seconds: int = 300,
        coverage_tags: object = (),
        asset_universe: object = (),
        authority_scope: Mapping[str, Any] | None = None,
        fetch_policy: Mapping[str, Any] | None = None,
        cost_policy: Mapping[str, Any] | None = None,
        now_ms: int,
    ) -> dict[str, Any]:
        payload = _normalized_news_source_config_payload(
            source_id=source_id,
            provider_type=provider_type,
            feed_url=feed_url,
            source_domain=source_domain,
            source_name=source_name,
            source_role=source_role,
            trust_tier=trust_tier,
            managed_by_config=managed_by_config,
            enabled=enabled,
            refresh_interval_seconds=refresh_interval_seconds,
            coverage_tags=coverage_tags,
            asset_universe=asset_universe,
            authority_scope=authority_scope,
            fetch_policy=fetch_policy,
            cost_policy=cost_policy,
        )
        config_payload_hash = _news_source_config_payload_hash(payload)
        payload["config_payload_hash"] = config_payload_hash
        existing = self.conn.execute(
            "SELECT * FROM news_sources WHERE source_id = %s",
            (payload["source_id"],),
        ).fetchone()
        status = "inserted"
        if existing is not None:
            terminal_config_payload_hash = _optional_source_config_payload_hash(
                existing["terminal_config_payload_hash"],
                field_name="terminal_config_payload_hash",
            )
            terminal_config_matches = terminal_config_payload_hash == config_payload_hash
            effective_payload = {
                **payload,
                "enabled": False if terminal_config_matches else payload["enabled"],
                "terminal_config_payload_hash": (terminal_config_payload_hash if terminal_config_matches else None),
            }
            status = "updated" if _source_material_changed(existing, effective_payload) else "duplicate"
        if status == "duplicate":
            row = dict(existing)
            return {**row, "status": status}

        cursor = self.conn.execute(
            """
            INSERT INTO news_sources (
              source_id, provider_type, feed_url, source_domain, source_name, source_role,
              trust_tier, managed_by_config, enabled, refresh_interval_seconds,
              coverage_tags_json, asset_universe_json, authority_scope_json, fetch_policy_json,
              cost_policy_json, config_payload_hash, terminal_config_payload_hash,
              created_at_ms, updated_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, %s, %s)
            ON CONFLICT (source_id) DO UPDATE SET
              provider_type = EXCLUDED.provider_type,
              feed_url = EXCLUDED.feed_url,
              source_domain = EXCLUDED.source_domain,
              source_name = EXCLUDED.source_name,
              source_role = EXCLUDED.source_role,
              trust_tier = EXCLUDED.trust_tier,
              managed_by_config = EXCLUDED.managed_by_config,
              enabled = CASE
                WHEN news_sources.terminal_config_payload_hash = EXCLUDED.config_payload_hash THEN false
                ELSE EXCLUDED.enabled
              END,
              refresh_interval_seconds = EXCLUDED.refresh_interval_seconds,
              coverage_tags_json = EXCLUDED.coverage_tags_json,
              asset_universe_json = EXCLUDED.asset_universe_json,
              authority_scope_json = EXCLUDED.authority_scope_json,
              fetch_policy_json = EXCLUDED.fetch_policy_json,
              cost_policy_json = EXCLUDED.cost_policy_json,
              config_payload_hash = EXCLUDED.config_payload_hash,
              terminal_config_payload_hash = CASE
                WHEN news_sources.terminal_config_payload_hash = EXCLUDED.config_payload_hash
                  THEN news_sources.terminal_config_payload_hash
                ELSE NULL
              END,
              consecutive_failures = CASE
                WHEN news_sources.terminal_config_payload_hash IS NOT NULL
                 AND news_sources.terminal_config_payload_hash IS DISTINCT FROM EXCLUDED.config_payload_hash
                  THEN 0
                ELSE news_sources.consecutive_failures
              END,
              last_error = CASE
                WHEN news_sources.terminal_config_payload_hash IS NOT NULL
                 AND news_sources.terminal_config_payload_hash IS DISTINCT FROM EXCLUDED.config_payload_hash
                  THEN NULL
                ELSE news_sources.last_error
              END,
              next_fetch_after_ms = CASE
                WHEN news_sources.terminal_config_payload_hash IS NOT NULL
                 AND news_sources.terminal_config_payload_hash IS DISTINCT FROM EXCLUDED.config_payload_hash
                  THEN 0
                ELSE news_sources.next_fetch_after_ms
              END,
              source_quality_status = CASE
                WHEN news_sources.terminal_config_payload_hash IS NOT NULL
                 AND news_sources.terminal_config_payload_hash IS DISTINCT FROM EXCLUDED.config_payload_hash
                  THEN 'unknown'
                ELSE news_sources.source_quality_status
              END,
              updated_at_ms = EXCLUDED.updated_at_ms
            RETURNING *
            """,
            (
                payload["source_id"],
                payload["provider_type"],
                payload["feed_url"],
                payload["source_domain"],
                payload["source_name"],
                payload["source_role"],
                payload["trust_tier"],
                payload["managed_by_config"],
                payload["enabled"],
                payload["refresh_interval_seconds"],
                _json(payload["coverage_tags_json"]),
                _json(payload["asset_universe_json"]),
                _json(payload["authority_scope_json"]),
                _json(payload["fetch_policy_json"]),
                _json(payload["cost_policy_json"]),
                config_payload_hash,
                int(now_ms),
                int(now_ms),
            ),
        )
        row = cursor.fetchone()
        returned_row = _required_returning_row(cursor, row)
        return {**returned_row, "status": status}

    def reconcile_configured_sources(
        self,
        sources: Iterable[NewsSourceConfig | Mapping[str, Any]],
        *,
        now_ms: int,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        configured_source_ids: list[str] = []
        for source in sources:
            payload = _source_payload(source)
            configured_source_ids.append(str(payload["source_id"]))
            rows.append(self.upsert_source(**payload, now_ms=now_ms))
        rows.extend(
            self.disable_unconfigured_source_rows(
                configured_source_ids=configured_source_ids,
                now_ms=now_ms,
            )
        )
        return rows

    def _disable_unconfigured_source_rows(
        self,
        *,
        configured_source_ids: Sequence[str] | None = None,
        active_source_ids: Sequence[str] | None = None,
        now_ms: int,
    ) -> tuple[list[dict[str, Any]], int]:
        source_ids = configured_source_ids if configured_source_ids is not None else active_source_ids
        normalized_ids = [str(source_id) for source_id in (source_ids or [])]
        cursor = self.conn.execute(
            """
            UPDATE news_sources
               SET enabled = false,
                   updated_at_ms = %s
             WHERE managed_by_config = true
               AND enabled = true
               AND NOT (source_id = ANY(%s::text[]))
            RETURNING *
            """,
            (int(now_ms), normalized_ids),
        )
        rows = cursor.fetchall()
        disabled_count = expect_mutation_count(
            cursor,
            expected=len(rows),
            error_code="news_repository_rowcount_invalid",
        )
        return [{**dict(row), "status": "disabled"} for row in rows], disabled_count

    def disable_unconfigured_source_rows(
        self,
        *,
        configured_source_ids: Sequence[str] | None = None,
        active_source_ids: Sequence[str] | None = None,
        now_ms: int,
    ) -> list[dict[str, Any]]:
        rows, _disabled_count = self._disable_unconfigured_source_rows(
            configured_source_ids=configured_source_ids,
            active_source_ids=active_source_ids,
            now_ms=now_ms,
        )
        return rows

    def disable_unconfigured_sources(
        self,
        *,
        configured_source_ids: Sequence[str] | None = None,
        active_source_ids: Sequence[str] | None = None,
        now_ms: int,
    ) -> int:
        _disabled_rows, disabled_count = self._disable_unconfigured_source_rows(
            configured_source_ids=configured_source_ids,
            active_source_ids=active_source_ids,
            now_ms=now_ms,
        )
        return disabled_count

    def disable_source(
        self,
        *,
        source_id: str,
        error: str,
        now_ms: int,
    ) -> dict[str, Any]:
        cursor = self.conn.execute(
            """
            UPDATE news_sources
               SET enabled = false,
                   last_error = %s,
                   source_quality_status = 'poor',
                   terminal_config_payload_hash = config_payload_hash,
                   updated_at_ms = %s
             WHERE source_id = %s
            RETURNING *
            """,
            (_compact_error(error), int(now_ms), source_id),
        )
        row = cursor.fetchone()
        return _required_returning_row(cursor, row)

    def list_news_item_ids_for_sources(self, *, source_ids: Sequence[str]) -> list[str]:
        normalized_ids = list(dict.fromkeys(str(source_id) for source_id in source_ids if str(source_id)))
        if not normalized_ids:
            return []
        rows = self.conn.execute(
            """
            SELECT DISTINCT edges.news_item_id
              FROM news_item_observation_edges AS edges
             WHERE edges.source_id = ANY(%s::text[])
             ORDER BY edges.news_item_id ASC
            """,
            (normalized_ids,),
        ).fetchall()
        return [str(row["news_item_id"]) for row in rows]

    def list_news_item_source_watermarks_for_sources(self, *, source_ids: Sequence[str]) -> list[dict[str, Any]]:
        normalized_ids = list(dict.fromkeys(str(source_id) for source_id in source_ids if str(source_id)))
        if not normalized_ids:
            return []
        rows = self.conn.execute(
            """
            SELECT DISTINCT
                   edges.news_item_id,
                   GREATEST(
                     COALESCE(NULLIF(items.published_at_ms, 0), 0),
                     COALESCE(NULLIF(items.fetched_at_ms, 0), 0)
                   )::bigint AS source_watermark_ms
              FROM news_item_observation_edges AS edges
              JOIN news_items AS items ON items.news_item_id = edges.news_item_id
             WHERE edges.source_id = ANY(%s::text[])
             ORDER BY edges.news_item_id ASC
            """,
            (normalized_ids,),
        ).fetchall()
        return [
            {
                "news_item_id": str(row["news_item_id"]),
                "source_watermark_ms": _required_positive_news_item_source_watermark(row),
            }
            for row in rows
        ]

    def list_news_item_source_watermarks(self, *, news_item_ids: Sequence[str]) -> list[dict[str, Any]]:
        normalized_ids = list(dict.fromkeys(str(news_item_id) for news_item_id in news_item_ids if str(news_item_id)))
        if not normalized_ids:
            return []
        rows = self.conn.execute(
            """
            SELECT items.news_item_id,
                   GREATEST(
                     COALESCE(NULLIF(items.published_at_ms, 0), 0),
                     COALESCE(NULLIF(items.fetched_at_ms, 0), 0)
                   )::bigint AS source_watermark_ms
              FROM news_items AS items
             WHERE items.news_item_id = ANY(%s::text[])
             ORDER BY items.news_item_id ASC
            """,
            (normalized_ids,),
        ).fetchall()
        return [
            {
                "news_item_id": str(row["news_item_id"]),
                "source_watermark_ms": _required_positive_news_item_source_watermark(row),
            }
            for row in rows
        ]

    def list_source_ids_for_news_items(self, *, news_item_ids: Sequence[str]) -> list[str]:
        normalized_ids = list(dict.fromkeys(str(news_item_id) for news_item_id in news_item_ids if str(news_item_id)))
        if not normalized_ids:
            return []
        rows = self.conn.execute(
            """
            SELECT DISTINCT edges.source_id
              FROM news_item_observation_edges AS edges
             WHERE edges.news_item_id = ANY(%s::text[])
             ORDER BY source_id ASC
            """,
            (normalized_ids,),
        ).fetchall()
        return [str(row["source_id"]) for row in rows]

    def claim_due_sources(
        self,
        *,
        now_ms: int,
        limit: int,
        claim_lease_ms: int,
    ) -> list[dict[str, Any]]:
        parsed_limit = require_nonnegative_int(
            limit,
            error_code="news_source_claim_limit_required",
        )
        parsed_claim_lease_ms = require_positive_int(
            claim_lease_ms,
            error_code="news_source_claim_lease_ms_required",
        )
        cursor = self.conn.execute(
            """
            WITH due AS (
              SELECT source_id
                FROM news_sources
               WHERE enabled = true
                 AND next_fetch_after_ms <= %s
               ORDER BY next_fetch_after_ms ASC, source_id ASC
               LIMIT %s
               FOR UPDATE SKIP LOCKED
            )
            UPDATE news_sources AS sources
               SET next_fetch_after_ms = %s,
                   updated_at_ms = %s
              FROM due
             WHERE sources.source_id = due.source_id
            RETURNING sources.*
            """,
            (
                int(now_ms),
                parsed_limit,
                int(now_ms) + parsed_claim_lease_ms,
                int(now_ms),
            ),
        )
        rows = cursor.fetchall()
        expect_mutation_count(cursor, expected=len(rows), error_code="news_repository_rowcount_invalid")
        return [dict(row) for row in rows]

    def start_fetch_run(self, *, source_id: str, started_at_ms: int) -> str:
        fetch_run_id = f"news-fetch-run-{uuid.uuid4().hex}"
        cursor = self.conn.execute(
            """
            INSERT INTO news_fetch_runs (fetch_run_id, source_id, started_at_ms, status)
            VALUES (%s, %s, %s, 'running')
            """,
            (fetch_run_id, source_id, int(started_at_ms)),
        )
        expect_mutation_count(cursor, expected=1, error_code="news_repository_rowcount_invalid")
        cursor = self.conn.execute(
            """
            UPDATE news_sources
               SET last_fetch_at_ms = %s,
                   updated_at_ms = %s
             WHERE source_id = %s
            """,
            (int(started_at_ms), int(started_at_ms), source_id),
        )
        expect_mutation_count(cursor, expected=1, error_code="news_repository_rowcount_invalid")
        return fetch_run_id

    def prune_successful_fetch_runs(self, *, cutoff_ms: int, limit: int) -> int:
        cursor = self.conn.execute(
            """
            WITH expired_fetch_runs AS (
              SELECT fetch_run_id
              FROM news_fetch_runs
              WHERE status = 'success'
                AND finished_at_ms < %s
              ORDER BY finished_at_ms ASC, fetch_run_id ASC
              LIMIT %s
              FOR UPDATE SKIP LOCKED
            )
            DELETE FROM news_fetch_runs AS runs
            USING expired_fetch_runs AS expired
            WHERE runs.fetch_run_id = expired.fetch_run_id
            """,
            (cutoff_ms, limit),
        )
        count = mutation_count(cursor, error_code="news_repository_rowcount_invalid")
        if count > limit:
            raise TypeError("news_repository_rowcount_invalid")
        return count

    def finish_fetch_run(
        self,
        *,
        fetch_run_id: str,
        source_id: str,
        status: str,
        finished_at_ms: int,
        fetched_count: int | None = None,
        inserted_count: int | None = None,
        updated_count: int | None = None,
        duplicate_count: int | None = None,
        items_seen: int | None = None,
        items_inserted: int | None = None,
        items_updated: int | None = None,
        http_status: int | None = None,
        error: str | None = None,
        extra_json: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        finished = _required_fetch_run_finished_at_ms(finished_at_ms)
        finished_status = _required_fetch_run_completion_status(status)
        fetched = _required_fetch_run_count("fetched_count", fetched_count, items_seen)
        inserted = _required_fetch_run_count("inserted_count", inserted_count, items_inserted)
        updated = _required_fetch_run_count("updated_count", updated_count, items_updated)
        duplicates = _required_fetch_run_count("duplicate_count", duplicate_count)
        response_status = _optional_fetch_run_http_status(http_status)
        extra_payload = _optional_fetch_run_extra_json(extra_json)
        cursor = self.conn.execute(
            """
            UPDATE news_fetch_runs
               SET finished_at_ms = %s,
                   status = %s,
                   fetched_count = %s,
                   inserted_count = %s,
                   updated_count = %s,
                   duplicate_count = %s,
                   http_status = %s,
                   error = %s,
                   extra_json = %s
             WHERE fetch_run_id = %s
            RETURNING *
            """,
            (
                finished,
                finished_status,
                fetched,
                inserted,
                updated,
                duplicates,
                response_status,
                _compact_error(error),
                _json(extra_payload),
                fetch_run_id,
            ),
        )
        row = cursor.fetchone()
        returned_row = _required_returning_row(cursor, row)
        if finished_status == "success":
            source_cursor = self.conn.execute(
                """
                UPDATE news_sources
                   SET last_success_at_ms = %s,
                       next_fetch_after_ms = %s + refresh_interval_seconds * 1000,
                       consecutive_failures = 0,
                       last_error = NULL,
                       source_quality_status = 'healthy',
                       updated_at_ms = %s
                 WHERE source_id = %s
                """,
                (finished, finished, finished, source_id),
            )
        else:
            source_cursor = self.conn.execute(
                """
                UPDATE news_sources
                   SET consecutive_failures = consecutive_failures + 1,
                       last_error = %s,
                       next_fetch_after_ms = %s + refresh_interval_seconds * 1000,
                       source_quality_status = 'degraded',
                       updated_at_ms = %s
                 WHERE source_id = %s
                """,
                (_compact_error(error), finished, finished, source_id),
            )
        expect_mutation_count(source_cursor, expected=1, error_code="news_repository_rowcount_invalid")
        return returned_row

    def update_source_http_cache(
        self,
        *,
        source_id: str,
        etag: str | None,
        last_modified: str | None,
        now_ms: int,
    ) -> None:
        self.conn.execute(
            """
            UPDATE news_sources
               SET etag = COALESCE(%s, etag),
                   last_modified = COALESCE(%s, last_modified),
                   updated_at_ms = %s
             WHERE source_id = %s
            """,
            (
                str(etag) if etag else None,
                str(last_modified) if last_modified else None,
                int(now_ms),
                source_id,
            ),
        )

    def source_sync_cursor(self, source_id: str) -> dict[str, Any]:
        row = self.conn.execute(
            """
            SELECT sync_cursor_json, sync_high_watermark_ms, sync_overlap_ms, sync_diagnostics_json
              FROM news_sources
             WHERE source_id = %s
            """,
            (str(source_id),),
        ).fetchone()
        if row is None:
            return {}
        cursor = _json_dict(row["sync_cursor_json"])
        cursor["high_watermark_ms"] = _required_source_sync_cursor_nonnegative_int(row, "sync_high_watermark_ms")
        cursor["overlap_ms"] = _required_source_sync_cursor_nonnegative_int(row, "sync_overlap_ms")
        diagnostics = _json_dict(row["sync_diagnostics_json"])
        if diagnostics:
            cursor["diagnostics"] = diagnostics
        return cursor

    def update_source_sync_state(
        self,
        source_id: str,
        next_cursor: Mapping[str, Any],
        *,
        now_ms: int,
    ) -> None:
        cursor = _json_dict(next_cursor)
        diagnostics = {
            key: cursor[key]
            for key in ("pages_scanned", "rest_received", "oldest_seen_ms", "stop_reason")
            if key in cursor
        }
        self.conn.execute(
            """
            UPDATE news_sources
               SET sync_cursor_json = %s,
                   sync_high_watermark_ms = COALESCE(%s, sync_high_watermark_ms),
                   sync_overlap_ms = COALESCE(%s, sync_overlap_ms),
                   sync_diagnostics_json = %s,
                   updated_at_ms = %s
             WHERE source_id = %s
            """,
            (
                _json(cursor),
                _positive_optional_int(cursor.get("high_watermark_ms")),
                _positive_optional_int(cursor.get("overlap_ms")),
                _json(diagnostics),
                int(now_ms),
                str(source_id),
            ),
        )

    def upsert_provider_item(
        self,
        *,
        source_id: str,
        fetch_run_id: str,
        source_item_key: str,
        canonical_url: str,
        payload_hash: str,
        raw_payload: Mapping[str, Any],
        provider_article_id: str | None = None,
        provider_article_key: str | None = None,
        provider_payload_status: str | None = None,
        provider_published_at_ms: int | None = None,
        provider_observed_at_ms: int | None = None,
        fetched_at_ms: int,
    ) -> dict[str, Any]:
        payload = dict(raw_payload)
        source = self.conn.execute(
            """
            SELECT provider_type
              FROM news_sources
             WHERE source_id = %s
            """,
            (source_id,),
        ).fetchone()
        if source is None:
            raise ValueError(f"news source does not exist: {source_id}")
        provider_type = str(source["provider_type"]).strip().lower()
        incoming_article_id = _provider_article_id(
            explicit=provider_article_id,
            explicit_key=provider_article_key,
            provider_type=provider_type,
            payload=payload,
        )
        incoming_article_key = provider_global_article_key(
            provider_type=provider_type,
            provider_article_id=incoming_article_id,
        )
        existing = self.conn.execute(
            """
            SELECT provider_items.*, sources.provider_type
              FROM news_provider_items AS provider_items
              JOIN news_sources AS sources ON sources.source_id = provider_items.source_id
             WHERE provider_items.source_id = %s
               AND (
                 provider_items.source_item_key = %s
                 OR (%s <> '' AND provider_items.provider_article_key = %s)
               )
             ORDER BY
               CASE WHEN provider_items.source_item_key = %s THEN 0 ELSE 1 END,
               provider_items.provider_observed_at_ms DESC,
               provider_items.provider_item_id ASC
             LIMIT 1
            """,
            (source_id, source_item_key, incoming_article_key, incoming_article_key, source_item_key),
        ).fetchone()
        stored_source_item_key = str(existing["source_item_key"]) if existing is not None else str(source_item_key)
        existing_article_id = str(existing["provider_article_id"] or "") if existing is not None else ""
        existing_article_key = str(existing["provider_article_key"] or "") if existing is not None else ""
        if incoming_article_key:
            normalized_article_id = incoming_article_id
            normalized_article_key = incoming_article_key
        elif provider_type in PROVIDER_GLOBAL_ARTICLE_ID_TYPES and existing_article_key:
            normalized_article_id = existing_article_id or _provider_article_id_from_global_key(
                provider_type=provider_type,
                provider_article_key=existing_article_key,
            )
            normalized_article_key = existing_article_key
        else:
            normalized_article_id = ""
            normalized_article_key = ""
        incoming_payload_status = _provider_payload_status(
            explicit=provider_payload_status,
            payload=payload,
        )
        normalized_payload_status = _merge_provider_payload_status(
            existing=str(existing["provider_payload_status"] or "") if existing is not None else "",
            incoming=incoming_payload_status,
        )
        incoming_published_at_ms = (
            int(provider_published_at_ms)
            if provider_published_at_ms is not None
            else _provider_published_at_ms(payload)
        )
        normalized_published_at_ms = (
            incoming_published_at_ms
            if incoming_published_at_ms is not None
            else (
                int(existing["provider_published_at_ms"])
                if existing is not None and existing["provider_published_at_ms"] is not None
                else None
            )
        )
        normalized_observed_at_ms = int(
            provider_observed_at_ms if provider_observed_at_ms is not None else fetched_at_ms
        )
        keep_existing_payload = (
            existing is not None
            and str(existing["provider_payload_status"] or "").strip().lower() == "ready"
            and incoming_payload_status != "ready"
        )
        stored_canonical_url = str(existing["canonical_url"]) if keep_existing_payload else str(canonical_url)
        stored_payload_hash = str(existing["payload_hash"]) if keep_existing_payload else str(payload_hash)
        stored_payload = dict(existing["raw_payload_json"]) if keep_existing_payload else payload
        stored_fetched_at_ms = int(existing["fetched_at_ms"]) if keep_existing_payload else int(fetched_at_ms)
        status = "inserted"
        if existing is not None:
            status = "duplicate"
            material_changed = (
                existing["payload_hash"] != stored_payload_hash
                or existing["canonical_url"] != stored_canonical_url
                or dict(existing["raw_payload_json"]) != stored_payload
                or existing["provider_article_id"] != normalized_article_id
                or existing["provider_article_key"] != normalized_article_key
                or existing["provider_payload_status"] != normalized_payload_status
                or existing["provider_published_at_ms"] != normalized_published_at_ms
            )
            if not material_changed:
                return {
                    **dict(existing),
                    "status": "duplicate",
                    "incoming_provider_payload_status": incoming_payload_status,
                }
            if material_changed:
                status = "updated"
        provider_item_id = (
            str(existing["provider_item_id"]) if existing is not None else f"news-provider-item-{uuid.uuid4().hex}"
        )
        cursor = self.conn.execute(
            """
            INSERT INTO news_provider_items (
              provider_item_id, source_id, fetch_run_id, source_item_key, canonical_url,
              payload_hash, raw_payload_json, fetched_at_ms, provider_article_id,
              provider_article_key, provider_payload_status, provider_published_at_ms,
              provider_observed_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (source_id, source_item_key) DO UPDATE SET
              fetch_run_id = EXCLUDED.fetch_run_id,
              canonical_url = CASE
                WHEN news_provider_items.provider_payload_status = 'ready'
                 AND EXCLUDED.provider_payload_status <> 'ready'
                  THEN news_provider_items.canonical_url
                ELSE EXCLUDED.canonical_url
              END,
              payload_hash = CASE
                WHEN news_provider_items.provider_payload_status = 'ready'
                 AND EXCLUDED.provider_payload_status <> 'ready'
                  THEN news_provider_items.payload_hash
                ELSE EXCLUDED.payload_hash
              END,
              raw_payload_json = CASE
                WHEN news_provider_items.provider_payload_status = 'ready'
                 AND EXCLUDED.provider_payload_status <> 'ready'
                  THEN news_provider_items.raw_payload_json
                ELSE EXCLUDED.raw_payload_json
              END,
              fetched_at_ms = CASE
                WHEN news_provider_items.provider_payload_status = 'ready'
                 AND EXCLUDED.provider_payload_status <> 'ready'
                  THEN news_provider_items.fetched_at_ms
                ELSE EXCLUDED.fetched_at_ms
              END,
              provider_article_id = EXCLUDED.provider_article_id,
              provider_article_key = EXCLUDED.provider_article_key,
              provider_payload_status = CASE
                WHEN news_provider_items.provider_payload_status = 'ready'
                  OR EXCLUDED.provider_payload_status = 'ready'
                  THEN 'ready'
                ELSE 'partial'
              END,
              provider_published_at_ms = EXCLUDED.provider_published_at_ms,
              provider_observed_at_ms = EXCLUDED.provider_observed_at_ms
            RETURNING *
            """,
            (
                provider_item_id,
                source_id,
                fetch_run_id,
                stored_source_item_key,
                stored_canonical_url,
                stored_payload_hash,
                _json(stored_payload),
                stored_fetched_at_ms,
                normalized_article_id,
                normalized_article_key,
                incoming_payload_status,
                normalized_published_at_ms,
                normalized_observed_at_ms,
            ),
        )
        row = cursor.fetchone()
        returned_row = _required_returning_row(cursor, row)
        return {**returned_row, "status": status, "incoming_provider_payload_status": incoming_payload_status}

    def list_source_status(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            WITH edge_item_aggregate AS (
              SELECT edges.source_id,
                     COUNT(DISTINCT edges.news_item_id)::int AS canonical_item_count,
                     COUNT(*)::int AS observation_edge_count,
                     MAX(items.published_at_ms) AS latest_item_published_at_ms,
                     MAX(items.fetched_at_ms) AS latest_item_fetched_at_ms
                FROM news_item_observation_edges AS edges
                JOIN news_items AS items ON items.news_item_id = edges.news_item_id
               GROUP BY edges.source_id
            ),
            provider_item_aggregate AS (
              SELECT provider_items.source_id,
                     COUNT(*)::int AS raw_observation_count
                FROM news_provider_items AS provider_items
               GROUP BY provider_items.source_id
            ),
            page_row_aggregate AS (
              SELECT edges.source_id,
                     COUNT(DISTINCT rows.row_id)::int AS serving_row_count
                FROM news_item_observation_edges AS edges
                JOIN news_page_rows AS rows ON rows.news_item_id = edges.news_item_id
               WHERE rows.projection_version = %(projection_version)s
               GROUP BY edges.source_id
            ),
            latest_fetch_run AS MATERIALIZED (
              SELECT sources.source_id,
                     latest.latest_fetch_run_json
                FROM news_sources AS sources
                LEFT JOIN LATERAL (
                  SELECT jsonb_build_object(
                           'status', fetch_runs.status,
                           'started_at_ms', fetch_runs.started_at_ms,
                           'finished_at_ms', fetch_runs.finished_at_ms,
                           'http_status', fetch_runs.http_status,
                           'fetched_count', fetch_runs.fetched_count,
                           'inserted_count', fetch_runs.inserted_count,
                           'updated_count', fetch_runs.updated_count,
                           'duplicate_count', fetch_runs.duplicate_count,
                           'error', fetch_runs.error
                         ) AS latest_fetch_run_json
                    FROM news_fetch_runs AS fetch_runs
                   WHERE fetch_runs.source_id = sources.source_id
                   ORDER BY fetch_runs.started_at_ms DESC, fetch_runs.fetch_run_id DESC
                   LIMIT 1
                ) AS latest ON TRUE
            )
            SELECT sources.*,
                   COALESCE(edge_item_aggregate.canonical_item_count, 0)::int AS item_count,
                   edge_item_aggregate.latest_item_published_at_ms,
                   edge_item_aggregate.latest_item_fetched_at_ms,
                   latest_fetch_run.latest_fetch_run_json,
                   jsonb_build_object(
                     'raw_observation_count',
                       COALESCE(provider_item_aggregate.raw_observation_count, 0)::int,
                     'canonical_item_count',
                       COALESCE(edge_item_aggregate.canonical_item_count, 0)::int,
                     'observation_edge_count',
                       COALESCE(edge_item_aggregate.observation_edge_count, 0)::int,
                     'enabled_serving_row_count',
                       CASE
                         WHEN sources.enabled THEN COALESCE(page_row_aggregate.serving_row_count, 0)::int
                         ELSE 0
                       END,
                     'disabled_serving_row_count',
                       CASE
                         WHEN sources.enabled THEN 0
                         ELSE COALESCE(page_row_aggregate.serving_row_count, 0)::int
                       END
                   ) AS dedup_diagnostics_json
              FROM news_sources AS sources
              LEFT JOIN edge_item_aggregate ON edge_item_aggregate.source_id = sources.source_id
              LEFT JOIN provider_item_aggregate ON provider_item_aggregate.source_id = sources.source_id
              LEFT JOIN page_row_aggregate ON page_row_aggregate.source_id = sources.source_id
              LEFT JOIN latest_fetch_run ON latest_fetch_run.source_id = sources.source_id
             ORDER BY sources.enabled DESC, sources.source_domain ASC, sources.source_id ASC
            """,
            {"projection_version": NEWS_PAGE_PROJECTION_VERSION},
        ).fetchall()
        return [_source_status_payload(row) for row in rows]
