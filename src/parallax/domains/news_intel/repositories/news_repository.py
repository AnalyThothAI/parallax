from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from psycopg.types.json import Jsonb

from parallax.domains.news_intel.services.news_canonical_identity import (
    CANONICAL_POLICY_VERSION,
    CanonicalIdentity,
    canonical_identity_for_observation,
)
from parallax.domains.news_intel.services.news_canonical_identity import (
    provider_article_key as canonical_provider_article_key,
)
from parallax.domains.news_intel.services.news_url_identity import url_identity_kind
from parallax.domains.news_intel.types import NewsSourceConfig
from parallax.domains.news_intel.types.source_classification import normalize_string_tuple
from parallax.domains.news_intel.types.source_quality_policy import window_ms_for_label
from parallax.platform.db.json_safety import postgres_safe_json

_DEFAULT_SOURCE_CLAIM_LEASE_MS = 60_000
_REDACTED = "<redacted>"
_SECRET_ERROR_KEYS = (
    "api[_-]?key",
    "access[_-]?token",
    "refresh[_-]?token",
    "bearer[_-]?token",
    "token",
    "secret",
    "authorization",
    "cookie",
    "key",
    "password",
    "passphrase",
)
_SECRET_ERROR_KEY_PATTERN = "|".join(_SECRET_ERROR_KEYS)
_SECRET_QUERY_RE = re.compile(
    rf"([?&](?:{_SECRET_ERROR_KEY_PATTERN})=)"
    r"[^&#\s]+",
    re.IGNORECASE,
)
_SECRET_KEY_VALUE_RE = re.compile(
    rf"((?<![A-Za-z0-9_])(?:{_SECRET_ERROR_KEY_PATTERN})\s*[:=]\s*)([\"']?)[^\"'\s,;}}&]+([\"']?)",
    re.IGNORECASE,
)
_SECRET_QUOTED_KEY_VALUE_RE = re.compile(
    rf"((?<![A-Za-z0-9_])(?:{_SECRET_ERROR_KEY_PATTERN})\s*[:=]\s*)([\"']).*?\2",
    re.IGNORECASE,
)
_SECRET_HEADER_RE = re.compile(r"\b(authorization|cookie)\s*:\s*[^\r\n]+", re.IGNORECASE)
_BEARER_RE = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE)
_URL_USERINFO_RE = re.compile(r"([a-z][a-z0-9+.-]*://)[^/@\s]+@", re.IGNORECASE)
_CHECK_QUOTED_VALUE_RE = re.compile(r"'((?:''|[^'])*)'(?:\s*::\s*[A-Za-z_][A-Za-z0-9_]*)?")
_PUBLICATION_METADATA_FIELDS = {"computed_at_ms", "updated_at_ms", "projected_at_ms", "payload_hash"}


class NewsRepository:
    def __init__(self, conn: Any):
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
        context_policy: Mapping[str, Any] | None = None,
        cost_policy: Mapping[str, Any] | None = None,
        now_ms: int,
        commit: bool = True,
    ) -> dict[str, Any]:
        existing = self.conn.execute(
            "SELECT * FROM news_sources WHERE source_id = %s",
            (str(source_id),),
        ).fetchone()
        payload = {
            "source_id": str(source_id),
            "provider_type": str(provider_type),
            "feed_url": str(feed_url),
            "source_domain": str(source_domain),
            "source_name": str(source_name),
            "source_role": str(source_role),
            "trust_tier": str(trust_tier),
            "managed_by_config": bool(managed_by_config),
            "enabled": bool(enabled),
            "refresh_interval_seconds": max(1, int(refresh_interval_seconds)),
            "coverage_tags_json": list(normalize_string_tuple(coverage_tags)),
            "asset_universe_json": list(normalize_string_tuple(asset_universe)),
            "authority_scope_json": _json_dict(authority_scope),
            "fetch_policy_json": _json_dict(fetch_policy),
            "context_policy_json": _json_dict(context_policy),
            "cost_policy_json": _json_dict(cost_policy),
        }
        status = "inserted"
        if existing is not None:
            status = "updated" if _source_material_changed(existing, payload) else "duplicate"
        if status == "duplicate":
            row = dict(existing)
            if commit:
                self.conn.commit()
            return {**row, "status": status}

        row = self.conn.execute(
            """
            INSERT INTO news_sources (
              source_id, provider_type, feed_url, source_domain, source_name, source_role,
              trust_tier, managed_by_config, enabled, refresh_interval_seconds,
              coverage_tags_json, asset_universe_json, authority_scope_json, fetch_policy_json,
              context_policy_json, cost_policy_json, created_at_ms, updated_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (source_id) DO UPDATE SET
              provider_type = EXCLUDED.provider_type,
              feed_url = EXCLUDED.feed_url,
              source_domain = EXCLUDED.source_domain,
              source_name = EXCLUDED.source_name,
              source_role = EXCLUDED.source_role,
              trust_tier = EXCLUDED.trust_tier,
              managed_by_config = EXCLUDED.managed_by_config,
              enabled = EXCLUDED.enabled,
              refresh_interval_seconds = EXCLUDED.refresh_interval_seconds,
              coverage_tags_json = EXCLUDED.coverage_tags_json,
              asset_universe_json = EXCLUDED.asset_universe_json,
              authority_scope_json = EXCLUDED.authority_scope_json,
              fetch_policy_json = EXCLUDED.fetch_policy_json,
              context_policy_json = EXCLUDED.context_policy_json,
              cost_policy_json = EXCLUDED.cost_policy_json,
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
                _json(payload["context_policy_json"]),
                _json(payload["cost_policy_json"]),
                int(now_ms),
                int(now_ms),
            ),
        ).fetchone()
        if commit:
            self.conn.commit()
        return {**dict(row), "status": status}

    def reconcile_configured_sources(
        self,
        sources: Iterable[NewsSourceConfig | Mapping[str, Any]],
        *,
        now_ms: int,
        commit: bool = True,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        configured_source_ids: list[str] = []
        for source in sources:
            payload = _source_payload(source)
            configured_source_ids.append(str(payload["source_id"]))
            rows.append(self.upsert_source(**payload, now_ms=now_ms, commit=False))
        rows.extend(
            self.disable_unconfigured_source_rows(
                configured_source_ids=configured_source_ids,
                now_ms=now_ms,
                commit=False,
            )
        )
        if commit:
            self.conn.commit()
        return rows

    def disable_unconfigured_source_rows(
        self,
        *,
        configured_source_ids: Sequence[str] | None = None,
        active_source_ids: Sequence[str] | None = None,
        now_ms: int,
        commit: bool = True,
    ) -> list[dict[str, Any]]:
        source_ids = configured_source_ids if configured_source_ids is not None else active_source_ids
        normalized_ids = [str(source_id) for source_id in (source_ids or [])]
        rows = self.conn.execute(
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
        ).fetchall()
        if commit:
            self.conn.commit()
        return [{**dict(row), "status": "disabled"} for row in rows]

    def disable_unconfigured_sources(
        self,
        *,
        configured_source_ids: Sequence[str] | None = None,
        active_source_ids: Sequence[str] | None = None,
        now_ms: int,
        commit: bool = True,
    ) -> int:
        rows = self.disable_unconfigured_source_rows(
            configured_source_ids=configured_source_ids,
            active_source_ids=active_source_ids,
            now_ms=now_ms,
            commit=False,
        )
        if commit:
            self.conn.commit()
        return len(rows)

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

    def list_news_item_ids_for_canonical_rebuild(self, *, limit: int) -> list[str]:
        rows = self.conn.execute(
            """
            SELECT news_item_id
              FROM news_items
             ORDER BY updated_at_ms DESC, news_item_id ASC
             LIMIT %s
            """,
            (max(0, int(limit)),),
        ).fetchall()
        return [str(row["news_item_id"]) for row in rows]

    def claim_due_sources(
        self,
        *,
        now_ms: int,
        limit: int,
        claim_lease_ms: int = _DEFAULT_SOURCE_CLAIM_LEASE_MS,
        commit: bool = True,
    ) -> list[dict[str, Any]]:
        rows = self.conn.execute(
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
                max(0, int(limit)),
                int(now_ms) + max(1, int(claim_lease_ms)),
                int(now_ms),
            ),
        ).fetchall()
        if commit:
            self.conn.commit()
        return [dict(row) for row in rows]

    def start_fetch_run(self, *, source_id: str, started_at_ms: int, commit: bool = True) -> str:
        fetch_run_id = f"news-fetch-run-{uuid.uuid4().hex}"
        self.conn.execute(
            """
            INSERT INTO news_fetch_runs (fetch_run_id, source_id, started_at_ms, status)
            VALUES (%s, %s, %s, 'running')
            """,
            (fetch_run_id, source_id, int(started_at_ms)),
        )
        self.conn.execute(
            """
            UPDATE news_sources
               SET last_fetch_at_ms = %s,
                   updated_at_ms = %s
             WHERE source_id = %s
            """,
            (int(started_at_ms), int(started_at_ms), source_id),
        )
        if commit:
            self.conn.commit()
        return fetch_run_id

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
        commit: bool = True,
    ) -> dict[str, Any]:
        fetched = _first_int(fetched_count, items_seen)
        inserted = _first_int(inserted_count, items_inserted)
        updated = _first_int(updated_count, items_updated)
        duplicates = _first_int(duplicate_count)
        row = self.conn.execute(
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
                int(finished_at_ms),
                status,
                fetched,
                inserted,
                updated,
                duplicates,
                int(http_status) if http_status is not None else None,
                _compact_error(error),
                _json(dict(extra_json or {})),
                fetch_run_id,
            ),
        ).fetchone()
        if status == "success":
            self.conn.execute(
                """
                UPDATE news_sources
                   SET last_success_at_ms = %s,
                       next_fetch_after_ms = %s + refresh_interval_seconds * 1000,
                       consecutive_failures = 0,
                       last_error = NULL,
                       updated_at_ms = %s
                 WHERE source_id = %s
                """,
                (int(finished_at_ms), int(finished_at_ms), int(finished_at_ms), source_id),
            )
        else:
            self.conn.execute(
                """
                UPDATE news_sources
                   SET consecutive_failures = consecutive_failures + 1,
                       last_error = %s,
                       next_fetch_after_ms = %s + refresh_interval_seconds * 1000,
                       updated_at_ms = %s
                 WHERE source_id = %s
                """,
                (_compact_error(error), int(finished_at_ms), int(finished_at_ms), source_id),
            )
        if commit:
            self.conn.commit()
        return dict(row)

    def update_source_http_cache(
        self,
        *,
        source_id: str,
        etag: str | None,
        last_modified: str | None,
        now_ms: int,
        commit: bool = True,
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
        if commit:
            self.conn.commit()

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
        cursor["high_watermark_ms"] = int(row["sync_high_watermark_ms"] or 0)
        cursor["overlap_ms"] = int(row["sync_overlap_ms"] or 0)
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
        commit: bool = True,
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
        if commit:
            self.conn.commit()

    def upsert_provider_item(
        self,
        *,
        source_id: str,
        fetch_run_id: str,
        source_item_key: str,
        canonical_url: str,
        payload_hash: str,
        raw_payload: Mapping[str, Any] | None = None,
        raw_payload_json: Mapping[str, Any] | None = None,
        provider_article_id: str | None = None,
        provider_article_key: str | None = None,
        provider_payload_status: str | None = None,
        provider_published_at_ms: int | None = None,
        provider_observed_at_ms: int | None = None,
        fetched_at_ms: int,
        commit: bool = True,
    ) -> dict[str, Any]:
        payload = dict(raw_payload if raw_payload is not None else raw_payload_json or {})
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
            provider_type=provider_type,
            source_item_key=source_item_key,
            payload=payload,
        )
        incoming_article_key = str(provider_article_key or "").strip() or canonical_provider_article_key(
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
        existing_article_id = str(existing["provider_article_id"] or "").strip() if existing is not None else ""
        normalized_article_id = existing_article_id or incoming_article_id
        existing_article_key = str(existing["provider_article_key"] or "").strip() if existing is not None else ""
        normalized_article_key = existing_article_key or (
            canonical_provider_article_key(provider_type=provider_type, provider_article_id=existing_article_id)
            if existing_article_id
            else incoming_article_key
        )
        if normalized_article_id and not normalized_article_key:
            normalized_article_key = canonical_provider_article_key(
                provider_type=provider_type,
                provider_article_id=normalized_article_id,
            )
        incoming_payload_status = _provider_payload_status(
            explicit=provider_payload_status,
            payload=payload,
        )
        normalized_payload_status = _merge_provider_payload_status(
            existing=str(existing["provider_payload_status"] or "") if existing is not None else "",
            incoming=incoming_payload_status,
        )
        normalized_published_at_ms = (
            int(provider_published_at_ms)
            if provider_published_at_ms is not None
            else _provider_published_at_ms(payload)
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
            if (
                existing["payload_hash"] != stored_payload_hash
                or existing["canonical_url"] != stored_canonical_url
                or dict(existing["raw_payload_json"]) != stored_payload
                or existing["fetched_at_ms"] != stored_fetched_at_ms
                or existing["provider_article_id"] != normalized_article_id
                or existing["provider_article_key"] != normalized_article_key
                or existing["provider_payload_status"] != normalized_payload_status
                or existing["provider_published_at_ms"] != normalized_published_at_ms
                or existing["provider_observed_at_ms"] != normalized_observed_at_ms
            ):
                status = "updated"
        provider_item_id = (
            str(existing["provider_item_id"]) if existing is not None else f"news-provider-item-{uuid.uuid4().hex}"
        )
        row = self.conn.execute(
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
              provider_article_id = COALESCE(
                NULLIF(news_provider_items.provider_article_id, ''),
                EXCLUDED.provider_article_id
              ),
              provider_article_key = COALESCE(
                NULLIF(news_provider_items.provider_article_key, ''),
                EXCLUDED.provider_article_key
              ),
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
        ).fetchone()
        if commit:
            self.conn.commit()
        return {**dict(row), "status": status, "incoming_provider_payload_status": incoming_payload_status}

    def upsert_canonical_news_item(
        self,
        *,
        provider_item_id: str,
        canonical_identity: CanonicalIdentity | None = None,
        canonical_url: str,
        title: str,
        summary: str = "",
        body_text: str = "",
        language: str = "en",
        published_at_ms: int | None = None,
        fetched_at_ms: int,
        content_hash: str,
        title_fingerprint: str,
        now_ms: int,
        provider_signal: Mapping[str, Any] | None = None,
        provider_token_impacts: Sequence[Mapping[str, Any]] | None = None,
        provider_payload_status: str | None = None,
        commit: bool = True,
    ) -> dict[str, Any]:
        item_published_at_ms = int(published_at_ms if published_at_ms is not None else fetched_at_ms)
        provider_signal_payload = dict(provider_signal or {})
        provider_token_impacts_payload = [dict(item) for item in provider_token_impacts or []]
        observation = self.conn.execute(
            """
            SELECT provider_items.*, sources.provider_type, sources.source_domain
              FROM news_provider_items AS provider_items
              JOIN news_sources AS sources ON sources.source_id = provider_items.source_id
             WHERE provider_items.provider_item_id = %s
            """,
            (provider_item_id,),
        ).fetchone()
        if observation is None:
            raise ValueError(f"news provider item does not exist: {provider_item_id}")
        observation_source_id = str(observation["source_id"])
        observation_source_domain = str(observation["source_domain"])
        computed_identity = canonical_identity_for_observation(
            provider_type=str(observation["provider_type"]),
            source_id=observation_source_id,
            provider_article_id=str(observation["provider_article_id"] or ""),
            canonical_url=canonical_url,
            content_hash=content_hash,
            title_fingerprint=title_fingerprint,
            published_at_ms=item_published_at_ms,
        )
        identity = canonical_identity if canonical_identity is not None else computed_identity
        if (
            computed_identity.dedup_key_kind == "canonical_url"
            and identity.canonical_item_key != computed_identity.canonical_item_key
        ):
            identity = computed_identity
        provider_article_key = str(observation["provider_article_key"] or "")
        observation_payload_status = str(observation["provider_payload_status"] or "").strip().lower()
        incoming_payload_status = str(provider_payload_status or "").strip().lower()
        effective_payload_status = (
            incoming_payload_status if incoming_payload_status in {"partial", "ready"} else observation_payload_status
        )
        ready_content_identity = identity.dedup_key_kind == "content_hash" and effective_payload_status == "ready"
        hard_url_identity = identity.dedup_key_kind == "canonical_url"
        promotes_provider_article_identity = hard_url_identity or ready_content_identity
        if provider_article_key:
            existing_provider_article_item = self.conn.execute(
                """
                SELECT items.news_item_id,
                       items.provider_item_id,
                       items.source_id,
                       items.canonical_item_key,
                       items.dedup_key_kind,
                       items.dedup_key_confidence,
                       items.url_identity_kind,
                       provider_items.provider_payload_status
                  FROM news_item_observation_edges AS edges
                  JOIN news_items AS items ON items.news_item_id = edges.news_item_id
                  JOIN news_provider_items AS provider_items ON provider_items.provider_item_id = items.provider_item_id
                 WHERE edges.provider_article_key = %s
                 ORDER BY
                   CASE
                     WHEN items.dedup_key_kind = 'content_hash'
                      AND items.url_identity_kind = 'article'
                      AND provider_items.provider_payload_status = 'ready'
                       THEN 0
                     ELSE 1
                   END,
                   edges.provider_article_key ASC,
                   items.source_id ASC,
                   items.provider_item_id ASC
                 LIMIT 1
                """,
                (provider_article_key,),
            ).fetchone()
            reuse_provider_article_item = (
                existing_provider_article_item is not None
                and str(existing_provider_article_item["canonical_item_key"] or "")
                and str(existing_provider_article_item["canonical_item_key"]) != identity.canonical_item_key
            )
            if reuse_provider_article_item and promotes_provider_article_identity:
                if hard_url_identity:
                    reuse_provider_article_item = False
                else:
                    existing_ready_content_identity = (
                        str(existing_provider_article_item["dedup_key_kind"] or "") == "content_hash"
                        and str(existing_provider_article_item["url_identity_kind"] or "") == "article"
                        and str(existing_provider_article_item["provider_payload_status"] or "") == "ready"
                    )
                    same_provider_item = str(existing_provider_article_item["provider_item_id"] or "") == str(
                        provider_item_id
                    )
                    if same_provider_item:
                        reuse_provider_article_item = False
                    elif existing_ready_content_identity:
                        existing_tie_breaker = (
                            provider_article_key,
                            str(existing_provider_article_item["source_id"] or ""),
                            str(existing_provider_article_item["provider_item_id"] or ""),
                        )
                        incoming_tie_breaker = (provider_article_key, observation_source_id, str(provider_item_id))
                        reuse_provider_article_item = existing_tie_breaker <= incoming_tie_breaker
                    else:
                        reuse_provider_article_item = False
            if reuse_provider_article_item and existing_provider_article_item is not None:
                identity = CanonicalIdentity(
                    canonical_item_key=str(existing_provider_article_item["canonical_item_key"]),
                    news_item_id=str(existing_provider_article_item["news_item_id"]),
                    dedup_key_kind=str(existing_provider_article_item["dedup_key_kind"] or identity.dedup_key_kind),
                    dedup_key_confidence=str(
                        existing_provider_article_item["dedup_key_confidence"] or identity.dedup_key_confidence
                    ),
                    url_identity_kind=str(
                        existing_provider_article_item["url_identity_kind"] or identity.url_identity_kind
                    ),
                    match_type="same_provider_article_id",
                    match_confidence="strong",
                    evidence={
                        **dict(identity.evidence),
                        "provider_article_key": provider_article_key,
                        "provider_article_id": str(observation["provider_article_id"] or ""),
                        "provider_article_existing_news_item_id": str(existing_provider_article_item["news_item_id"]),
                    },
                )
        self.conn.execute(
            """
            SELECT pg_advisory_xact_lock(
              ('x' || substr(md5(%s), 1, 16))::bit(64)::bigint
            )
            """,
            (identity.canonical_item_key,),
        )
        item_payload = {
            "provider_item_id": str(provider_item_id),
            "source_id": observation_source_id,
            "source_domain": observation_source_domain,
            "canonical_url": str(canonical_url),
            "title": str(title),
            "summary": str(summary),
            "body_text": str(body_text),
            "language": str(language),
            "published_at_ms": item_published_at_ms,
            "fetched_at_ms": int(fetched_at_ms),
            "content_hash": str(content_hash),
            "title_fingerprint": str(title_fingerprint),
            "provider_signal_json": provider_signal_payload,
            "provider_token_impacts_json": provider_token_impacts_payload,
        }
        existing = self.conn.execute(
            "SELECT * FROM news_items WHERE canonical_item_key = %s",
            (identity.canonical_item_key,),
        ).fetchone()
        existing_representative_provider = None
        if existing is not None:
            existing_representative_provider = self.conn.execute(
                """
                SELECT provider_article_key, provider_payload_status
                  FROM news_provider_items
                 WHERE provider_item_id = %s
                """,
                (str(existing["provider_item_id"]),),
            ).fetchone()
        existing_representative = (
            {
                **dict(existing),
                "provider_payload_status": (
                    str(existing_representative_provider["provider_payload_status"] or "")
                    if existing_representative_provider is not None
                    else ""
                ),
                "provider_article_key": (
                    str(existing_representative_provider["provider_article_key"] or "")
                    if existing_representative_provider is not None
                    else ""
                ),
            }
            if existing is not None
            else None
        )
        incoming_representative = {
            **item_payload,
            "provider_payload_status": str(observation["provider_payload_status"] or ""),
            "provider_article_key": str(observation["provider_article_key"] or ""),
        }
        replace_representative = existing is None or _representative_payload_should_replace(
            existing_representative or {},
            incoming_representative,
        )
        content_changed = (
            existing is not None and replace_representative and _news_item_content_changed(existing, item_payload)
        )
        item_id = str(existing["news_item_id"]) if existing is not None else identity.news_item_id
        existing_edge = self.conn.execute(
            "SELECT * FROM news_item_observation_edges WHERE provider_item_id = %s",
            (provider_item_id,),
        ).fetchone()
        previous_edge_news_item_id = (
            str(existing_edge["news_item_id"])
            if existing_edge is not None and str(existing_edge["news_item_id"]) != item_id
            else None
        )
        row = self.conn.execute(
            """
            INSERT INTO news_items (
              news_item_id, provider_item_id, source_id, source_domain, canonical_url,
              title, summary, body_text, language, published_at_ms, fetched_at_ms,
              content_hash, title_fingerprint, provider_signal_json, provider_token_impacts_json,
              canonical_item_key, dedup_key_kind, dedup_key_confidence, url_identity_kind,
              canonical_policy_version, created_at_ms, updated_at_ms
            )
            VALUES (
              %(item_id)s, %(provider_item_id)s, %(source_id)s, %(source_domain)s,
              %(canonical_url)s, %(title)s, %(summary)s, %(body_text)s, %(language)s,
              %(published_at_ms)s, %(fetched_at_ms)s, %(content_hash)s,
              %(title_fingerprint)s, %(provider_signal_json)s, %(provider_token_impacts_json)s,
              %(canonical_item_key)s, %(dedup_key_kind)s, %(dedup_key_confidence)s,
              %(url_identity_kind)s, %(canonical_policy_version)s, %(created_at_ms)s,
              %(updated_at_ms)s
            )
            ON CONFLICT (canonical_item_key) WHERE canonical_item_key <> '' DO UPDATE SET
              provider_item_id = CASE
                WHEN %(replace_representative)s THEN EXCLUDED.provider_item_id
                ELSE news_items.provider_item_id
              END,
              source_id = CASE
                WHEN %(replace_representative)s THEN EXCLUDED.source_id
                ELSE news_items.source_id
              END,
              source_domain = CASE
                WHEN %(replace_representative)s THEN EXCLUDED.source_domain
                ELSE news_items.source_domain
              END,
              canonical_url = CASE
                WHEN %(replace_representative)s THEN EXCLUDED.canonical_url
                ELSE news_items.canonical_url
              END,
              title = CASE
                WHEN %(replace_representative)s THEN EXCLUDED.title
                ELSE news_items.title
              END,
              summary = CASE
                WHEN %(replace_representative)s THEN EXCLUDED.summary
                ELSE news_items.summary
              END,
              body_text = CASE
                WHEN %(replace_representative)s THEN EXCLUDED.body_text
                ELSE news_items.body_text
              END,
              language = CASE
                WHEN %(replace_representative)s THEN EXCLUDED.language
                ELSE news_items.language
              END,
              published_at_ms = CASE
                WHEN %(replace_representative)s THEN EXCLUDED.published_at_ms
                ELSE news_items.published_at_ms
              END,
              fetched_at_ms = CASE
                WHEN %(replace_representative)s THEN EXCLUDED.fetched_at_ms
                ELSE news_items.fetched_at_ms
              END,
              content_hash = CASE
                WHEN %(replace_representative)s THEN EXCLUDED.content_hash
                ELSE news_items.content_hash
              END,
              title_fingerprint = CASE
                WHEN %(replace_representative)s THEN EXCLUDED.title_fingerprint
                ELSE news_items.title_fingerprint
              END,
              provider_signal_json = CASE
                WHEN %(replace_representative)s THEN EXCLUDED.provider_signal_json
                ELSE news_items.provider_signal_json
              END,
              provider_token_impacts_json = CASE
                WHEN %(replace_representative)s THEN EXCLUDED.provider_token_impacts_json
                ELSE news_items.provider_token_impacts_json
              END,
              dedup_key_kind = EXCLUDED.dedup_key_kind,
              dedup_key_confidence = EXCLUDED.dedup_key_confidence,
              url_identity_kind = CASE
                WHEN %(replace_representative)s THEN EXCLUDED.url_identity_kind
                ELSE news_items.url_identity_kind
              END,
              canonical_policy_version = EXCLUDED.canonical_policy_version,
              lifecycle_status = CASE
                WHEN NOT %(replace_representative)s THEN news_items.lifecycle_status
                WHEN news_items.content_hash = EXCLUDED.content_hash THEN news_items.lifecycle_status
                ELSE 'raw'
              END,
              updated_at_ms = EXCLUDED.updated_at_ms
            RETURNING *
            """,
            {
                "item_id": item_id,
                "provider_item_id": item_payload["provider_item_id"],
                "source_id": item_payload["source_id"],
                "source_domain": item_payload["source_domain"],
                "canonical_url": item_payload["canonical_url"],
                "title": item_payload["title"],
                "summary": item_payload["summary"],
                "body_text": item_payload["body_text"],
                "language": item_payload["language"],
                "published_at_ms": item_published_at_ms,
                "fetched_at_ms": int(fetched_at_ms),
                "content_hash": item_payload["content_hash"],
                "title_fingerprint": item_payload["title_fingerprint"],
                "provider_signal_json": _json(provider_signal_payload),
                "provider_token_impacts_json": _json(provider_token_impacts_payload),
                "canonical_item_key": identity.canonical_item_key,
                "dedup_key_kind": identity.dedup_key_kind,
                "dedup_key_confidence": identity.dedup_key_confidence,
                "url_identity_kind": identity.url_identity_kind,
                "canonical_policy_version": CANONICAL_POLICY_VERSION,
                "created_at_ms": int(now_ms),
                "updated_at_ms": int(now_ms),
                "replace_representative": replace_representative,
            },
        ).fetchone()
        edge_evidence = {
            **dict(identity.evidence),
            "item_payload": {
                "canonical_url": item_payload["canonical_url"],
                "title": item_payload["title"],
                "summary": item_payload["summary"],
                "body_text": item_payload["body_text"],
                "language": item_payload["language"],
                "published_at_ms": item_payload["published_at_ms"],
                "fetched_at_ms": item_payload["fetched_at_ms"],
                "content_hash": item_payload["content_hash"],
                "title_fingerprint": item_payload["title_fingerprint"],
                "provider_signal_json": provider_signal_payload,
                "provider_token_impacts_json": provider_token_impacts_payload,
                "url_identity_kind": identity.url_identity_kind,
            },
        }
        edge_payload = {
            "news_item_id": str(row["news_item_id"]),
            "source_id": observation_source_id,
            "provider_article_key": str(observation["provider_article_key"] or ""),
            "match_type": identity.match_type,
            "match_confidence": identity.match_confidence,
            "policy_version": CANONICAL_POLICY_VERSION,
            "evidence_json": edge_evidence,
        }
        self.conn.execute(
            """
            INSERT INTO news_item_observation_edges (
              provider_item_id, news_item_id, source_id, provider_article_key, match_type,
              match_confidence, policy_version, evidence_json, first_seen_at_ms, last_seen_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (provider_item_id) DO UPDATE SET
              news_item_id = EXCLUDED.news_item_id,
              source_id = EXCLUDED.source_id,
              provider_article_key = EXCLUDED.provider_article_key,
              match_type = EXCLUDED.match_type,
              match_confidence = EXCLUDED.match_confidence,
              policy_version = EXCLUDED.policy_version,
              evidence_json = EXCLUDED.evidence_json,
              last_seen_at_ms = EXCLUDED.last_seen_at_ms
            """,
            (
                provider_item_id,
                edge_payload["news_item_id"],
                edge_payload["source_id"],
                edge_payload["provider_article_key"],
                edge_payload["match_type"],
                edge_payload["match_confidence"],
                edge_payload["policy_version"],
                _json(edge_payload["evidence_json"]),
                int(now_ms),
                int(now_ms),
            ),
        )
        provider_article_remapped_old_item_ids: list[str] = []
        if provider_article_key and promotes_provider_article_identity:
            provider_article_remapped_old_item_ids = self._remap_provider_article_edges_to_news_item(
                provider_article_key=provider_article_key,
                news_item_id=str(row["news_item_id"]),
                now_ms=now_ms,
                remap_reason="hard_canonical_url" if hard_url_identity else "ready_content_hash",
            )
        row = self._refresh_news_item_observation_summary(news_item_id=str(row["news_item_id"]), now_ms=now_ms)
        aggregate_changed = existing is not None and _news_item_aggregate_changed(existing, row)
        edge_changed = (
            existing_edge is None
            or _news_item_edge_changed(
                existing_edge,
                edge_payload,
            )
            or bool(provider_article_remapped_old_item_ids)
        )
        remapped_edge = previous_edge_news_item_id is not None
        affected_news_item_ids = [str(row["news_item_id"])]
        old_news_item_ids = list(
            dict.fromkeys(
                [
                    item_id
                    for item_id in [previous_edge_news_item_id, *provider_article_remapped_old_item_ids]
                    if item_id
                ]
            )
        )
        if old_news_item_ids:
            remapped_edge = True
        for old_news_item_id in old_news_item_ids:
            affected_news_item_ids.append(old_news_item_id)
            self._refresh_news_item_observation_summary(
                news_item_id=old_news_item_id,
                now_ms=now_ms,
            )
            deleted_old_item = self._delete_zero_edge_news_item(news_item_id=old_news_item_id)
            if not deleted_old_item:
                self._reselect_news_item_representative_from_edges(
                    news_item_id=old_news_item_id,
                    now_ms=now_ms,
                )
                self._clear_item_scoped_derived_facts(news_item_id=old_news_item_id)
        if existing is None and not remapped_edge:
            status = "inserted"
        elif content_changed or aggregate_changed or edge_changed or remapped_edge:
            status = "updated"
        else:
            status = "duplicate"
        if content_changed:
            self._clear_item_scoped_derived_facts(news_item_id=item_id)
        if commit:
            self.conn.commit()
        return {
            **dict(row),
            "status": status,
            "affected_news_item_ids": list(dict.fromkeys(affected_news_item_ids)),
        }

    def _remap_provider_article_edges_to_news_item(
        self,
        *,
        provider_article_key: str,
        news_item_id: str,
        now_ms: int,
        remap_reason: str = "ready_content_hash",
    ) -> list[str]:
        rows = self.conn.execute(
            """
            WITH remapped AS (
              SELECT provider_item_id, news_item_id AS old_news_item_id
                FROM news_item_observation_edges
               WHERE provider_article_key = %s
                 AND news_item_id <> %s
            ),
            updated AS (
              UPDATE news_item_observation_edges AS edges
                 SET news_item_id = %s,
                     match_type = 'same_provider_article_id',
                     match_confidence = 'strong',
                     policy_version = %s,
                     evidence_json = edges.evidence_json || jsonb_build_object(
                       'provider_article_remap_reason', %s::text,
                       'provider_article_remapped_to_news_item_id', %s::text,
                       'provider_article_remapped_at_ms', %s::bigint
                     ),
                     last_seen_at_ms = %s
                FROM remapped
               WHERE edges.provider_item_id = remapped.provider_item_id
               RETURNING remapped.old_news_item_id
            )
            SELECT DISTINCT old_news_item_id
              FROM updated
            """,
            (
                str(provider_article_key),
                str(news_item_id),
                str(news_item_id),
                CANONICAL_POLICY_VERSION,
                str(remap_reason),
                str(news_item_id),
                int(now_ms),
                int(now_ms),
            ),
        ).fetchall()
        return [str(row["old_news_item_id"]) for row in rows]

    def _refresh_news_item_observation_summary(self, *, news_item_id: str, now_ms: int) -> dict[str, Any]:
        row = self.conn.execute(
            """
            WITH edge_summary AS (
              SELECT
                edges.news_item_id,
                COUNT(*)::int AS duplicate_observation_count,
                COALESCE(jsonb_agg(DISTINCT edges.source_id ORDER BY edges.source_id), '[]'::jsonb) AS source_ids_json,
                COALESCE(
                  jsonb_agg(DISTINCT sources.source_domain ORDER BY sources.source_domain),
                  '[]'::jsonb
                ) AS source_domains_json,
                COALESCE(
                  jsonb_agg(DISTINCT edges.provider_article_key ORDER BY edges.provider_article_key)
                    FILTER (WHERE edges.provider_article_key <> ''),
                  '[]'::jsonb
                ) AS provider_article_keys_json
              FROM news_item_observation_edges AS edges
              JOIN news_sources AS sources ON sources.source_id = edges.source_id
             WHERE edges.news_item_id = %s
             GROUP BY edges.news_item_id
            )
            UPDATE news_items AS items
               SET duplicate_observation_count = edge_summary.duplicate_observation_count,
                   source_ids_json = edge_summary.source_ids_json,
                   source_domains_json = edge_summary.source_domains_json,
                   provider_article_keys_json = edge_summary.provider_article_keys_json,
                   updated_at_ms = %s
              FROM edge_summary
             WHERE items.news_item_id = edge_summary.news_item_id
            RETURNING items.*
            """,
            (news_item_id, int(now_ms)),
        ).fetchone()
        if row is not None:
            return dict(row)
        fallback = self.conn.execute(
            "SELECT * FROM news_items WHERE news_item_id = %s",
            (news_item_id,),
        ).fetchone()
        return dict(fallback) if fallback is not None else {}

    def _delete_zero_edge_news_item(self, *, news_item_id: str) -> bool:
        row = self.conn.execute(
            """
            DELETE FROM news_items AS items
             WHERE items.news_item_id = %s
               AND NOT EXISTS (
                 SELECT 1
                   FROM news_item_observation_edges AS edges
                  WHERE edges.news_item_id = items.news_item_id
               )
            RETURNING items.news_item_id
            """,
            (news_item_id,),
        ).fetchone()
        return row is not None

    def _clear_item_scoped_derived_facts(self, *, news_item_id: str) -> None:
        self.conn.execute("DELETE FROM news_fact_candidates WHERE news_item_id = %s", (news_item_id,))
        self.conn.execute("DELETE FROM news_token_mentions WHERE news_item_id = %s", (news_item_id,))
        self.conn.execute("DELETE FROM news_item_entities WHERE news_item_id = %s", (news_item_id,))

    def _reselect_news_item_representative_from_edges(self, *, news_item_id: str, now_ms: int) -> dict[str, Any]:
        row = self.conn.execute(
            """
            WITH representative_edge AS (
              SELECT
                edges.provider_item_id,
                edges.source_id,
                sources.source_domain,
                provider_items.canonical_url AS provider_canonical_url,
                edges.evidence_json #> '{item_payload}' AS item_payload
              FROM news_item_observation_edges AS edges
              JOIN news_provider_items AS provider_items
                ON provider_items.provider_item_id = edges.provider_item_id
              JOIN news_sources AS sources ON sources.source_id = edges.source_id
             WHERE edges.news_item_id = %s
             ORDER BY
               CASE WHEN provider_items.provider_payload_status = 'ready' THEN 0 ELSE 1 END,
               CASE
                 WHEN edges.evidence_json #>> '{item_payload,url_identity_kind}' = 'article' THEN 0
                 WHEN provider_items.canonical_url ~* '^https?://' THEN 1
                 ELSE 2
               END,
               edges.provider_article_key ASC,
               edges.source_id ASC,
               provider_items.payload_hash ASC,
               edges.provider_item_id ASC
             LIMIT 1
            )
            UPDATE news_items AS items
               SET provider_item_id = representative_edge.provider_item_id,
                   source_id = representative_edge.source_id,
                   source_domain = representative_edge.source_domain,
                   canonical_url = COALESCE(
                     NULLIF(representative_edge.item_payload ->> 'canonical_url', ''),
                     representative_edge.provider_canonical_url
                   ),
                   title = COALESCE(NULLIF(representative_edge.item_payload ->> 'title', ''), items.title),
                   summary = COALESCE(representative_edge.item_payload ->> 'summary', items.summary),
                   body_text = COALESCE(representative_edge.item_payload ->> 'body_text', items.body_text),
                   language = COALESCE(NULLIF(representative_edge.item_payload ->> 'language', ''), items.language),
                   published_at_ms = COALESCE(
                     CASE
                       WHEN representative_edge.item_payload ->> 'published_at_ms' ~ '^[0-9]+$'
                         THEN (representative_edge.item_payload ->> 'published_at_ms')::bigint
                       ELSE NULL
                     END,
                     items.published_at_ms
                   ),
                   fetched_at_ms = COALESCE(
                     CASE
                       WHEN representative_edge.item_payload ->> 'fetched_at_ms' ~ '^[0-9]+$'
                         THEN (representative_edge.item_payload ->> 'fetched_at_ms')::bigint
                       ELSE NULL
                     END,
                     items.fetched_at_ms
                   ),
                   content_hash = COALESCE(
                     NULLIF(representative_edge.item_payload ->> 'content_hash', ''),
                     items.content_hash
                   ),
                   title_fingerprint = COALESCE(
                     NULLIF(representative_edge.item_payload ->> 'title_fingerprint', ''),
                     items.title_fingerprint
                   ),
                   provider_signal_json = COALESCE(
                     representative_edge.item_payload -> 'provider_signal_json',
                     '{}'::jsonb
                   ),
                   provider_token_impacts_json = COALESCE(
                     representative_edge.item_payload -> 'provider_token_impacts_json',
                     '[]'::jsonb
                   ),
                   url_identity_kind = COALESCE(
                     NULLIF(representative_edge.item_payload ->> 'url_identity_kind', ''),
                     items.url_identity_kind
                   ),
                   lifecycle_status = 'raw',
                   updated_at_ms = %s
              FROM representative_edge
             WHERE items.news_item_id = %s
            RETURNING items.*
            """,
            (news_item_id, int(now_ms), news_item_id),
        ).fetchone()
        return dict(row) if row is not None else {}

    def upsert_news_context_item(
        self,
        *,
        context_item_id: str,
        source_id: str,
        parent_news_item_id: str | None = None,
        provider_item_id: str | None = None,
        context_type: str,
        author: str | None = None,
        canonical_url: str | None = None,
        body_text: str,
        published_at_ms: int | None = None,
        engagement_json: Mapping[str, Any] | None = None,
        raw_payload_json: Mapping[str, Any] | None = None,
        created_at_ms: int,
        commit: bool = True,
    ) -> dict[str, Any]:
        row = self.conn.execute(
            """
            INSERT INTO news_context_items (
              context_item_id, source_id, parent_news_item_id, provider_item_id, context_type,
              author, canonical_url, body_text, published_at_ms, engagement_json,
              raw_payload_json, created_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (context_item_id) DO UPDATE SET
              source_id = EXCLUDED.source_id,
              parent_news_item_id = EXCLUDED.parent_news_item_id,
              provider_item_id = EXCLUDED.provider_item_id,
              context_type = EXCLUDED.context_type,
              author = EXCLUDED.author,
              canonical_url = EXCLUDED.canonical_url,
              body_text = EXCLUDED.body_text,
              published_at_ms = EXCLUDED.published_at_ms,
              engagement_json = EXCLUDED.engagement_json,
              raw_payload_json = EXCLUDED.raw_payload_json,
              created_at_ms = EXCLUDED.created_at_ms
            RETURNING *
            """,
            (
                str(context_item_id),
                str(source_id),
                str(parent_news_item_id) if parent_news_item_id else None,
                str(provider_item_id) if provider_item_id else None,
                str(context_type),
                str(author) if author is not None else None,
                str(canonical_url) if canonical_url is not None else None,
                str(body_text),
                int(published_at_ms) if published_at_ms is not None else None,
                _json(_json_dict(engagement_json)),
                _json(_json_dict(raw_payload_json)),
                int(created_at_ms),
            ),
        ).fetchone()
        if commit:
            self.conn.commit()
        return dict(row)

    def insert_news_item_agent_run(self, **payload: Any) -> dict[str, Any]:
        commit = bool(payload.pop("commit", True))
        row = self.conn.execute(
            """
            INSERT INTO news_item_agent_runs (
              run_id, news_item_id, provider, model, backend, execution_trace_id, workflow_name,
              agent_name, lane, artifact_version_hash, prompt_version, schema_version,
              validator_version, guardrail_version, input_hash, output_hash, execution_started,
              status, outcome, error_class, error, request_json, response_json,
              validation_errors_json, trace_metadata_json, usage_json, latency_ms,
              started_at_ms, finished_at_ms, created_at_ms
            )
            VALUES (
              %(run_id)s, %(news_item_id)s, %(provider)s, %(model)s, %(backend)s, %(execution_trace_id)s,
              %(workflow_name)s, %(agent_name)s, %(lane)s, %(artifact_version_hash)s,
              %(prompt_version)s, %(schema_version)s, %(validator_version)s, %(guardrail_version)s,
              %(input_hash)s, %(output_hash)s, %(execution_started)s, %(status)s, %(outcome)s,
              %(error_class)s, %(error)s, %(request_json)s, %(response_json)s,
              %(validation_errors_json)s, %(trace_metadata_json)s, %(usage_json)s,
              %(latency_ms)s, %(started_at_ms)s, %(finished_at_ms)s, %(created_at_ms)s
            )
            RETURNING *
            """,
            _agent_run_payload(payload),
        ).fetchone()
        if commit:
            self.conn.commit()
        return dict(row)

    def upsert_news_item_agent_brief(self, **payload: Any) -> dict[str, Any]:
        commit = bool(payload.pop("commit", True))
        row = self.conn.execute(
            """
            INSERT INTO news_item_agent_briefs (
              news_item_id, agent_run_id, status, direction, decision_class, brief_json,
              input_hash, artifact_version_hash, prompt_version, schema_version,
              validator_version, computed_at_ms, created_at_ms, updated_at_ms
            )
            VALUES (
              %(news_item_id)s, %(agent_run_id)s, %(status)s, %(direction)s,
              %(decision_class)s, %(brief_json)s, %(input_hash)s, %(artifact_version_hash)s,
              %(prompt_version)s, %(schema_version)s, %(validator_version)s,
              %(computed_at_ms)s, %(created_at_ms)s, %(updated_at_ms)s
            )
            ON CONFLICT (news_item_id) DO UPDATE SET
              agent_run_id = EXCLUDED.agent_run_id,
              status = EXCLUDED.status,
              direction = EXCLUDED.direction,
              decision_class = EXCLUDED.decision_class,
              brief_json = EXCLUDED.brief_json,
              input_hash = EXCLUDED.input_hash,
              artifact_version_hash = EXCLUDED.artifact_version_hash,
              prompt_version = EXCLUDED.prompt_version,
              schema_version = EXCLUDED.schema_version,
              validator_version = EXCLUDED.validator_version,
              computed_at_ms = EXCLUDED.computed_at_ms,
              updated_at_ms = EXCLUDED.updated_at_ms
            RETURNING *
            """,
            _agent_brief_payload(payload),
        ).fetchone()
        if commit:
            self.conn.commit()
        return dict(row)

    def get_news_item_agent_brief(self, news_item_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT *
              FROM news_item_agent_briefs
             WHERE news_item_id = %s
            """,
            (news_item_id,),
        ).fetchone()
        return dict(row) if row is not None else None

    def list_page_source_items(self, *, limit: int, cursor: str | None = None) -> list[dict[str, Any]]:
        return self.list_news_page_rows(limit=limit, cursor=cursor)

    def list_news_page_rows(
        self,
        *,
        limit: int,
        cursor: str | None = None,
        status: str | None = None,
        direction: str | None = None,
        provider_type: str | None = None,
        source_role: str | None = None,
        trust_tier: str | None = None,
        coverage_tag: str | None = None,
        content_class: str | None = None,
        content_tag: str | None = None,
        decision_class: str | None = None,
        signal: str | None = None,
        min_score: int | None = None,
        q: str | None = None,
    ) -> list[dict[str, Any]]:
        return self._list_projected_news_page_rows(
            limit=limit,
            cursor=cursor,
            status=status,
            direction=direction,
            provider_type=provider_type,
            source_role=source_role,
            trust_tier=trust_tier,
            coverage_tag=coverage_tag,
            content_class=content_class,
            content_tag=content_tag,
            decision_class=decision_class,
            signal=signal,
            min_score=min_score,
            q=q,
        )

    def list_news_high_signal_notification_candidates(
        self,
        *,
        min_score: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT
              row_id,
              news_item_id,
              latest_at_ms,
              headline,
              summary,
              source_domain,
              canonical_url,
              duplicate_count,
              source_ids_json AS source_ids,
              source_domains_json AS source_domains,
              signal_json AS signal,
              token_impacts_json AS token_impacts,
              content_class,
              content_tags_json AS content_tags,
              source_json AS source,
              agent_brief_json AS agent_brief,
              agent_status,
              agent_brief_computed_at_ms,
              computed_at_ms,
              projection_version
            FROM news_page_rows
            WHERE COALESCE((signal_json -> 'alert_eligibility' ->> 'eligible')::boolean, false) = true
              AND COALESCE(NULLIF(signal_json -> 'alert_eligibility' ->> 'provider_score', '')::int, -1) >= %s
              AND EXISTS (
                SELECT 1
                  FROM news_item_observation_edges AS edges
                  JOIN news_sources AS sources ON sources.source_id = edges.source_id
                 WHERE edges.news_item_id = news_page_rows.news_item_id
                   AND sources.enabled = true
              )
            ORDER BY
              latest_at_ms DESC,
              agent_brief_computed_at_ms DESC NULLS LAST,
              COALESCE(NULLIF(signal_json -> 'alert_eligibility' ->> 'provider_score', '')::int, -1) DESC,
              row_id DESC
            LIMIT %s
            """,
            (int(min_score), max(0, int(limit))),
        ).fetchall()
        payloads: list[dict[str, Any]] = []
        for row in rows:
            payload = dict(row)
            payload["agent_brief"] = _public_agent_brief_payload(payload.get("agent_brief"))
            payloads.append(payload)
        return payloads

    def _list_projected_news_page_rows(
        self,
        *,
        limit: int,
        cursor: str | None = None,
        status: str | None = None,
        direction: str | None = None,
        provider_type: str | None = None,
        source_role: str | None = None,
        trust_tier: str | None = None,
        coverage_tag: str | None = None,
        content_class: str | None = None,
        content_tag: str | None = None,
        decision_class: str | None = None,
        signal: str | None = None,
        min_score: int | None = None,
        q: str | None = None,
    ) -> list[dict[str, Any]]:
        cursor_time, cursor_id = _decode_page_cursor(cursor)
        filter_sql, filter_params = _news_page_row_filter_sql(
            status=status,
            direction=direction,
            provider_type=provider_type,
            source_role=source_role,
            trust_tier=trust_tier,
            coverage_tag=coverage_tag,
            content_class=content_class,
            content_tag=content_tag,
            decision_class=decision_class,
            signal=signal,
            min_score=min_score,
            q=q,
        )
        rows = self.conn.execute(
            f"""
            SELECT
              row_id,
              news_item_id,
              latest_at_ms,
              lifecycle_status,
              headline,
              summary,
              source_domain,
              canonical_url,
              duplicate_count,
              source_ids_json AS source_ids,
              source_domains_json AS source_domains,
              token_lanes_json AS token_lanes,
              fact_lanes_json AS fact_lanes,
              signal_json AS signal,
              token_impacts_json AS token_impacts,
              content_class,
              content_tags_json AS content_tags,
              content_classification_json AS content_classification,
              source_json AS source,
              agent_brief_json AS agent_brief,
              agent_status,
              agent_brief_computed_at_ms,
              computed_at_ms,
              projection_version
            FROM news_page_rows
            WHERE (
              %s::bigint IS NULL
              OR (latest_at_ms, row_id) < (%s::bigint, %s::text)
            )
              AND EXISTS (
                SELECT 1
                  FROM news_item_observation_edges AS edges
                  JOIN news_sources AS sources ON sources.source_id = edges.source_id
                 WHERE edges.news_item_id = news_page_rows.news_item_id
                   AND sources.enabled = true
              )
            {filter_sql}
            ORDER BY latest_at_ms DESC, row_id DESC
            LIMIT %s
            """,
            (
                cursor_time,
                cursor_time,
                cursor_id,
                *filter_params,
                max(0, int(limit)),
            ),
        ).fetchall()
        payloads: list[dict[str, Any]] = []
        for row in rows:
            payload = dict(row)
            payload["agent_brief"] = _public_agent_brief_payload(payload.get("agent_brief"))
            payloads.append(payload)
        return payloads

    def list_unprocessed_items(self, *, limit: int, now_ms: int, commit: bool = True) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            WITH picked AS (
              SELECT news_item_id
                FROM news_items
               WHERE lifecycle_status IN ('raw', 'process_failed')
                  OR (
                    lifecycle_status = 'processed'
                    AND content_classification_json = '{}'::jsonb
                  )
               ORDER BY published_at_ms ASC, news_item_id ASC
               LIMIT %s
               FOR UPDATE SKIP LOCKED
            ),
            claimed AS (
              UPDATE news_items AS items
                 SET processing_attempts = processing_attempts + 1,
                     updated_at_ms = %s
                FROM picked
               WHERE items.news_item_id = picked.news_item_id
              RETURNING items.*
            )
            SELECT claimed.news_item_id,
                   claimed.provider_item_id,
                   claimed.source_id,
                   sources.source_domain AS source_domain,
                   claimed.canonical_url,
                   claimed.title,
                   claimed.summary,
                   claimed.body_text,
                   claimed.language,
                   claimed.published_at_ms,
                   claimed.fetched_at_ms,
                   claimed.content_hash,
                   claimed.title_fingerprint,
                   claimed.lifecycle_status,
                   claimed.processing_attempts,
                   claimed.processing_error,
                   claimed.processed_at_ms,
                   claimed.content_class,
                   claimed.content_tags_json,
                   claimed.content_classification_json,
                   claimed.provider_signal_json,
                   claimed.provider_token_impacts_json,
                   claimed.created_at_ms,
                   claimed.updated_at_ms,
                   sources.provider_type,
                   sources.source_role,
                   sources.trust_tier,
                   sources.source_name,
                   sources.authority_scope_json
              FROM claimed
              JOIN news_sources AS sources ON sources.source_id = claimed.source_id
            """,
            (max(0, int(limit)), int(now_ms)),
        ).fetchall()
        if commit:
            self.conn.commit()
        return [dict(row) for row in rows]

    def replace_item_entities(
        self,
        *,
        news_item_id: str,
        entities: Sequence[Any],
        commit: bool = True,
    ) -> None:
        self.conn.execute("DELETE FROM news_item_entities WHERE news_item_id = %s", (news_item_id,))
        for entity in entities:
            self.conn.execute(
                """
                INSERT INTO news_item_entities (
                  entity_id, news_item_id, entity_type, raw_value, normalized_value, chain,
                  span_start, span_end, text_surface, confidence, extraction_policy_version, created_at_ms
                )
                VALUES (
                  %(entity_id)s, %(news_item_id)s, %(entity_type)s, %(raw_value)s, %(normalized_value)s,
                  %(chain)s, %(span_start)s, %(span_end)s, %(text_surface)s, %(confidence)s,
                  %(extraction_policy_version)s, %(created_at_ms)s
                )
                ON CONFLICT (entity_id) DO UPDATE SET
                  raw_value = EXCLUDED.raw_value,
                  normalized_value = EXCLUDED.normalized_value,
                  chain = EXCLUDED.chain,
                  span_start = EXCLUDED.span_start,
                  span_end = EXCLUDED.span_end,
                  text_surface = EXCLUDED.text_surface,
                  confidence = EXCLUDED.confidence,
                  extraction_policy_version = EXCLUDED.extraction_policy_version
                """,
                _entity_payload(entity),
            )
        if commit:
            self.conn.commit()

    def replace_token_mentions(
        self,
        *,
        news_item_id: str,
        mentions: Sequence[Any],
        commit: bool = True,
    ) -> None:
        self.conn.execute("DELETE FROM news_token_mentions WHERE news_item_id = %s", (news_item_id,))
        for mention in mentions:
            self.conn.execute(
                """
                INSERT INTO news_token_mentions (
                  mention_id, news_item_id, entity_id, observed_symbol, chain_id, address,
                  resolution_status, target_type, target_id, display_symbol, display_name,
                  reason_codes_json, candidate_targets_json, evidence_strength, confidence, created_at_ms
                )
                VALUES (
                  %(mention_id)s, %(news_item_id)s, %(entity_id)s, %(observed_symbol)s, %(chain_id)s,
                  %(address)s, %(resolution_status)s, %(target_type)s, %(target_id)s, %(display_symbol)s,
                  %(display_name)s, %(reason_codes_json)s, %(candidate_targets_json)s,
                  %(evidence_strength)s, %(confidence)s, %(created_at_ms)s
                )
                ON CONFLICT (mention_id) DO UPDATE SET
                  observed_symbol = EXCLUDED.observed_symbol,
                  chain_id = EXCLUDED.chain_id,
                  address = EXCLUDED.address,
                  resolution_status = EXCLUDED.resolution_status,
                  target_type = EXCLUDED.target_type,
                  target_id = EXCLUDED.target_id,
                  display_symbol = EXCLUDED.display_symbol,
                  display_name = EXCLUDED.display_name,
                  reason_codes_json = EXCLUDED.reason_codes_json,
                  candidate_targets_json = EXCLUDED.candidate_targets_json,
                  evidence_strength = EXCLUDED.evidence_strength,
                  confidence = EXCLUDED.confidence
                """,
                _mention_payload(mention),
            )
        if commit:
            self.conn.commit()

    def replace_fact_candidates(
        self,
        *,
        news_item_id: str,
        candidates: Sequence[Any],
        commit: bool = True,
    ) -> None:
        self.conn.execute("DELETE FROM news_fact_candidates WHERE news_item_id = %s", (news_item_id,))
        for candidate in candidates:
            self.conn.execute(
                """
                INSERT INTO news_fact_candidates (
                  fact_candidate_id, news_item_id, event_type, claim, realis, evidence_quote,
                  evidence_span_start, evidence_span_end, source_role, required_slots_json,
                  affected_targets_json, validation_status, rejection_reasons_json,
                  extraction_method, policy_version, created_at_ms, updated_at_ms
                )
                VALUES (
                  %(fact_candidate_id)s, %(news_item_id)s, %(event_type)s, %(claim)s, %(realis)s,
                  %(evidence_quote)s, %(evidence_span_start)s, %(evidence_span_end)s, %(source_role)s,
                  %(required_slots_json)s, %(affected_targets_json)s, %(validation_status)s,
                  %(rejection_reasons_json)s, %(extraction_method)s, %(policy_version)s,
                  %(created_at_ms)s, %(updated_at_ms)s
                )
                ON CONFLICT (fact_candidate_id) DO UPDATE SET
                  claim = EXCLUDED.claim,
                  realis = EXCLUDED.realis,
                  evidence_quote = EXCLUDED.evidence_quote,
                  evidence_span_start = EXCLUDED.evidence_span_start,
                  evidence_span_end = EXCLUDED.evidence_span_end,
                  required_slots_json = EXCLUDED.required_slots_json,
                  affected_targets_json = EXCLUDED.affected_targets_json,
                  validation_status = EXCLUDED.validation_status,
                  rejection_reasons_json = EXCLUDED.rejection_reasons_json,
                  extraction_method = EXCLUDED.extraction_method,
                  policy_version = EXCLUDED.policy_version,
                  updated_at_ms = EXCLUDED.updated_at_ms
                """,
                _fact_payload(candidate),
            )
        if commit:
            self.conn.commit()

    def mark_item_processed(self, *, news_item_id: str, processed_at_ms: int, commit: bool = True) -> None:
        self.conn.execute(
            """
            UPDATE news_items
               SET lifecycle_status = 'processed',
                   processing_error = NULL,
                   processed_at_ms = %s,
                   updated_at_ms = %s
             WHERE news_item_id = %s
            """,
            (int(processed_at_ms), int(processed_at_ms), news_item_id),
        )
        if commit:
            self.conn.commit()

    def update_item_content_classification(
        self,
        *,
        news_item_id: str,
        content_class: str,
        content_tags: Sequence[str],
        classification_payload: Mapping[str, Any],
        now_ms: int,
        commit: bool = True,
    ) -> None:
        self.conn.execute(
            """
            UPDATE news_items
               SET content_class = %s,
                   content_tags_json = %s,
                   content_classification_json = %s,
                   updated_at_ms = %s
             WHERE news_item_id = %s
            """,
            (
                str(content_class),
                _json([str(tag) for tag in content_tags]),
                _json(_json_dict(classification_payload)),
                int(now_ms),
                str(news_item_id),
            ),
        )
        if commit:
            self.conn.commit()

    def mark_item_process_failed(
        self,
        *,
        news_item_id: str,
        error: str,
        now_ms: int,
        commit: bool = True,
    ) -> None:
        self.conn.execute(
            """
            UPDATE news_items
               SET lifecycle_status = 'process_failed',
                   processing_error = %s,
                   updated_at_ms = %s
             WHERE news_item_id = %s
            """,
            (_compact_error(error), int(now_ms), news_item_id),
        )
        if commit:
            self.conn.commit()

    def load_items_for_page_projection(self, *, news_item_ids: Sequence[str]) -> list[dict[str, Any]]:
        target_ids = list(dict.fromkeys(str(news_item_id) for news_item_id in news_item_ids if str(news_item_id)))
        if not target_ids:
            return []
        rows = self.conn.execute(
            """
            WITH target_items AS (
              SELECT items.*
                FROM news_items AS items
               WHERE items.news_item_id = ANY(%s::text[])
                 AND EXISTS (
                   SELECT 1
                     FROM news_item_observation_edges AS edges
                     JOIN news_sources AS edge_sources ON edge_sources.source_id = edges.source_id
                    WHERE edges.news_item_id = items.news_item_id
                      AND edge_sources.enabled = true
                 )
            )
            SELECT
              to_jsonb(items.*)
                || jsonb_build_object(
                  'source_id', source_rep.source_id,
                  'source_domain', source_rep.source_domain,
                  'provider_type', source_rep.provider_type,
                  'source_name', source_rep.source_name,
                  'source_role', source_rep.source_role,
                  'trust_tier', source_rep.trust_tier,
                  'coverage_tags_json', source_rep.coverage_tags_json,
                  'source_quality_status', source_rep.source_quality_status,
                  'duplicate_observation_count',
                    COALESCE(edge_summary.duplicate_observation_count, items.duplicate_observation_count),
                  'source_ids_json', COALESCE(edge_summary.source_ids_json, items.source_ids_json),
                  'source_domains_json', COALESCE(edge_summary.source_domains_json, items.source_domains_json),
                  'provider_article_keys_json',
                    COALESCE(edge_summary.provider_article_keys_json, items.provider_article_keys_json)
                ) AS item,
              CASE
                WHEN current_brief.news_item_id IS NULL THEN NULL
                ELSE to_jsonb(current_brief.*)
              END AS current_brief,
              COALESCE(mentions.token_mentions, '[]'::jsonb) AS token_mentions,
              COALESCE(facts.fact_candidates, '[]'::jsonb) AS fact_candidates
            FROM target_items AS items
            JOIN LATERAL (
              SELECT edge_sources.*
                FROM news_item_observation_edges AS edges
                JOIN news_sources AS edge_sources ON edge_sources.source_id = edges.source_id
                JOIN news_provider_items AS provider_items ON provider_items.provider_item_id = edges.provider_item_id
               WHERE edges.news_item_id = items.news_item_id
                 AND edge_sources.enabled = true
               ORDER BY
                 CASE WHEN provider_items.provider_payload_status = 'ready' THEN 0 ELSE 1 END,
                 CASE WHEN edges.evidence_json #>> '{item_payload,url_identity_kind}' = 'article' THEN 0 ELSE 1 END,
                 edges.provider_article_key ASC,
                 edge_sources.source_id ASC,
                 provider_items.payload_hash ASC,
                 edges.provider_item_id ASC
               LIMIT 1
            ) AS source_rep ON true
            LEFT JOIN LATERAL (
              SELECT
                COUNT(*)::int AS duplicate_observation_count,
                COALESCE(jsonb_agg(DISTINCT edges.source_id ORDER BY edges.source_id), '[]'::jsonb)
                  AS source_ids_json,
                COALESCE(
                  jsonb_agg(DISTINCT edge_sources.source_domain ORDER BY edge_sources.source_domain),
                  '[]'::jsonb
                ) AS source_domains_json,
                COALESCE(
                  jsonb_agg(DISTINCT edges.provider_article_key ORDER BY edges.provider_article_key)
                    FILTER (WHERE edges.provider_article_key <> ''),
                  '[]'::jsonb
                ) AS provider_article_keys_json
                FROM news_item_observation_edges AS edges
                JOIN news_sources AS edge_sources ON edge_sources.source_id = edges.source_id
               WHERE edges.news_item_id = items.news_item_id
                 AND edge_sources.enabled = true
            ) AS edge_summary ON true
            LEFT JOIN news_item_agent_briefs AS current_brief ON current_brief.news_item_id = items.news_item_id
            LEFT JOIN LATERAL (
              SELECT COALESCE(jsonb_agg(to_jsonb(mentions.*) ORDER BY mentions.mention_id), '[]'::jsonb)
                AS token_mentions
                FROM news_token_mentions AS mentions
               WHERE mentions.news_item_id = items.news_item_id
            ) AS mentions ON true
            LEFT JOIN LATERAL (
              SELECT COALESCE(jsonb_agg(to_jsonb(facts.*) ORDER BY facts.fact_candidate_id), '[]'::jsonb)
                AS fact_candidates
                FROM news_fact_candidates AS facts
               WHERE facts.news_item_id = items.news_item_id
            ) AS facts ON true
            ORDER BY items.published_at_ms DESC, items.news_item_id DESC
            """,
            (target_ids,),
        ).fetchall()
        return [
            {
                "item": _json_dict(row["item"]),
                "current_brief": _json_dict(row["current_brief"]) if row["current_brief"] is not None else None,
                "token_mentions": _json_list(row["token_mentions"]),
                "fact_candidates": _json_list(row["fact_candidates"]),
            }
            for row in rows
        ]

    def load_items_for_brief_targets(self, *, news_item_ids: Sequence[str]) -> list[dict[str, Any]]:
        target_ids = [str(item_id) for item_id in dict.fromkeys(news_item_ids) if str(item_id)]
        if not target_ids:
            return []
        rows = self.conn.execute(
            """
            WITH target_ids(news_item_id, ordinal) AS (
              SELECT news_item_id, ordinal
                FROM unnest(%s::text[]) WITH ORDINALITY AS ids(news_item_id, ordinal)
            ),
            candidates AS (
              SELECT
                items.news_item_id,
                target_ids.ordinal,
                items.published_at_ms,
                GREATEST(
                  COALESCE(items.processed_at_ms, items.created_at_ms, 0),
                  COALESCE(mention_updates.updated_at_ms, 0),
                  COALESCE(fact_updates.updated_at_ms, 0),
                  COALESCE(context_updates.updated_at_ms, 0)
                ) AS source_updated_at_ms
              FROM target_ids
              JOIN news_items AS items ON items.news_item_id = target_ids.news_item_id
              LEFT JOIN LATERAL (
                SELECT MAX(created_at_ms) AS updated_at_ms
                  FROM news_token_mentions
                 WHERE news_item_id = items.news_item_id
              ) AS mention_updates ON true
              LEFT JOIN LATERAL (
                SELECT MAX(updated_at_ms) AS updated_at_ms
                  FROM news_fact_candidates
                 WHERE news_item_id = items.news_item_id
              ) AS fact_updates ON true
              LEFT JOIN LATERAL (
                SELECT MAX(created_at_ms) AS updated_at_ms
                  FROM news_context_items
                 WHERE parent_news_item_id = items.news_item_id
              ) AS context_updates ON true
              WHERE items.lifecycle_status = 'processed'
                AND EXISTS (
                  SELECT 1
                    FROM news_item_observation_edges AS edges
                    JOIN news_sources AS edge_sources ON edge_sources.source_id = edges.source_id
                   WHERE edges.news_item_id = items.news_item_id
                     AND edge_sources.enabled = true
                )
            )
            SELECT
              to_jsonb(items.*)
                || jsonb_build_object(
                  'source_name', sources.source_name,
                  'source_role', sources.source_role,
                  'trust_tier', sources.trust_tier,
                  'duplicate_count', COALESCE(edge_summary.duplicate_count, 1),
                  'source_ids_json', COALESCE(edge_summary.source_ids_json, '[]'::jsonb),
                  'source_domains_json', COALESCE(edge_summary.source_domains_json, '[]'::jsonb),
                  'provider_article_keys_json', COALESCE(edge_summary.provider_article_keys_json, '[]'::jsonb)
                ) AS item,
              CASE
                WHEN current_brief.news_item_id IS NULL THEN NULL
                ELSE to_jsonb(current_brief.*)
              END AS current_brief,
              CASE WHEN latest_run.run_id IS NULL THEN NULL ELSE to_jsonb(latest_run.*) END AS latest_run,
              candidates.source_updated_at_ms,
              COALESCE(token_rows.rows, '[]'::jsonb) AS token_mentions,
              COALESCE(fact_rows.rows, '[]'::jsonb) AS fact_candidates,
              COALESCE(context_rows.rows, '[]'::jsonb) AS context_items
            FROM candidates
            JOIN news_items AS items ON items.news_item_id = candidates.news_item_id
            JOIN news_sources AS sources ON sources.source_id = items.source_id
            LEFT JOIN news_item_agent_briefs AS current_brief ON current_brief.news_item_id = items.news_item_id
            LEFT JOIN LATERAL (
              SELECT COUNT(*)::int AS duplicate_count,
                     COALESCE(jsonb_agg(DISTINCT edges.source_id ORDER BY edges.source_id), '[]'::jsonb)
                       AS source_ids_json,
                     COALESCE(
                       jsonb_agg(DISTINCT edge_sources.source_domain ORDER BY edge_sources.source_domain)
                         FILTER (WHERE edge_sources.source_domain IS NOT NULL),
                       '[]'::jsonb
                     ) AS source_domains_json,
                     COALESCE(
                       jsonb_agg(DISTINCT edges.provider_article_key ORDER BY edges.provider_article_key)
                         FILTER (WHERE edges.provider_article_key <> ''),
                       '[]'::jsonb
                     ) AS provider_article_keys_json
                FROM news_item_observation_edges AS edges
                JOIN news_sources AS edge_sources ON edge_sources.source_id = edges.source_id
               WHERE edges.news_item_id = items.news_item_id
                 AND edge_sources.enabled = true
            ) AS edge_summary ON true
            LEFT JOIN LATERAL (
              SELECT *
                FROM news_item_agent_runs AS runs
               WHERE runs.news_item_id = items.news_item_id
               ORDER BY runs.finished_at_ms DESC, runs.run_id DESC
               LIMIT 1
            ) AS latest_run ON true
            LEFT JOIN LATERAL (
              SELECT jsonb_agg(to_jsonb(mentions.*) ORDER BY mentions.mention_id ASC) AS rows
                FROM news_token_mentions AS mentions
               WHERE mentions.news_item_id = items.news_item_id
            ) AS token_rows ON true
            LEFT JOIN LATERAL (
              SELECT jsonb_agg(to_jsonb(facts.*) ORDER BY facts.fact_candidate_id ASC) AS rows
                FROM news_fact_candidates AS facts
               WHERE facts.news_item_id = items.news_item_id
            ) AS fact_rows ON true
            LEFT JOIN LATERAL (
              SELECT jsonb_agg(
                       to_jsonb(context_items.*)
                       ORDER BY context_items.published_at_ms DESC NULLS LAST,
                                context_items.context_item_id ASC
                     ) AS rows
                FROM (
                  SELECT *
                    FROM news_context_items
                   WHERE parent_news_item_id = items.news_item_id
                   ORDER BY published_at_ms DESC NULLS LAST, context_item_id ASC
                   LIMIT 25
                ) AS context_items
            ) AS context_rows ON true
            ORDER BY candidates.ordinal ASC
            """,
            (target_ids,),
        ).fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            item = _json_dict(row["item"])
            context_items = _json_list(row["context_items"])
            item["context_items"] = context_items
            results.append(
                {
                    "item": item,
                    "token_mentions": _json_list(row["token_mentions"]),
                    "fact_candidates": _json_list(row["fact_candidates"]),
                    "context_items": context_items,
                    "current_brief": _json_dict(row["current_brief"]) if row["current_brief"] is not None else None,
                    "latest_run": _json_dict(row["latest_run"]) if row["latest_run"] is not None else None,
                    "source_updated_at_ms": int(row["source_updated_at_ms"] or 0),
                }
            )
        return results

    def list_context_items_for_news_item(self, news_item_id: str, *, limit: int = 25) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT *
              FROM news_context_items
             WHERE parent_news_item_id = %s
             ORDER BY published_at_ms DESC NULLS LAST, context_item_id ASC
             LIMIT %s
            """,
            (str(news_item_id), max(0, int(limit))),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_news_item_detail(self, *, news_item_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT to_jsonb(items.*) AS item,
                   to_jsonb(sources.*) AS source,
                   to_jsonb(provider_items.*) AS provider_item,
                   CASE
                     WHEN fetch_runs.fetch_run_id IS NULL THEN NULL
                     ELSE to_jsonb(fetch_runs.*)
                   END AS fetch_run,
                   CASE
                     WHEN current_brief.news_item_id IS NULL THEN NULL
                     ELSE to_jsonb(current_brief.*)
                   END AS agent_brief,
                   CASE
                     WHEN latest_run.agent_run IS NULL THEN NULL
                     ELSE latest_run.agent_run
                   END AS agent_run,
                   COALESCE(
                     jsonb_agg(DISTINCT to_jsonb(entities.*))
                       FILTER (WHERE entities.entity_id IS NOT NULL),
                     '[]'::jsonb
                   ) AS entities,
                   COALESCE(
                     jsonb_agg(DISTINCT to_jsonb(mentions.*))
                       FILTER (WHERE mentions.mention_id IS NOT NULL),
                     '[]'::jsonb
                   ) AS token_mentions,
                   COALESCE(
                     jsonb_agg(DISTINCT to_jsonb(facts.*))
                       FILTER (WHERE facts.fact_candidate_id IS NOT NULL),
                     '[]'::jsonb
                   ) AS fact_candidates
              FROM news_items AS items
              JOIN news_sources AS sources ON sources.source_id = items.source_id
              JOIN news_provider_items AS provider_items ON provider_items.provider_item_id = items.provider_item_id
              LEFT JOIN news_fetch_runs AS fetch_runs ON fetch_runs.fetch_run_id = provider_items.fetch_run_id
              LEFT JOIN news_item_agent_briefs AS current_brief ON current_brief.news_item_id = items.news_item_id
              LEFT JOIN LATERAL (
                SELECT jsonb_build_object(
                         'run_id', runs.run_id,
                         'status', runs.status,
                         'outcome', runs.outcome,
                         'execution_started', runs.execution_started,
                         'model', runs.model,
                         'provider', runs.provider,
                         'lane', runs.lane,
                         'execution_trace_id', runs.execution_trace_id,
                         'error_class', runs.error_class,
                         'error', runs.error,
                         'usage_json', runs.usage_json,
                         'trace_metadata_json', runs.trace_metadata_json,
                         'started_at_ms', runs.started_at_ms,
                         'finished_at_ms', runs.finished_at_ms
                       ) AS agent_run
                  FROM news_item_agent_runs AS runs
                 WHERE runs.news_item_id = items.news_item_id
                 ORDER BY runs.finished_at_ms DESC, runs.run_id DESC
                 LIMIT 1
              ) AS latest_run ON true
              LEFT JOIN news_item_entities AS entities ON entities.news_item_id = items.news_item_id
              LEFT JOIN news_token_mentions AS mentions ON mentions.news_item_id = items.news_item_id
              LEFT JOIN news_fact_candidates AS facts ON facts.news_item_id = items.news_item_id
             WHERE items.news_item_id = %s
             GROUP BY items.news_item_id, sources.source_id, provider_items.provider_item_id, fetch_runs.fetch_run_id,
                      current_brief.news_item_id, latest_run.agent_run
            """,
            (news_item_id,),
        ).fetchone()
        if row is None:
            return None
        observation_rows = self.conn.execute(
            """
            SELECT to_jsonb(edges.*)
                     || jsonb_build_object(
                       'source_domain', sources.source_domain,
                       'source_name', sources.source_name,
                       'source_role', sources.source_role,
                       'trust_tier', sources.trust_tier,
                       'enabled', sources.enabled,
                       'provider_payload_status', provider_items.provider_payload_status,
                       'provider_published_at_ms', provider_items.provider_published_at_ms,
                       'provider_observed_at_ms', provider_items.provider_observed_at_ms
                     ) AS observation_edge,
                   to_jsonb(provider_items.*)
                     || jsonb_build_object(
                       'source_domain', sources.source_domain,
                       'source_name', sources.source_name,
                       'source_role', sources.source_role,
                       'trust_tier', sources.trust_tier,
                       'enabled', sources.enabled
                     ) AS provider_observation
              FROM news_item_observation_edges AS edges
              JOIN news_provider_items AS provider_items ON provider_items.provider_item_id = edges.provider_item_id
              JOIN news_sources AS sources ON sources.source_id = edges.source_id
             WHERE edges.news_item_id = %s
             ORDER BY sources.enabled DESC, edges.source_id ASC, provider_items.source_item_key ASC
            """,
            (news_item_id,),
        ).fetchall()
        context_items = [
            _public_context_item_payload(item) for item in self.list_context_items_for_news_item(news_item_id, limit=25)
        ]
        item_payload = _json_dict(row["item"])
        provider_signal = _json_dict(item_payload.get("provider_signal_json"))
        provider_token_impacts = _json_list(item_payload.get("provider_token_impacts_json"))
        agent_brief = _detail_agent_brief(row["agent_brief"])
        token_mentions = _json_list(row["token_mentions"])
        fact_candidates = _json_list(row["fact_candidates"])
        public_item = _public_news_item_payload(item_payload)
        return {
            **public_item,
            "content_tags": _json_list(item_payload.get("content_tags_json")),
            "content_classification": _json_dict(item_payload.get("content_classification_json")),
            "signal": _signal_from_provider_or_agent(provider_signal=provider_signal, agent_brief=agent_brief),
            "token_impacts": provider_token_impacts,
            "token_lanes": _token_lanes_from_mentions(
                token_mentions=token_mentions,
                provider_token_impacts=provider_token_impacts,
            ),
            "fact_lanes": [_fact_lane_from_candidate(candidate) for candidate in fact_candidates],
            "provider_signal": provider_signal,
            "provider_token_impacts": provider_token_impacts,
            "source": _public_source_payload(_json_dict(row["source"])),
            "provider_item": _public_provider_observation_payload(_json_dict(row["provider_item"])),
            "fetch_run": _public_fetch_run_payload(_json_dict(row["fetch_run"]))
            if row["fetch_run"] is not None
            else None,
            "agent_brief": agent_brief,
            "agent_run": _public_agent_run_payload(_json_dict(row["agent_run"]))
            if row["agent_run"] is not None
            else None,
            "observation_edges": [
                _public_observation_edge_payload(_json_dict(observation_row["observation_edge"]))
                for observation_row in observation_rows
            ],
            "provider_observations": [
                _public_provider_observation_payload(_json_dict(observation_row["provider_observation"]))
                for observation_row in observation_rows
            ],
            "entities": _json_list(row["entities"]),
            "token_mentions": token_mentions,
            "fact_candidates": fact_candidates,
            "context_items": context_items,
        }

    def get_news_fact_detail(self, *, fact_candidate_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT facts.*, items.title AS headline, items.canonical_url, items.source_domain
              FROM news_fact_candidates AS facts
              JOIN news_items AS items ON items.news_item_id = facts.news_item_id
             WHERE facts.fact_candidate_id = %s
            """,
            (fact_candidate_id,),
        ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["canonical_url"] = _public_url(result.get("canonical_url"))
        return result

    def list_source_quality_inputs_for_targets(
        self,
        *,
        source_windows: Sequence[tuple[str, str]],
        now_ms: int,
    ) -> list[dict[str, Any]]:
        source_ids_by_window: dict[str, list[str]] = {}
        for source_id, window in source_windows:
            normalized_source_id = str(source_id)
            normalized_window = str(window).strip().lower()
            if not normalized_source_id or not normalized_window:
                continue
            source_ids_by_window.setdefault(normalized_window, []).append(normalized_source_id)
        rows: list[dict[str, Any]] = []
        for window, source_ids in source_ids_by_window.items():
            window_rows = self._list_source_quality_inputs_for_source_ids(
                source_ids=list(dict.fromkeys(source_ids)),
                window_ms=window_ms_for_label(window),
                now_ms=now_ms,
            )
            rows.extend({**row, "window": window} for row in window_rows)
        return rows

    def _list_source_quality_inputs_for_source_ids(
        self,
        *,
        source_ids: Sequence[str] | None,
        window_ms: int,
        now_ms: int,
    ) -> list[dict[str, Any]]:
        window_start_ms = int(now_ms) - max(1, int(window_ms))
        source_filter = list(dict.fromkeys(str(source_id) for source_id in (source_ids or []) if str(source_id)))
        source_filter_param = source_filter or None
        rows = self.conn.execute(
            """
            WITH source_rows AS (
              SELECT source_id
                FROM news_sources
               WHERE %s::text[] IS NULL OR source_id = ANY(%s::text[])
               ORDER BY enabled DESC, source_id ASC
            ),
            window_items AS (
              SELECT items.news_item_id,
                     items.source_id,
                     items.published_at_ms,
                     items.fetched_at_ms,
                     items.lifecycle_status
                FROM source_rows AS sources
                JOIN news_items AS items ON items.source_id = sources.source_id
               WHERE items.published_at_ms >= %s
                 AND items.published_at_ms <= %s
            ),
            fetch_agg AS (
              SELECT fetch_runs.source_id,
                     COUNT(*)::int AS fetch_run_count,
                     COUNT(*) FILTER (WHERE fetch_runs.status = 'success')::int AS fetch_success_count,
                     COALESCE(SUM(fetch_runs.fetched_count), 0)::int AS items_fetched,
                     COALESCE(SUM(fetch_runs.inserted_count), 0)::int AS items_inserted,
                     COALESCE(SUM(fetch_runs.duplicate_count), 0)::int AS items_duplicate
                FROM source_rows AS sources
                JOIN news_fetch_runs AS fetch_runs ON fetch_runs.source_id = sources.source_id
               WHERE fetch_runs.started_at_ms >= %s
                 AND fetch_runs.started_at_ms <= %s
               GROUP BY fetch_runs.source_id
            ),
            item_agg AS (
              SELECT source_id,
                     COUNT(*)::int AS item_count,
                     COUNT(*) FILTER (WHERE lifecycle_status = 'processed')::int AS processed_item_count,
                     MAX(published_at_ms)::bigint AS latest_item_published_at_ms,
                     ROUND(
                       PERCENTILE_CONT(0.5) WITHIN GROUP (
                         ORDER BY GREATEST(0, fetched_at_ms - published_at_ms)
                       )
                     )::bigint AS median_lag_ms
                FROM window_items
               GROUP BY source_id
            ),
            mention_agg AS (
              SELECT items.source_id,
                     COUNT(mentions.mention_id)::int AS mention_count,
                     COUNT(mentions.mention_id) FILTER (
                       WHERE mentions.resolution_status IN (
                         'exact_address',
                         'known_symbol',
                         'unique_by_context'
                       )
                     )::int AS resolved_mention_count
                FROM window_items AS items
                JOIN news_token_mentions AS mentions ON mentions.news_item_id = items.news_item_id
               GROUP BY items.source_id
            ),
            fact_agg AS (
              SELECT items.source_id,
                     COUNT(facts.fact_candidate_id)::int AS fact_count,
                     COUNT(facts.fact_candidate_id) FILTER (
                       WHERE facts.validation_status = 'attention'
                     )::int AS attention_fact_count,
                     COUNT(facts.fact_candidate_id) FILTER (
                       WHERE facts.validation_status = 'accepted'
                     )::int AS accepted_fact_count
                FROM window_items AS items
                JOIN news_fact_candidates AS facts ON facts.news_item_id = items.news_item_id
               GROUP BY items.source_id
            ),
            brief_agg AS (
              SELECT items.source_id,
                     COUNT(DISTINCT briefs.news_item_id) FILTER (
                       WHERE briefs.status = 'ready'
                     )::int AS ready_brief_count
                FROM window_items AS items
                JOIN news_item_agent_briefs AS briefs ON briefs.news_item_id = items.news_item_id
               GROUP BY items.source_id
            ),
            context_agg AS (
              SELECT context_items.source_id,
                     COUNT(*)::int AS context_item_count,
                     COUNT(DISTINCT parent_news_item_id) FILTER (
                       WHERE parent_news_item_id IS NOT NULL
                     )::int AS context_parent_item_count
                FROM source_rows AS sources
                JOIN news_context_items AS context_items
                  ON context_items.source_id = sources.source_id
               WHERE COALESCE(context_items.published_at_ms, context_items.created_at_ms) >= %s
                 AND COALESCE(context_items.published_at_ms, context_items.created_at_ms) <= %s
               GROUP BY context_items.source_id
            ),
            useful_item_agg AS (
              SELECT useful_items.source_id,
                     COUNT(DISTINCT useful_items.news_item_id)::int AS useful_item_count
                FROM (
                  SELECT items.source_id,
                         items.news_item_id
                    FROM window_items AS items
                    JOIN news_fact_candidates AS facts ON facts.news_item_id = items.news_item_id
                   WHERE facts.validation_status IN ('accepted', 'attention')
                  UNION
                  SELECT items.source_id,
                         items.news_item_id
                    FROM window_items AS items
                    JOIN news_context_items AS context_items
                      ON context_items.source_id = items.source_id
                     AND COALESCE(context_items.published_at_ms, context_items.created_at_ms) >= %s
                     AND COALESCE(context_items.published_at_ms, context_items.created_at_ms) <= %s
                     AND context_items.parent_news_item_id = items.news_item_id
                ) AS useful_items
               GROUP BY useful_items.source_id
            )
            SELECT sources.source_id,
                   COALESCE(fetch_agg.fetch_run_count, 0)::int AS fetch_run_count,
                   COALESCE(fetch_agg.fetch_success_count, 0)::int AS fetch_success_count,
                   COALESCE(fetch_agg.items_fetched, 0)::int AS items_fetched,
                   COALESCE(fetch_agg.items_inserted, 0)::int AS items_inserted,
                   COALESCE(fetch_agg.items_duplicate, 0)::int AS items_duplicate,
                   COALESCE(item_agg.item_count, 0)::int AS item_count,
                   COALESCE(item_agg.processed_item_count, 0)::int AS processed_item_count,
                   COALESCE(mention_agg.mention_count, 0)::int AS mention_count,
                   COALESCE(mention_agg.resolved_mention_count, 0)::int AS resolved_mention_count,
                   COALESCE(fact_agg.fact_count, 0)::int AS fact_count,
                   COALESCE(fact_agg.attention_fact_count, 0)::int AS attention_fact_count,
                   COALESCE(fact_agg.accepted_fact_count, 0)::int AS accepted_fact_count,
                   COALESCE(brief_agg.ready_brief_count, 0)::int AS ready_brief_count,
                   COALESCE(context_agg.context_item_count, 0)::int AS context_item_count,
                   COALESCE(context_agg.context_parent_item_count, 0)::int AS context_parent_item_count,
                   COALESCE(useful_item_agg.useful_item_count, 0)::int AS useful_item_count,
                   item_agg.latest_item_published_at_ms,
                   item_agg.median_lag_ms
              FROM source_rows AS sources
              LEFT JOIN fetch_agg ON fetch_agg.source_id = sources.source_id
              LEFT JOIN item_agg ON item_agg.source_id = sources.source_id
              LEFT JOIN mention_agg ON mention_agg.source_id = sources.source_id
              LEFT JOIN fact_agg ON fact_agg.source_id = sources.source_id
              LEFT JOIN brief_agg ON brief_agg.source_id = sources.source_id
              LEFT JOIN context_agg ON context_agg.source_id = sources.source_id
              LEFT JOIN useful_item_agg ON useful_item_agg.source_id = sources.source_id
             ORDER BY sources.source_id ASC
            """,
            (
                source_filter_param,
                source_filter_param,
                window_start_ms,
                int(now_ms),
                window_start_ms,
                int(now_ms),
                window_start_ms,
                int(now_ms),
                window_start_ms,
                int(now_ms),
            ),
        ).fetchall()
        return [dict(row) for row in rows]

    def replace_source_quality_rows(
        self,
        *,
        rows: Sequence[Mapping[str, Any]],
        status_window: str | None = None,
        commit: bool = True,
    ) -> list[str]:
        normalized_status_window = str(status_window).strip().lower() if status_window else None
        changed_status_source_ids: list[str] = []
        for row in rows:
            payload = _source_quality_payload(row)
            payload["payload_hash"] = _stable_payload_hash(payload, exclude=_PUBLICATION_METADATA_FIELDS)
            self.conn.execute(
                """
                INSERT INTO news_source_quality_rows (
                  row_id, source_id, "window", computed_at_ms, fetch_success_rate,
                  items_fetched, items_inserted, duplicate_rate, process_success_rate,
                  resolved_token_rate, attention_rate, accepted_fact_rate, brief_ready_rate,
                  median_lag_ms, quality_score, diagnostics_json, projection_version, payload_hash
                )
                VALUES (
                  %(row_id)s, %(source_id)s, %(window)s, %(computed_at_ms)s, %(fetch_success_rate)s,
                  %(items_fetched)s, %(items_inserted)s, %(duplicate_rate)s, %(process_success_rate)s,
                  %(resolved_token_rate)s, %(attention_rate)s, %(accepted_fact_rate)s, %(brief_ready_rate)s,
                  %(median_lag_ms)s, %(quality_score)s, %(diagnostics_json)s, %(projection_version)s,
                  %(payload_hash)s
                )
                ON CONFLICT (source_id, "window") DO UPDATE SET
                  row_id = EXCLUDED.row_id,
                  computed_at_ms = EXCLUDED.computed_at_ms,
                  fetch_success_rate = EXCLUDED.fetch_success_rate,
                  items_fetched = EXCLUDED.items_fetched,
                  items_inserted = EXCLUDED.items_inserted,
                  duplicate_rate = EXCLUDED.duplicate_rate,
                  process_success_rate = EXCLUDED.process_success_rate,
                  resolved_token_rate = EXCLUDED.resolved_token_rate,
                  attention_rate = EXCLUDED.attention_rate,
                  accepted_fact_rate = EXCLUDED.accepted_fact_rate,
                  brief_ready_rate = EXCLUDED.brief_ready_rate,
                  median_lag_ms = EXCLUDED.median_lag_ms,
                  quality_score = EXCLUDED.quality_score,
                  diagnostics_json = EXCLUDED.diagnostics_json,
                  projection_version = EXCLUDED.projection_version,
                  payload_hash = EXCLUDED.payload_hash
                WHERE news_source_quality_rows.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash
                """,
                payload,
            )
            if normalized_status_window and payload["window"] == normalized_status_window:
                status = _json_dict(row.get("diagnostics_json")).get("status")
                cursor = self.conn.execute(
                    """
                    UPDATE news_sources
                       SET source_quality_status = %s,
                           updated_at_ms = GREATEST(updated_at_ms, %s)
                     WHERE source_id = %s
                       AND source_quality_status IS DISTINCT FROM %s
                    """,
                    (
                        str(status or "unknown"),
                        payload["computed_at_ms"],
                        payload["source_id"],
                        str(status or "unknown"),
                    ),
                )
                if int(getattr(cursor, "rowcount", 0) or 0) > 0:
                    changed_status_source_ids.append(str(payload["source_id"]))
        if commit:
            self.conn.commit()
        return list(dict.fromkeys(changed_status_source_ids))

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
            context_aggregate AS (
              SELECT context_items.source_id,
                     COUNT(context_items.context_item_id)::int AS context_item_count,
                     MAX(
                       GREATEST(
                         COALESCE(context_items.published_at_ms, context_items.created_at_ms),
                         context_items.created_at_ms
                       )
                     ) AS latest_context_seen_at_ms
                FROM news_context_items AS context_items
               GROUP BY context_items.source_id
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
               GROUP BY edges.source_id
            ),
            latest_fetch_run AS (
              SELECT DISTINCT ON (fetch_runs.source_id)
                     fetch_runs.source_id,
                     jsonb_build_object(
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
               ORDER BY fetch_runs.source_id, fetch_runs.started_at_ms DESC, fetch_runs.fetch_run_id DESC
            ),
            latest_quality AS (
              SELECT DISTINCT ON (quality.source_id)
                     quality.*
                FROM news_source_quality_rows AS quality
               ORDER BY
                 quality.source_id,
                 quality.computed_at_ms DESC,
                 CASE quality."window"
                   WHEN '24h' THEN 0
                   WHEN '4h' THEN 1
                   WHEN '1h' THEN 2
                   WHEN '7d' THEN 3
                   ELSE 4
                 END
            )
            SELECT sources.*,
                   COALESCE(edge_item_aggregate.canonical_item_count, 0)::int AS item_count,
                   edge_item_aggregate.latest_item_published_at_ms,
                   edge_item_aggregate.latest_item_fetched_at_ms,
                   COALESCE(context_aggregate.context_item_count, 0)::int AS context_item_count,
                   context_aggregate.latest_context_seen_at_ms,
                   latest_fetch_run.latest_fetch_run_json,
                   CASE
                     WHEN latest_quality.source_id IS NULL THEN NULL
                     ELSE to_jsonb(latest_quality)
                   END AS latest_quality_json,
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
              LEFT JOIN context_aggregate ON context_aggregate.source_id = sources.source_id
              LEFT JOIN provider_item_aggregate ON provider_item_aggregate.source_id = sources.source_id
              LEFT JOIN page_row_aggregate ON page_row_aggregate.source_id = sources.source_id
              LEFT JOIN latest_fetch_run ON latest_fetch_run.source_id = sources.source_id
              LEFT JOIN latest_quality ON latest_quality.source_id = sources.source_id
             ORDER BY sources.enabled DESC, sources.source_domain ASC, sources.source_id ASC
            """
        ).fetchall()
        return [_source_status_payload(row) for row in rows]

    def news_dedup_diagnostics(
        self,
        *,
        window_ms: int = 8 * 3_600_000,
        score_threshold: int = 80,
        now_ms: int | None = None,
    ) -> dict[str, Any]:
        resolved_now_ms = int(now_ms) if now_ms is not None else 0
        row = self.conn.execute(
            """
            WITH params AS (
              SELECT
                CASE
                  WHEN %(now_ms)s::bigint > 0 THEN %(now_ms)s::bigint
                  ELSE (extract(epoch FROM clock_timestamp()) * 1000)::bigint
                END AS now_ms,
                GREATEST(%(window_ms)s::bigint, 0) AS window_ms,
                GREATEST(%(score_threshold)s::numeric, 0) AS score_threshold
            ),
            visible_rows AS (
              SELECT rows.row_id,
                     rows.news_item_id,
                     rows.canonical_item_key,
                     items.content_hash,
                     EXISTS (
                       SELECT 1
                         FROM news_item_observation_edges AS edges
                         JOIN news_sources AS sources ON sources.source_id = edges.source_id
                        WHERE edges.news_item_id = rows.news_item_id
                          AND sources.enabled = true
                     ) AS has_enabled_edge
                FROM news_page_rows AS rows
                JOIN news_items AS items ON items.news_item_id = rows.news_item_id
            ),
            enabled_content_duplicates AS (
              SELECT content_hash, COUNT(*)::int AS row_count
                FROM visible_rows
               WHERE has_enabled_edge = true
                 AND COALESCE(content_hash, '') <> ''
               GROUP BY content_hash
              HAVING COUNT(*) > 1
            ),
            top_content_duplicate_groups AS (
              SELECT jsonb_build_object(
                       'content_hash', duplicates.content_hash,
                       'visible_row_count', duplicates.row_count,
                       'duplicate_excess', duplicates.row_count - 1,
                       'news_item_ids',
                         (
                           SELECT COALESCE(jsonb_agg(rows.news_item_id ORDER BY rows.news_item_id), '[]'::jsonb)
                             FROM visible_rows AS rows
                            WHERE rows.content_hash = duplicates.content_hash
                              AND rows.has_enabled_edge = true
                         )
                     ) AS payload
                FROM enabled_content_duplicates AS duplicates
               ORDER BY duplicates.row_count DESC, duplicates.content_hash ASC
               LIMIT 20
            ),
            top_canonical_duplicate_groups AS (
              SELECT jsonb_build_object(
                       'canonical_item_key', rows.canonical_item_key,
                       'visible_row_count', COUNT(*)::int,
                       'duplicate_excess', COUNT(*)::int - 1,
                       'news_item_ids', jsonb_agg(rows.news_item_id ORDER BY rows.news_item_id)
                     ) AS payload
                FROM visible_rows AS rows
               WHERE rows.has_enabled_edge = true
                 AND COALESCE(rows.canonical_item_key, '') <> ''
               GROUP BY rows.canonical_item_key
              HAVING COUNT(*) > 1
               ORDER BY COUNT(*) DESC, rows.canonical_item_key ASC
               LIMIT 20
            ),
            scoped_items AS (
              SELECT items.news_item_id,
                     items.source_id,
                     items.title_fingerprint,
                     items.canonical_url,
                     items.published_at_ms,
                     items.fetched_at_ms,
                     items.created_at_ms,
                     CASE
                       WHEN items.provider_signal_json ->> 'score' ~ '^-?[0-9]+(\\.[0-9]+)?$'
                         THEN (items.provider_signal_json ->> 'score')::numeric
                       ELSE 0
                     END AS provider_score
                FROM news_items AS items
                CROSS JOIN params
               WHERE COALESCE(NULLIF(items.created_at_ms, 0), items.fetched_at_ms, 0)
                     >= params.now_ms - params.window_ms
            ),
            material_title_duplicates AS (
              SELECT scoped_items.source_id,
                     scoped_items.title_fingerprint,
                     COUNT(*)::int AS row_count,
                     COUNT(*) FILTER (WHERE scoped_items.provider_score >= params.score_threshold)::int
                       AS ge_threshold_rows
                FROM scoped_items
                CROSS JOIN params
               WHERE COALESCE(scoped_items.title_fingerprint, '') <> ''
               GROUP BY scoped_items.source_id, scoped_items.title_fingerprint
              HAVING COUNT(*) > 1
            ),
            top_material_title_duplicate_groups AS (
              SELECT jsonb_build_object(
                       'source_id', duplicates.source_id,
                       'title_fingerprint', duplicates.title_fingerprint,
                       'row_count', duplicates.row_count,
                       'duplicate_rows', duplicates.row_count - 1,
                       'ge_threshold_rows', duplicates.ge_threshold_rows,
                       'ge_threshold_duplicate_rows', GREATEST(duplicates.ge_threshold_rows - 1, 0),
                       'news_item_ids',
                         (
                           SELECT COALESCE(jsonb_agg(items.news_item_id ORDER BY items.news_item_id), '[]'::jsonb)
                             FROM scoped_items AS items
                            WHERE items.source_id = duplicates.source_id
                              AND items.title_fingerprint = duplicates.title_fingerprint
                         )
                     ) AS payload
                FROM material_title_duplicates AS duplicates
               ORDER BY duplicates.ge_threshold_rows DESC, duplicates.row_count DESC,
                        duplicates.source_id ASC, duplicates.title_fingerprint ASC
               LIMIT 20
            ),
            case_insensitive_url_duplicates AS (
              SELECT lower(scoped_items.canonical_url) AS normalized_url,
                     COUNT(*)::int AS row_count,
                     COUNT(*) FILTER (WHERE scoped_items.provider_score >= params.score_threshold)::int
                       AS ge_threshold_rows
                FROM scoped_items
                CROSS JOIN params
               WHERE scoped_items.canonical_url ~* '^https?://'
               GROUP BY lower(scoped_items.canonical_url)
              HAVING COUNT(*) > 1
            ),
            top_case_insensitive_url_duplicate_groups AS (
              SELECT jsonb_build_object(
                       'normalized_url', duplicates.normalized_url,
                       'row_count', duplicates.row_count,
                       'duplicate_rows', duplicates.row_count - 1,
                       'ge_threshold_rows', duplicates.ge_threshold_rows,
                       'ge_threshold_duplicate_rows', GREATEST(duplicates.ge_threshold_rows - 1, 0),
                       'news_item_ids',
                         (
                           SELECT COALESCE(jsonb_agg(items.news_item_id ORDER BY items.news_item_id), '[]'::jsonb)
                             FROM scoped_items AS items
                            WHERE lower(items.canonical_url) = duplicates.normalized_url
                         )
                     ) AS payload
                FROM case_insensitive_url_duplicates AS duplicates
               ORDER BY duplicates.ge_threshold_rows DESC, duplicates.row_count DESC, duplicates.normalized_url ASC
               LIMIT 20
            ),
            preview_or_generic_url_rows AS (
              SELECT COUNT(*)::int AS row_count,
                     COUNT(*) FILTER (WHERE scoped_items.provider_score >= params.score_threshold)::int
                       AS ge_threshold_rows
                FROM scoped_items
                CROSS JOIN params
               WHERE scoped_items.canonical_url ~* '^https?://news\\.6551\\.io/preview/'
                  OR scoped_items.canonical_url ~* '^https?://([^/]+\\.)?treeofalpha\\.com/preview_article'
                  OR scoped_items.canonical_url ~* '^https?://([^/]+\\.)?binance\\.com/[^?]*/support/announcement/?$'
            ),
            historical_high_score_items AS (
              SELECT COUNT(*)::int AS row_count
                FROM scoped_items
                CROSS JOIN params
               WHERE scoped_items.provider_score >= params.score_threshold
                 AND COALESCE(scoped_items.published_at_ms, 0) < params.now_ms - params.window_ms
            ),
            brief_input_risk AS (
              SELECT COUNT(*)::int AS row_count,
                     COUNT(*) FILTER (
                       WHERE COALESCE(items.published_at_ms, 0) < params.now_ms - params.window_ms
                     )::int AS stale_rows
                FROM news_projection_dirty_targets AS targets
                JOIN news_items AS items ON items.news_item_id = targets.target_id
                CROSS JOIN params
               WHERE targets.projection_name = 'brief_input'
                 AND targets.target_kind = 'news_item'
            ),
            source_sync AS (
              SELECT jsonb_build_object(
                       'source_id', sources.source_id,
                       'enabled', sources.enabled,
                       'source_domain', sources.source_domain,
                       'sync_high_watermark_ms', sources.sync_high_watermark_ms,
                       'sync_overlap_ms', sources.sync_overlap_ms,
                       'watermark_lag_ms',
                         CASE
                           WHEN sources.sync_high_watermark_ms > 0
                           THEN GREATEST(params.now_ms - sources.sync_high_watermark_ms, 0)
                           ELSE NULL
                         END,
                       'pages_scanned', sources.sync_diagnostics_json -> 'pages_scanned',
                       'rest_received', sources.sync_diagnostics_json -> 'rest_received',
                       'oldest_seen_ms', sources.sync_diagnostics_json -> 'oldest_seen_ms',
                       'stop_reason', sources.sync_diagnostics_json ->> 'stop_reason'
                     ) AS payload
                FROM news_sources AS sources
                CROSS JOIN params
               WHERE sources.provider_type = 'opennews'
               ORDER BY sources.enabled DESC, sources.source_id ASC
            )
            SELECT
              (SELECT COUNT(*)::int FROM news_provider_items) AS raw_observation_count,
              (SELECT COUNT(*)::int FROM news_items) AS canonical_item_count,
              (SELECT COUNT(*)::int FROM news_item_observation_edges) AS observation_edge_count,
              (SELECT COUNT(*)::int FROM visible_rows WHERE has_enabled_edge = true) AS enabled_serving_row_count,
              (SELECT COUNT(*)::int FROM visible_rows WHERE has_enabled_edge = false) AS disabled_serving_row_count,
              COALESCE(
                (SELECT SUM(row_count - 1)::int FROM enabled_content_duplicates),
                0
              ) AS enabled_exact_content_visible_duplicate_excess,
              COALESCE((SELECT jsonb_agg(payload) FROM top_content_duplicate_groups), '[]'::jsonb)
                AS top_visible_content_duplicate_groups,
              COALESCE((SELECT jsonb_agg(payload) FROM top_canonical_duplicate_groups), '[]'::jsonb)
                AS top_visible_canonical_duplicate_groups,
              jsonb_build_object(
                'groups', COALESCE((SELECT COUNT(*)::int FROM material_title_duplicates), 0),
                'rows', COALESCE((SELECT SUM(row_count)::int FROM material_title_duplicates), 0),
                'duplicate_rows', COALESCE((SELECT SUM(row_count - 1)::int FROM material_title_duplicates), 0),
                'ge_threshold_rows', COALESCE((SELECT SUM(ge_threshold_rows)::int FROM material_title_duplicates), 0),
                'ge_threshold_duplicate_rows',
                  COALESCE((SELECT SUM(GREATEST(ge_threshold_rows - 1, 0))::int FROM material_title_duplicates), 0),
                'top_groups',
                  COALESCE((SELECT jsonb_agg(payload) FROM top_material_title_duplicate_groups), '[]'::jsonb)
              ) AS material_title_duplicate_groups,
              jsonb_build_object(
                'groups', COALESCE((SELECT COUNT(*)::int FROM case_insensitive_url_duplicates), 0),
                'rows', COALESCE((SELECT SUM(row_count)::int FROM case_insensitive_url_duplicates), 0),
                'duplicate_rows', COALESCE((SELECT SUM(row_count - 1)::int FROM case_insensitive_url_duplicates), 0),
                'ge_threshold_rows',
                  COALESCE((SELECT SUM(ge_threshold_rows)::int FROM case_insensitive_url_duplicates), 0),
                'ge_threshold_duplicate_rows',
                  COALESCE(
                    (SELECT SUM(GREATEST(ge_threshold_rows - 1, 0))::int FROM case_insensitive_url_duplicates),
                    0
                  ),
                'top_groups',
                  COALESCE((SELECT jsonb_agg(payload) FROM top_case_insensitive_url_duplicate_groups), '[]'::jsonb)
              ) AS case_insensitive_url_duplicate_groups,
              jsonb_build_object(
                'rows', COALESCE((SELECT row_count FROM preview_or_generic_url_rows), 0),
                'ge_threshold_rows', COALESCE((SELECT ge_threshold_rows FROM preview_or_generic_url_rows), 0)
              ) AS preview_or_generic_url_rows,
              jsonb_build_object(
                'rows', COALESCE((SELECT row_count FROM historical_high_score_items), 0)
              ) AS historical_high_score_items,
              jsonb_build_object(
                'rows', COALESCE((SELECT row_count FROM brief_input_risk), 0),
                'stale_rows', COALESCE((SELECT stale_rows FROM brief_input_risk), 0)
              ) AS brief_input_risk,
              COALESCE((SELECT jsonb_agg(payload) FROM source_sync), '[]'::jsonb) AS source_sync_diagnostics
            """,
            {
                "now_ms": resolved_now_ms,
                "window_ms": max(0, int(window_ms)),
                "score_threshold": max(0, int(score_threshold)),
            },
        ).fetchone()
        if row is None:
            return {
                "raw_observation_count": 0,
                "canonical_item_count": 0,
                "observation_edge_count": 0,
                "enabled_serving_row_count": 0,
                "disabled_serving_row_count": 0,
                "enabled_exact_content_visible_duplicate_excess": 0,
                "top_visible_content_duplicate_groups": [],
                "top_visible_canonical_duplicate_groups": [],
                "material_title_duplicate_groups": {},
                "case_insensitive_url_duplicate_groups": {},
                "preview_or_generic_url_rows": {},
                "historical_high_score_items": {},
                "brief_input_risk": {},
                "source_sync_diagnostics": [],
            }
        return {
            "raw_observation_count": int(row["raw_observation_count"] or 0),
            "canonical_item_count": int(row["canonical_item_count"] or 0),
            "observation_edge_count": int(row["observation_edge_count"] or 0),
            "enabled_serving_row_count": int(row["enabled_serving_row_count"] or 0),
            "disabled_serving_row_count": int(row["disabled_serving_row_count"] or 0),
            "enabled_exact_content_visible_duplicate_excess": int(
                row["enabled_exact_content_visible_duplicate_excess"] or 0
            ),
            "top_visible_content_duplicate_groups": _json_list(row["top_visible_content_duplicate_groups"]),
            "top_visible_canonical_duplicate_groups": _json_list(row["top_visible_canonical_duplicate_groups"]),
            "material_title_duplicate_groups": _json_dict(row["material_title_duplicate_groups"]),
            "case_insensitive_url_duplicate_groups": _json_dict(row["case_insensitive_url_duplicate_groups"]),
            "preview_or_generic_url_rows": _json_dict(row["preview_or_generic_url_rows"]),
            "historical_high_score_items": _json_dict(row["historical_high_score_items"]),
            "brief_input_risk": _json_dict(row["brief_input_risk"]),
            "source_sync_diagnostics": _json_list(row["source_sync_diagnostics"]),
        }

    def _page_row_summary_by_news_item_id(self, news_item_ids: Sequence[str]) -> dict[str, dict[str, Any]]:
        normalized_ids = list(dict.fromkeys(str(news_item_id) for news_item_id in news_item_ids if str(news_item_id)))
        if not normalized_ids:
            return {}
        rows = self.conn.execute(
            """
            SELECT items.news_item_id,
                   items.canonical_item_key,
                   COALESCE(edge_summary.duplicate_observation_count, 0)::int
                     AS duplicate_observation_count,
                   COALESCE(edge_summary.source_ids_json, '[]'::jsonb) AS source_ids_json,
                   COALESCE(edge_summary.source_domains_json, '[]'::jsonb) AS source_domains_json,
                   COALESCE(edge_summary.provider_article_keys_json, '[]'::jsonb) AS provider_article_keys_json
              FROM news_items AS items
              LEFT JOIN LATERAL (
                SELECT
                  COUNT(*)::int AS duplicate_observation_count,
                  COALESCE(jsonb_agg(DISTINCT edges.source_id ORDER BY edges.source_id), '[]'::jsonb)
                    AS source_ids_json,
                  COALESCE(
                    jsonb_agg(DISTINCT sources.source_domain ORDER BY sources.source_domain),
                    '[]'::jsonb
                  ) AS source_domains_json,
                  COALESCE(
                    jsonb_agg(DISTINCT edges.provider_article_key ORDER BY edges.provider_article_key)
                      FILTER (WHERE edges.provider_article_key <> ''),
                    '[]'::jsonb
                  ) AS provider_article_keys_json
                  FROM news_item_observation_edges AS edges
                  JOIN news_sources AS sources ON sources.source_id = edges.source_id
                 WHERE edges.news_item_id = items.news_item_id
                   AND sources.enabled = true
              ) AS edge_summary ON true
             WHERE items.news_item_id = ANY(%s::text[])
            """,
            (normalized_ids,),
        ).fetchall()
        return {str(row["news_item_id"]): dict(row) for row in rows}

    def replace_page_rows_for_items(
        self,
        *,
        news_item_ids: Sequence[str],
        rows: Sequence[Mapping[str, Any]],
        commit: bool = True,
    ) -> dict[str, int]:
        scoped_ids = list(dict.fromkeys(str(news_item_id) for news_item_id in news_item_ids))
        row_payloads = [_page_row_payload(row) for row in rows]
        row_summary_by_item_id = self._page_row_summary_by_news_item_id(
            [str(payload["news_item_id"]) for payload in row_payloads]
        )
        for payload in row_payloads:
            _apply_page_row_summary(payload, row_summary_by_item_id.get(str(payload["news_item_id"]), {}))
        incoming_row_ids = list(dict.fromkeys(str(payload["row_id"]) for payload in row_payloads))
        deleted = 0
        if scoped_ids:
            if incoming_row_ids:
                cursor = self.conn.execute(
                    """
                    DELETE FROM news_page_rows
                     WHERE news_item_id = ANY(%s::text[])
                       AND NOT (row_id = ANY(%s::text[]))
                    """,
                    (scoped_ids, incoming_row_ids),
                )
            else:
                cursor = self.conn.execute(
                    "DELETE FROM news_page_rows WHERE news_item_id = ANY(%s::text[])",
                    (scoped_ids,),
                )
            deleted = int(getattr(cursor, "rowcount", 0) or 0)
        inserted = 0
        updated = 0
        unchanged = 0
        for payload in row_payloads:
            payload["payload_hash"] = _stable_payload_hash(payload, exclude=_PUBLICATION_METADATA_FIELDS)
            returned = self.conn.execute(
                """
                INSERT INTO news_page_rows (
                  row_id, news_item_id, latest_at_ms, lifecycle_status,
                  headline, summary, source_domain, canonical_url, token_lanes_json,
                  fact_lanes_json, content_class, content_tags_json, content_classification_json,
                  source_json, signal_json, token_impacts_json, agent_brief_json,
                  agent_status, agent_brief_computed_at_ms, computed_at_ms, projection_version,
                  canonical_item_key, duplicate_count, source_ids_json, source_domains_json,
                  provider_article_keys_json, payload_hash
                )
                VALUES (
                  %(row_id)s, %(news_item_id)s, %(latest_at_ms)s, %(lifecycle_status)s,
                  %(headline)s, %(summary)s, %(source_domain)s, %(canonical_url)s, %(token_lanes_json)s,
                  %(fact_lanes_json)s, %(content_class)s, %(content_tags_json)s, %(content_classification_json)s,
                  %(source_json)s, %(signal_json)s, %(token_impacts_json)s,
                  %(agent_brief_json)s, %(agent_status)s, %(agent_brief_computed_at_ms)s,
                  %(computed_at_ms)s, %(projection_version)s, %(canonical_item_key)s,
                  %(duplicate_count)s, %(source_ids_json)s, %(source_domains_json)s,
                  %(provider_article_keys_json)s, %(payload_hash)s
                )
                ON CONFLICT (row_id) DO UPDATE SET
                  news_item_id = EXCLUDED.news_item_id,
                  latest_at_ms = EXCLUDED.latest_at_ms,
                  lifecycle_status = EXCLUDED.lifecycle_status,
                  headline = EXCLUDED.headline,
                  summary = EXCLUDED.summary,
                  source_domain = EXCLUDED.source_domain,
                  canonical_url = EXCLUDED.canonical_url,
                  token_lanes_json = EXCLUDED.token_lanes_json,
                  fact_lanes_json = EXCLUDED.fact_lanes_json,
                  content_class = EXCLUDED.content_class,
                  content_tags_json = EXCLUDED.content_tags_json,
                  content_classification_json = EXCLUDED.content_classification_json,
                  source_json = EXCLUDED.source_json,
                  signal_json = EXCLUDED.signal_json,
                  token_impacts_json = EXCLUDED.token_impacts_json,
                  agent_brief_json = EXCLUDED.agent_brief_json,
                  agent_status = EXCLUDED.agent_status,
                  agent_brief_computed_at_ms = EXCLUDED.agent_brief_computed_at_ms,
                  computed_at_ms = EXCLUDED.computed_at_ms,
                  projection_version = EXCLUDED.projection_version,
                  canonical_item_key = EXCLUDED.canonical_item_key,
                  duplicate_count = EXCLUDED.duplicate_count,
                  source_ids_json = EXCLUDED.source_ids_json,
                  source_domains_json = EXCLUDED.source_domains_json,
                  provider_article_keys_json = EXCLUDED.provider_article_keys_json,
                  payload_hash = EXCLUDED.payload_hash
                WHERE news_page_rows.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash
                RETURNING (xmax = 0) AS inserted
                """,
                payload,
            ).fetchone()
            if returned is None:
                unchanged += 1
            elif bool(returned["inserted"]):
                inserted += 1
            else:
                updated += 1
        if commit:
            self.conn.commit()
        return {"inserted": inserted, "updated": updated, "unchanged": unchanged, "deleted": deleted}

    def delete_page_rows_for_sources(
        self,
        *,
        source_ids: Sequence[str] | None = None,
        source_domains: Sequence[str] | None = None,
        commit: bool = True,
    ) -> int:
        normalized_source_ids = [str(item) for item in (source_ids or [])]
        normalized_domains = [str(item) for item in (source_domains or [])]
        cursor = self.conn.execute(
            """
            WITH affected_items AS (
              SELECT DISTINCT edges.news_item_id
                FROM news_item_observation_edges AS edges
                JOIN news_sources AS sources ON sources.source_id = edges.source_id
               WHERE (
                 (%s::text[] <> '{}'::text[] AND edges.source_id = ANY(%s::text[]))
                 OR (%s::text[] <> '{}'::text[] AND sources.source_domain = ANY(%s::text[]))
               )
            ),
            deletable_items AS (
              SELECT affected_items.news_item_id
                FROM affected_items
               WHERE NOT EXISTS (
                 SELECT 1
                   FROM news_item_observation_edges AS edges
                   JOIN news_sources AS sources ON sources.source_id = edges.source_id
                  WHERE edges.news_item_id = affected_items.news_item_id
                    AND sources.enabled = true
               )
            )
            DELETE FROM news_page_rows AS rows
             USING deletable_items
             WHERE rows.news_item_id = deletable_items.news_item_id
            """,
            (normalized_source_ids, normalized_source_ids, normalized_domains, normalized_domains),
        )
        if commit:
            self.conn.commit()
        return int(cursor.rowcount or 0)

    def delete_page_rows_without_enabled_observation_edges(self, *, commit: bool = True) -> int:
        cursor = self.conn.execute(
            """
            DELETE FROM news_page_rows AS rows
             WHERE NOT EXISTS (
               SELECT 1
                 FROM news_item_observation_edges AS edges
                 JOIN news_sources AS sources ON sources.source_id = edges.source_id
                WHERE edges.news_item_id = rows.news_item_id
                  AND sources.enabled = true
             )
            """
        )
        if commit:
            self.conn.commit()
        return int(cursor.rowcount or 0)


def _source_payload(source: NewsSourceConfig | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(source, NewsSourceConfig):
        return {
            "source_id": source.source_id,
            "provider_type": source.provider_type,
            "feed_url": source.feed_url,
            "source_domain": source.source_domain,
            "source_name": source.source_name,
            "source_role": source.source_role,
            "trust_tier": source.trust_tier,
            "managed_by_config": source.managed_by_config,
            "enabled": source.enabled,
            "refresh_interval_seconds": source.refresh_interval_seconds,
            "coverage_tags": source.coverage_tags,
            "asset_universe": source.asset_universe,
            "authority_scope": source.authority_scope or {},
            "fetch_policy": source.fetch_policy or {},
            "context_policy": source.context_policy or {},
            "cost_policy": source.cost_policy or {},
        }
    payload = dict(source)
    payload["coverage_tags"] = normalize_string_tuple(payload.get("coverage_tags"))
    payload["asset_universe"] = normalize_string_tuple(payload.get("asset_universe"))
    payload["authority_scope"] = _json_dict(payload.get("authority_scope"))
    payload["fetch_policy"] = _json_dict(payload.get("fetch_policy"))
    payload["context_policy"] = _json_dict(payload.get("context_policy"))
    payload["cost_policy"] = _json_dict(payload.get("cost_policy"))
    return payload


def news_page_cursor(row: Mapping[str, Any]) -> str:
    return f"{int(row['latest_at_ms'])}:{row['row_id']}"


def _decode_page_cursor(cursor: str | None) -> tuple[int | None, str | None]:
    if not cursor:
        return None, None
    raw_time, separator, row_id = str(cursor).partition(":")
    if not separator:
        return None, str(cursor)
    try:
        cursor_time = int(raw_time)
    except ValueError:
        return None, str(cursor)
    return cursor_time, row_id


def _news_page_row_filter_sql(
    *,
    status: str | None = None,
    direction: str | None = None,
    provider_type: str | None = None,
    source_role: str | None = None,
    trust_tier: str | None = None,
    coverage_tag: str | None = None,
    content_class: str | None = None,
    content_tag: str | None = None,
    decision_class: str | None = None,
    signal: str | None = None,
    min_score: int | None = None,
    q: str | None = None,
) -> tuple[str, list[Any]]:
    filters: list[str] = []
    filter_params: list[Any] = []
    if status:
        filters.append("lifecycle_status = %s")
        filter_params.append(str(status))
    if direction:
        filters.append("LOWER(signal_json ->> 'direction') = %s")
        filter_params.append(str(direction).strip().lower())
    if signal:
        filters.append("LOWER(signal_json ->> 'direction') = %s")
        filter_params.append(str(signal).strip().lower())
    if min_score is not None:
        filters.append("COALESCE(NULLIF(signal_json ->> 'score', '')::int, -1) >= %s")
        filter_params.append(int(min_score))
    if decision_class:
        filters.append("agent_brief_json ->> 'decision_class' = %s")
        filter_params.append(str(decision_class))
    if provider_type:
        filters.append("source_json ->> 'provider_type' = %s")
        filter_params.append(str(provider_type))
    if source_role:
        filters.append("source_json ->> 'source_role' = %s")
        filter_params.append(str(source_role))
    if trust_tier:
        filters.append("source_json ->> 'trust_tier' = %s")
        filter_params.append(str(trust_tier))
    if coverage_tag:
        filters.append("(source_json -> 'coverage_tags') ? %s")
        filter_params.append(str(coverage_tag))
    if content_class:
        filters.append("content_class = %s")
        filter_params.append(str(content_class))
    if content_tag:
        filters.append("(content_tags_json ? %s)")
        filter_params.append(str(content_tag))
    if q:
        filters.append("(headline ILIKE %s OR summary ILIKE %s OR token_lanes_json::text ILIKE %s)")
        needle = f"%{str(q).strip()}%"
        filter_params.extend([needle, needle, needle])
    filter_sql = " AND " + " AND ".join(filters) if filters else ""
    return filter_sql, filter_params


def _page_row_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    payload["latest_at_ms"] = int(payload["latest_at_ms"])
    payload["computed_at_ms"] = int(payload["computed_at_ms"])
    payload["headline"] = str(payload.get("headline") or payload.get("title") or "")
    payload["canonical_url"] = str(payload.get("canonical_url") or payload.get("url") or "")
    payload["summary"] = str(payload.get("summary") or "")
    payload["token_lanes_json"] = _json(payload.get("token_lanes_json", payload.get("token_lanes")) or [])
    payload["fact_lanes_json"] = _json(payload.get("fact_lanes_json", payload.get("fact_lanes")) or [])
    payload["token_impacts_json"] = _json(payload.get("token_impacts_json", payload.get("token_impacts")) or [])
    payload["content_class"] = str(payload.get("content_class") or "low_signal")
    payload["content_tags_json"] = _json(payload.get("content_tags_json", payload.get("content_tags")) or [])
    payload["content_classification_json"] = _json(
        payload.get("content_classification_json", payload.get("content_classification")) or {}
    )
    payload["source_json"] = _json(payload.get("source_json", payload.get("source")) or {})
    agent_brief = payload.get("agent_brief_json", payload.get("agent_brief")) or {"status": "pending"}
    agent_status = str(payload.get("agent_status") or payload.get("agent_brief_status") or "pending")
    signal = payload.get("signal_json", payload.get("signal")) or _signal_from_agent_brief(agent_brief)
    payload["signal_json"] = _json(signal)
    payload["agent_brief_json"] = _json(agent_brief)
    payload["agent_status"] = agent_status
    payload["agent_brief_computed_at_ms"] = (
        int(payload["agent_brief_computed_at_ms"]) if payload.get("agent_brief_computed_at_ms") is not None else None
    )
    return payload


def _apply_page_row_summary(payload: dict[str, Any], summary: Mapping[str, Any]) -> None:
    payload["canonical_item_key"] = str(payload.get("canonical_item_key") or summary.get("canonical_item_key") or "")
    payload["duplicate_count"] = int(payload.get("duplicate_count") or summary.get("duplicate_observation_count") or 1)
    payload["source_ids_json"] = _json(
        payload.get("source_ids_json", payload.get("source_ids")) or summary.get("source_ids_json") or []
    )
    payload["source_domains_json"] = _json(
        payload.get("source_domains_json", payload.get("source_domains")) or summary.get("source_domains_json") or []
    )
    payload["provider_article_keys_json"] = _json(
        payload.get("provider_article_keys_json", payload.get("provider_article_keys"))
        or summary.get("provider_article_keys_json")
        or []
    )


def _detail_agent_brief(value: Any) -> dict[str, Any]:
    return _public_agent_brief_payload(value)


def _signal_from_agent_brief(value: Any) -> dict[str, Any]:
    payload = _json_dict(value)
    if str(payload.get("status") or "") != "ready":
        return {
            "source": "partial",
            "status": "partial",
            "direction": "neutral",
            "label_zh": "中性",
            "method": "pending",
        }
    direction = str(payload.get("direction") or "neutral")
    return {
        "source": "agent",
        "status": "ready",
        "direction": direction,
        "label_zh": _direction_label(direction),
        "title_zh": _json_dict(payload.get("brief_json")).get("title_zh"),
        "summary_zh": _json_dict(payload.get("brief_json")).get("summary_zh"),
        "method": "news_item_brief",
    }


def _signal_from_provider_or_agent(
    *,
    provider_signal: Mapping[str, Any],
    agent_brief: Mapping[str, Any],
) -> dict[str, Any]:
    provider_payload = _provider_signal_payload(provider_signal)
    provider_score = _optional_int(provider_payload.get("score")) if provider_payload else None
    if str(agent_brief.get("status") or "") == "ready":
        direction = str(agent_brief.get("direction") or "neutral")
        return _signal_with_independent_state(
            {
                "source": "agent",
                "status": "ready",
                "direction": direction,
                "label_zh": _direction_label(direction),
                "score": provider_score,
                "grade": provider_payload.get("grade") if provider_payload else None,
                "title_zh": _json_dict(agent_brief.get("brief_json")).get("title_zh"),
                "summary_zh": _json_dict(agent_brief.get("brief_json")).get("summary_zh"),
                "method": "news_item_brief",
            },
            provider_signal=provider_payload,
            agent_brief=agent_brief,
        )
    if provider_payload:
        return _signal_with_independent_state(
            provider_payload,
            provider_signal=provider_payload,
            agent_brief=agent_brief,
        )
    return _signal_with_independent_state(
        _signal_from_agent_brief(agent_brief),
        provider_signal=None,
        agent_brief=agent_brief,
    )


def _provider_signal_payload(provider_signal: Mapping[str, Any]) -> dict[str, Any] | None:
    if provider_signal.get("source") != "provider":
        return None
    return {
        key: value
        for key, value in {
            "source": "provider",
            "provider": provider_signal.get("provider") or "opennews",
            "status": provider_signal.get("status") or "partial",
            "direction": provider_signal.get("direction") or "neutral",
            "label_zh": provider_signal.get("label_zh")
            or _direction_label(str(provider_signal.get("direction") or "neutral")),
            "signal": provider_signal.get("signal"),
            "score": _optional_int(provider_signal.get("score")),
            "grade": provider_signal.get("grade"),
            "summary_zh": provider_signal.get("summary_zh"),
            "summary_en": provider_signal.get("summary_en"),
            "method": provider_signal.get("method") or "opennews.provider_signal",
        }.items()
        if value is not None
    }


def _signal_with_independent_state(
    signal: Mapping[str, Any],
    *,
    provider_signal: Mapping[str, Any] | None,
    agent_brief: Mapping[str, Any],
) -> dict[str, Any]:
    agent_status = str(agent_brief.get("status") or "pending")
    provider_score = _optional_int(provider_signal.get("score")) if provider_signal else None
    payload = {
        **signal,
        "provider_signal": dict(provider_signal) if provider_signal else None,
        "alert_eligibility": {
            key: value
            for key, value in {
                "agent_status": agent_status,
                "decision_class": agent_brief.get("decision_class"),
                "provider_status": provider_signal.get("status") if provider_signal else None,
                "provider_score": provider_score,
                "eligible": _alert_eligible(agent_brief=agent_brief, provider_score=provider_score),
            }.items()
            if value is not None
        },
    }
    return {key: value for key, value in payload.items() if value is not None}


def _alert_eligible(*, agent_brief: Mapping[str, Any], provider_score: int | None) -> bool:
    if str(agent_brief.get("status") or "") == "ready" and str(agent_brief.get("decision_class") or "") in {
        "driver",
        "watch",
    }:
        return True
    return provider_score is not None and provider_score >= 70


def _token_lanes_from_mentions(
    *,
    token_mentions: Sequence[Any],
    provider_token_impacts: Sequence[Any],
) -> list[dict[str, Any]]:
    impacts_by_symbol = {
        str(impact.get("symbol") or "").upper(): impact
        for impact in (_json_dict(value) for value in provider_token_impacts)
        if str(impact.get("symbol") or "")
    }
    lanes: list[dict[str, Any]] = []
    for mention in token_mentions:
        payload = _json_dict(mention)
        status = str(payload.get("resolution_status") or "")
        lane = {
            "lane": _token_lane_name(status),
            "resolution_status": status,
            "symbol": payload.get("display_symbol") or payload.get("observed_symbol") or payload.get("symbol"),
            "target_type": payload.get("target_type"),
            "target_id": payload.get("target_id"),
            "display_name": payload.get("display_name"),
            "reason_codes": _json_list(payload.get("reason_codes_json")),
            "candidate_targets": _json_list(payload.get("candidate_targets_json")),
        }
        impact = impacts_by_symbol.get(str(lane.get("symbol") or "").upper())
        if impact:
            lane.update(
                {
                    "provider_signal": impact.get("signal"),
                    "provider_score": _optional_int(impact.get("score")),
                    "provider_grade": impact.get("grade"),
                    "market_type": impact.get("market_type"),
                }
            )
        lanes.append({key: value for key, value in lane.items() if value is not None})
    return lanes


def _token_lane_name(status: str) -> str:
    if status in {"exact_address", "known_symbol", "unique_by_context", "resolved"}:
        return "resolved"
    if status in {"non_crypto", "nil"}:
        return "ignored"
    return "attention"


def _fact_lane_from_candidate(candidate: Any) -> dict[str, Any]:
    payload = _json_dict(candidate)
    return {
        "fact_candidate_id": payload.get("fact_candidate_id"),
        "event_type": payload.get("event_type"),
        "claim": payload.get("claim"),
        "realis": payload.get("realis"),
        "status": payload.get("validation_status") or payload.get("status"),
        "rejection_reasons": _json_list(payload.get("rejection_reasons_json")),
        "affected_targets": _json_list(payload.get("affected_targets_json")),
    }


def _direction_label(direction: str) -> str:
    if direction == "bullish":
        return "利好"
    if direction == "bearish":
        return "利空"
    return "中性"


def _entity_payload(entity: Any) -> dict[str, Any]:
    payload = _object_payload(entity)
    return {
        "entity_id": str(payload["entity_id"]),
        "news_item_id": str(payload["news_item_id"]),
        "entity_type": str(payload["entity_type"]),
        "raw_value": str(payload["raw_value"]),
        "normalized_value": str(payload["normalized_value"]),
        "chain": payload.get("chain"),
        "span_start": int(payload["span_start"]),
        "span_end": int(payload["span_end"]),
        "text_surface": str(payload["text_surface"]),
        "confidence": float(payload["confidence"]),
        "extraction_policy_version": str(payload["extraction_policy_version"]),
        "created_at_ms": int(payload["created_at_ms"]),
    }


def _mention_payload(mention: Any) -> dict[str, Any]:
    payload = _object_payload(mention)
    return {
        "mention_id": str(payload["mention_id"]),
        "news_item_id": str(payload["news_item_id"]),
        "entity_id": payload.get("entity_id"),
        "observed_symbol": payload.get("observed_symbol"),
        "chain_id": payload.get("chain_id"),
        "address": payload.get("address"),
        "resolution_status": str(payload["resolution_status"]),
        "target_type": payload.get("target_type"),
        "target_id": payload.get("target_id"),
        "display_symbol": payload.get("display_symbol"),
        "display_name": payload.get("display_name"),
        "reason_codes_json": _json(_json_list(payload.get("reason_codes"))),
        "candidate_targets_json": _json(_json_list(payload.get("candidate_targets"))),
        "evidence_strength": str(payload["evidence_strength"]),
        "confidence": float(payload["confidence"]),
        "created_at_ms": int(payload["created_at_ms"]),
    }


def _fact_payload(candidate: Any) -> dict[str, Any]:
    payload = _object_payload(candidate)
    return {
        "fact_candidate_id": str(payload["fact_candidate_id"]),
        "news_item_id": str(payload["news_item_id"]),
        "event_type": str(payload["event_type"]),
        "claim": str(payload["claim"]),
        "realis": str(payload["realis"]),
        "evidence_quote": str(payload["evidence_quote"]),
        "evidence_span_start": int(payload["evidence_span_start"]),
        "evidence_span_end": int(payload["evidence_span_end"]),
        "source_role": str(payload["source_role"]),
        "required_slots_json": _json(_json_dict(payload.get("required_slots"))),
        "affected_targets_json": _json(_json_list(payload.get("affected_targets"))),
        "validation_status": str(payload["validation_status"]),
        "rejection_reasons_json": _json(_json_list(payload.get("rejection_reasons"))),
        "extraction_method": str(payload["extraction_method"]),
        "policy_version": str(payload["policy_version"]),
        "created_at_ms": int(payload["created_at_ms"]),
        "updated_at_ms": int(payload["updated_at_ms"]),
    }


def _agent_run_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "run_id": str(payload["run_id"]),
        "news_item_id": str(payload["news_item_id"]),
        "provider": str(payload["provider"]),
        "model": str(payload["model"]),
        "backend": str(payload.get("backend") or "litellm_sdk"),
        "execution_trace_id": payload.get("execution_trace_id"),
        "workflow_name": str(payload["workflow_name"]),
        "agent_name": str(payload["agent_name"]),
        "lane": str(payload["lane"]),
        "artifact_version_hash": str(payload["artifact_version_hash"]),
        "prompt_version": str(payload["prompt_version"]),
        "schema_version": str(payload["schema_version"]),
        "validator_version": str(payload["validator_version"]),
        "guardrail_version": str(payload["guardrail_version"]),
        "input_hash": str(payload["input_hash"]),
        "output_hash": payload.get("output_hash"),
        "execution_started": bool(payload.get("execution_started", False)),
        "status": str(payload["status"]),
        "outcome": str(payload["outcome"]),
        "error_class": payload.get("error_class"),
        "error": _compact_error(payload.get("error")),
        "request_json": _json(payload.get("request_json") or {}),
        "response_json": _json(payload["response_json"]) if payload.get("response_json") is not None else None,
        "validation_errors_json": _json(payload.get("validation_errors_json") or []),
        "trace_metadata_json": _json(payload.get("trace_metadata_json") or {}),
        "usage_json": _json(payload.get("usage_json") or {}),
        "latency_ms": int(payload.get("latency_ms") or 0),
        "started_at_ms": int(payload["started_at_ms"]),
        "finished_at_ms": int(payload["finished_at_ms"]),
        "created_at_ms": int(payload["created_at_ms"]),
    }


def _agent_brief_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "news_item_id": str(payload["news_item_id"]),
        "agent_run_id": str(payload["agent_run_id"]),
        "status": str(payload["status"]),
        "direction": str(payload["direction"]),
        "decision_class": str(payload["decision_class"]),
        "brief_json": _json(payload.get("brief_json") or {}),
        "input_hash": str(payload["input_hash"]),
        "artifact_version_hash": str(payload["artifact_version_hash"]),
        "prompt_version": str(payload["prompt_version"]),
        "schema_version": str(payload["schema_version"]),
        "validator_version": str(payload["validator_version"]),
        "computed_at_ms": int(payload["computed_at_ms"]),
        "created_at_ms": int(payload["created_at_ms"]),
        "updated_at_ms": int(payload["updated_at_ms"]),
    }


def _source_quality_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "row_id": str(row["row_id"]),
        "source_id": str(row["source_id"]),
        "window": str(row["window"]),
        "computed_at_ms": int(row["computed_at_ms"]),
        "fetch_success_rate": _optional_float(row.get("fetch_success_rate")),
        "items_fetched": int(row.get("items_fetched") or 0),
        "items_inserted": int(row.get("items_inserted") or 0),
        "duplicate_rate": _optional_float(row.get("duplicate_rate")),
        "process_success_rate": _optional_float(row.get("process_success_rate")),
        "resolved_token_rate": _optional_float(row.get("resolved_token_rate")),
        "attention_rate": _optional_float(row.get("attention_rate")),
        "accepted_fact_rate": _optional_float(row.get("accepted_fact_rate")),
        "brief_ready_rate": _optional_float(row.get("brief_ready_rate")),
        "median_lag_ms": int(row["median_lag_ms"]) if row.get("median_lag_ms") is not None else None,
        "quality_score": _optional_float(row.get("quality_score")),
        "diagnostics_json": _json(row.get("diagnostics_json") or {}),
        "projection_version": str(row["projection_version"]),
    }


def _source_status_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    latest_quality = _json_dict(row.get("latest_quality_json"))
    quality_payload = _source_quality_read_payload(latest_quality) if latest_quality else None
    latest_item_published_at_ms = _optional_int(row.get("latest_item_published_at_ms"))
    latest_item_fetched_at_ms = _optional_int(row.get("latest_item_fetched_at_ms"))
    latest_context_seen_at_ms = _optional_int(row.get("latest_context_seen_at_ms"))
    context_item_count = int(row.get("context_item_count") or 0)
    last_success_at_ms = _optional_int(row.get("last_success_at_ms"))
    last_seen_at_ms = _max_optional_int(
        latest_item_fetched_at_ms,
        latest_context_seen_at_ms,
        last_success_at_ms,
    )
    return {
        "source_id": str(row["source_id"]),
        "provider_type": str(row.get("provider_type") or ""),
        "source_domain": str(row.get("source_domain") or ""),
        "source_name": str(row.get("source_name") or ""),
        "source_role": str(row.get("source_role") or ""),
        "trust_tier": str(row.get("trust_tier") or ""),
        "coverage_tags": _json_list(row.get("coverage_tags_json")),
        "source_quality_status": str(row.get("source_quality_status") or "unknown"),
        "quality": quality_payload,
        "enabled": bool(row.get("enabled")),
        "managed_by_config": bool(row.get("managed_by_config")),
        "refresh_interval_seconds": int(row.get("refresh_interval_seconds") or 0),
        "item_count": int(row.get("item_count") or 0),
        "context_item_count": context_item_count,
        "latest_item_published_at_ms": latest_item_published_at_ms,
        "latest_item_fetched_at_ms": latest_item_fetched_at_ms,
        "latest_context_seen_at_ms": latest_context_seen_at_ms,
        "last_seen_at_ms": last_seen_at_ms,
        "latest_fetch_run": _latest_fetch_run_payload(row.get("latest_fetch_run_json")),
        "latest_quality_counts": _latest_quality_counts(latest_quality),
        "sync_high_watermark_ms": int(row.get("sync_high_watermark_ms") or 0),
        "sync_overlap_ms": int(row.get("sync_overlap_ms") or 0),
        "sync_diagnostics": _json_dict(row.get("sync_diagnostics_json")),
        "dedup_diagnostics": _json_dict(row.get("dedup_diagnostics_json")),
        "provider_health": _provider_health_payload(
            row=row,
            quality_payload=quality_payload,
            last_seen_at_ms=last_seen_at_ms,
        ),
        "provider_capability_tags": _provider_capability_tags(row=row, context_item_count=context_item_count),
        "last_fetch_at_ms": _optional_int(row.get("last_fetch_at_ms")),
        "last_success_at_ms": last_success_at_ms,
        "next_fetch_after_ms": int(row.get("next_fetch_after_ms") or 0),
        "consecutive_failures": int(row.get("consecutive_failures") or 0),
        "last_error": _compact_error(row.get("last_error")),
    }


def _source_quality_read_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "row_id": str(row["row_id"]),
        "source_id": str(row["source_id"]),
        "window": str(row["window"]),
        "computed_at_ms": int(row["computed_at_ms"]),
        "fetch_success_rate": _optional_float(row.get("fetch_success_rate")),
        "items_fetched": int(row.get("items_fetched") or 0),
        "items_inserted": int(row.get("items_inserted") or 0),
        "duplicate_rate": _optional_float(row.get("duplicate_rate")),
        "process_success_rate": _optional_float(row.get("process_success_rate")),
        "resolved_token_rate": _optional_float(row.get("resolved_token_rate")),
        "attention_rate": _optional_float(row.get("attention_rate")),
        "accepted_fact_rate": _optional_float(row.get("accepted_fact_rate")),
        "brief_ready_rate": _optional_float(row.get("brief_ready_rate")),
        "median_lag_ms": int(row["median_lag_ms"]) if row.get("median_lag_ms") is not None else None,
        "quality_score": _optional_float(row.get("quality_score")),
        "diagnostics_json": _json_dict(row.get("diagnostics_json")),
        "projection_version": str(row["projection_version"]),
    }


def _source_material_changed(existing: Mapping[str, Any], payload: Mapping[str, Any]) -> bool:
    fields = (
        "provider_type",
        "feed_url",
        "source_domain",
        "source_name",
        "source_role",
        "trust_tier",
        "managed_by_config",
        "enabled",
        "refresh_interval_seconds",
        "coverage_tags_json",
        "asset_universe_json",
        "authority_scope_json",
        "fetch_policy_json",
        "context_policy_json",
        "cost_policy_json",
    )
    for field in fields:
        if _comparable_source_value(existing.get(field)) != _comparable_source_value(payload.get(field)):
            return True
    return False


def _provider_article_id(
    *,
    explicit: str | None,
    provider_type: str,
    source_item_key: str,
    payload: Mapping[str, Any],
) -> str:
    if explicit is not None:
        return str(explicit).strip()
    for field_name in ("provider_article_id", "article_id", "id"):
        value = str(payload.get(field_name) or "").strip()
        if value:
            return value
    if str(provider_type or "").strip().lower() == "opennews":
        return ""
    return str(source_item_key or "").strip()


def _provider_payload_status(*, explicit: str | None, payload: Mapping[str, Any]) -> str:
    normalized = str(explicit or "").strip().lower()
    if normalized in {"partial", "ready"}:
        return normalized
    provider_signal = _json_dict(payload.get("provider_signal"))
    if str(provider_signal.get("status") or "").strip().lower() == "ready":
        return "ready"
    ai_rating = _json_dict(payload.get("aiRating"))
    if str(ai_rating.get("status") or "").strip().lower() == "done":
        return "ready"
    return "partial"


def _merge_provider_payload_status(*, existing: str, incoming: str) -> str:
    if str(existing or "").strip().lower() == "ready":
        return "ready"
    if str(incoming or "").strip().lower() == "ready":
        return "ready"
    return "partial"


def _provider_published_at_ms(payload: Mapping[str, Any]) -> int | None:
    for field_name in ("published_at_ms", "published_ms", "ts"):
        value = _numeric_payload_ms(payload.get(field_name))
        if value is not None:
            return value
    return None


def _numeric_payload_ms(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    raw = str(value).strip()
    if not raw.isdigit():
        return None
    return int(raw)


def _representative_payload_should_replace(existing: Mapping[str, Any], incoming: Mapping[str, Any]) -> bool:
    existing_ready = _representative_payload_ready(existing)
    incoming_ready = _representative_payload_ready(incoming)
    if incoming_ready != existing_ready:
        return incoming_ready

    existing_url_rank = _representative_url_rank(existing.get("canonical_url"))
    incoming_url_rank = _representative_url_rank(incoming.get("canonical_url"))
    if incoming_url_rank != existing_url_rank:
        return incoming_url_rank > existing_url_rank

    if str(incoming.get("provider_item_id") or "") == str(existing.get("provider_item_id") or ""):
        return True

    return _representative_tie_breaker(incoming) < _representative_tie_breaker(existing)


def _representative_payload_ready(payload: Mapping[str, Any]) -> bool:
    provider_signal = _json_dict(payload.get("provider_signal_json"))
    signal_status = str(provider_signal.get("status") or "").strip().lower()
    if signal_status:
        return signal_status == "ready"
    return str(payload.get("provider_payload_status") or "").strip().lower() == "ready"


def _representative_url_rank(value: Any) -> int:
    canonical_url = str(value or "").strip()
    if not canonical_url or canonical_url.startswith("opennews://item/"):
        return 0
    kind = url_identity_kind(canonical_url)
    if kind == "article":
        return 2
    if canonical_url.startswith(("http://", "https://")):
        return 1
    return 0


def _representative_tie_breaker(payload: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(payload.get("provider_article_key") or ""),
        str(payload.get("source_id") or ""),
        _representative_payload_hash(payload),
        str(payload.get("provider_item_id") or ""),
    )


def _representative_payload_hash(payload: Mapping[str, Any]) -> str:
    material = {
        "canonical_url": str(payload.get("canonical_url") or ""),
        "title": str(payload.get("title") or ""),
        "summary": str(payload.get("summary") or ""),
        "body_text": str(payload.get("body_text") or ""),
    }
    return hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _news_item_content_changed(existing: Mapping[str, Any], payload: Mapping[str, Any]) -> bool:
    fields = (
        "canonical_url",
        "title",
        "summary",
        "body_text",
        "language",
        "published_at_ms",
        "content_hash",
        "title_fingerprint",
    )
    for field_name in fields:
        if existing.get(field_name) != payload.get(field_name):
            return True
    return _json_dict(existing.get("provider_signal_json")) != _json_dict(
        payload.get("provider_signal_json")
    ) or _json_list(existing.get("provider_token_impacts_json")) != _json_list(
        payload.get("provider_token_impacts_json")
    )


def _news_item_aggregate_changed(existing: Mapping[str, Any], updated: Mapping[str, Any]) -> bool:
    return (
        int(existing.get("duplicate_observation_count") or 0) != int(updated.get("duplicate_observation_count") or 0)
        or _json_list(existing.get("source_ids_json")) != _json_list(updated.get("source_ids_json"))
        or _json_list(existing.get("source_domains_json")) != _json_list(updated.get("source_domains_json"))
        or _json_list(existing.get("provider_article_keys_json"))
        != _json_list(updated.get("provider_article_keys_json"))
    )


def _news_item_edge_changed(existing: Mapping[str, Any], payload: Mapping[str, Any]) -> bool:
    fields = (
        "news_item_id",
        "source_id",
        "provider_article_key",
        "match_type",
        "match_confidence",
        "policy_version",
    )
    for field_name in fields:
        if existing.get(field_name) != payload.get(field_name):
            return True
    return _json_dict(existing.get("evidence_json")) != _json_dict(payload.get("evidence_json"))


def _comparable_source_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _comparable_source_value(item) for key, item in sorted(value.items())}
    if isinstance(value, list | tuple | set):
        return [_comparable_source_value(item) for item in value]
    return value


def _object_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    dump = getattr(value, "model_dump", None)
    if dump is not None:
        return dict(dump())
    if hasattr(value, "__dict__"):
        return dict(vars(value))
    return {name: getattr(value, name) for name in getattr(value, "__slots__", ()) if hasattr(value, name)}


def _public_observation_edge_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    allowed = (
        "news_item_id",
        "source_id",
        "source_domain",
        "source_name",
        "source_role",
        "trust_tier",
        "enabled",
        "match_type",
        "match_confidence",
        "policy_version",
        "first_seen_at_ms",
        "last_seen_at_ms",
        "provider_payload_status",
        "provider_published_at_ms",
        "provider_observed_at_ms",
    )
    return {key: row.get(key) for key in allowed if key in row}


def _public_news_item_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    allowed = (
        "news_item_id",
        "source_id",
        "source_domain",
        "canonical_url",
        "title",
        "summary",
        "body_text",
        "language",
        "published_at_ms",
        "fetched_at_ms",
        "lifecycle_status",
        "content_class",
        "processed_at_ms",
        "processing_error",
        "created_at_ms",
        "updated_at_ms",
        "duplicate_observation_count",
    )
    payload = {key: row.get(key) for key in allowed if key in row}
    payload["canonical_url"] = _public_url(payload.get("canonical_url"))
    return payload


def _public_context_item_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    allowed = (
        "context_item_id",
        "source_id",
        "parent_news_item_id",
        "context_type",
        "author",
        "canonical_url",
        "body_text",
        "published_at_ms",
        "engagement_json",
        "created_at_ms",
    )
    payload = {key: row.get(key) for key in allowed if key in row}
    payload["canonical_url"] = _public_url(payload.get("canonical_url"))
    return payload


def _public_provider_observation_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    allowed = (
        "source_id",
        "canonical_url",
        "fetched_at_ms",
        "provider_payload_status",
        "provider_published_at_ms",
        "provider_observed_at_ms",
        "source_domain",
        "source_name",
        "source_role",
        "trust_tier",
        "enabled",
    )
    payload = {key: row.get(key) for key in allowed if key in row}
    payload["canonical_url"] = _public_url(payload.get("canonical_url"))
    return payload


def _public_source_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    allowed = (
        "source_id",
        "provider_type",
        "source_domain",
        "source_name",
        "source_role",
        "trust_tier",
        "coverage_tags_json",
        "asset_universe_json",
        "authority_scope_json",
        "source_quality_status",
        "enabled",
        "managed_by_config",
        "refresh_interval_seconds",
        "created_at_ms",
        "updated_at_ms",
    )
    payload = {key: row.get(key) for key in allowed if key in row}
    if "coverage_tags_json" in payload:
        payload["coverage_tags"] = _json_list(payload.pop("coverage_tags_json"))
    if "asset_universe_json" in payload:
        payload["asset_universe"] = _json_list(payload.pop("asset_universe_json"))
    if "authority_scope_json" in payload:
        payload["authority_scope"] = _json_dict(payload.pop("authority_scope_json"))
    return payload


def _public_fetch_run_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    allowed = (
        "source_id",
        "status",
        "started_at_ms",
        "finished_at_ms",
        "fetched_count",
        "inserted_count",
        "updated_count",
        "duplicate_count",
        "http_status",
        "error",
        "created_at_ms",
    )
    payload = {key: row.get(key) for key in allowed if key in row}
    if "error" in payload:
        payload["error"] = _compact_error(payload.get("error"))
    return payload


def _public_agent_brief_payload(value: Any) -> dict[str, Any]:
    payload = _json_dict(value)
    brief_json = _json_dict(payload.get("brief_json"))
    if not payload:
        return {"status": "pending", "brief_json": {}}
    allowed = (
        "status",
        "direction",
        "decision_class",
        "title_zh",
        "summary_zh",
        "market_read_zh",
        "impact_zh",
        "watch_items_zh",
        "confidence",
        "prompt_version",
        "schema_version",
        "computed_at_ms",
    )
    public_payload = {key: payload.get(key) for key in allowed if key in payload}
    public_payload["status"] = str(public_payload.get("status") or "pending")
    public_payload["brief_json"] = brief_json
    if "title_zh" not in public_payload and brief_json.get("title_zh"):
        public_payload["title_zh"] = brief_json.get("title_zh")
    return public_payload


def _public_agent_run_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    allowed = (
        "status",
        "outcome",
        "execution_started",
        "model",
        "provider",
        "lane",
        "error_class",
        "error",
        "started_at_ms",
        "finished_at_ms",
    )
    payload = {key: row.get(key) for key in allowed if key in row}
    if "error" in payload:
        payload["error"] = _compact_error(payload.get("error"))
    return payload


def _public_url(value: Any) -> str:
    url = str(value or "").strip()
    if url.startswith(("http://", "https://")):
        return url
    return ""


def _json_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _quoted_constraint_values(constraint_def: str) -> tuple[str, ...]:
    values: list[str] = []
    for match in _CHECK_QUOTED_VALUE_RE.finditer(str(constraint_def or "")):
        value = match.group(1).replace("''", "'")
        if value:
            values.append(value)
    return tuple(dict.fromkeys(values))


def _json_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _first_int(*values: int | None) -> int:
    for value in values:
        if value is not None:
            return max(0, int(value))
    return 0


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _positive_optional_int(value: Any) -> int | None:
    item = _optional_int(value)
    if item is None or item <= 0:
        return None
    return item


def _max_optional_int(*values: int | None) -> int | None:
    normalized = [int(value) for value in values if value is not None]
    if not normalized:
        return None
    return max(normalized)


def _latest_fetch_run_payload(value: Any) -> dict[str, Any] | None:
    row = _json_dict(value)
    if not row:
        return None
    return {
        "status": str(row.get("status") or "unknown"),
        "started_at_ms": _optional_int(row.get("started_at_ms")),
        "finished_at_ms": _positive_optional_int(row.get("finished_at_ms")),
        "http_status": _optional_int(row.get("http_status")),
        "fetched_count": int(row.get("fetched_count") or 0),
        "inserted_count": int(row.get("inserted_count") or 0),
        "updated_count": int(row.get("updated_count") or 0),
        "duplicate_count": int(row.get("duplicate_count") or 0),
        "error": _compact_error(row.get("error")),
    }


def _latest_quality_counts(latest_quality: Mapping[str, Any]) -> dict[str, Any]:
    diagnostics = _json_dict(latest_quality.get("diagnostics_json"))
    counts = _json_dict(diagnostics.get("counts"))
    return {str(key): value for key, value in counts.items()}


def _provider_health_payload(
    *,
    row: Mapping[str, Any],
    quality_payload: Mapping[str, Any] | None,
    last_seen_at_ms: int | None,
) -> dict[str, Any]:
    consecutive_failures = int(row.get("consecutive_failures") or 0)
    last_error = _compact_error(row.get("last_error"))
    last_success_at_ms = _optional_int(row.get("last_success_at_ms"))
    if not bool(row.get("enabled")):
        status = "disabled"
        reason = "source_disabled"
    elif consecutive_failures > 0:
        status = "failing"
        reason = "consecutive_failures"
    else:
        quality_status = str(row.get("source_quality_status") or "unknown")
        if quality_payload:
            quality_status = str(_json_dict(quality_payload.get("diagnostics_json")).get("status") or quality_status)
        if quality_status in {"healthy", "watch", "degraded", "poor"}:
            status = quality_status
            reason = "quality_status"
        elif last_seen_at_ms is not None:
            status = "unknown"
            reason = "observed_without_quality"
        else:
            status = "unknown"
            reason = "no_observations"
    return {
        "status": status,
        "reason": reason,
        "last_error": last_error,
        "consecutive_failures": consecutive_failures,
        "last_success_at_ms": last_success_at_ms,
        "last_seen_at_ms": last_seen_at_ms,
    }


def _provider_capability_tags(*, row: Mapping[str, Any], context_item_count: int) -> list[str]:
    provider_type = str(row.get("provider_type") or "").strip().lower()
    source_role = str(row.get("source_role") or "").strip().lower()
    trust_tier = str(row.get("trust_tier") or "").strip().lower()
    tags: list[str] = []
    if provider_type in {"rss", "atom", "json_feed"}:
        tags.extend(["poll_primary_items", "http_cache"])
    elif provider_type in {"cryptopanic", "manual_api", "openbb", "github", "ossinsight"}:
        tags.extend(["poll_primary_items", "api_backed"])
    elif provider_type in {"twitter_profile", "twitter_thread_context", "reddit", "telegram_public", "hackernews"}:
        tags.extend(["poll_primary_items", "browser_backed"])
    else:
        tags.append("poll_primary_items")
    if context_item_count > 0 or _context_policy_enabled(row.get("context_policy_json")):
        tags.append("context_items")
    if source_role.startswith("official_") or trust_tier == "official":
        tags.append("official_source")
    if trust_tier in {"official", "high"}:
        tags.append("high_trust")
    return list(dict.fromkeys(tags))


def _context_policy_enabled(value: Any) -> bool:
    policy = _json_dict(value)
    if not policy:
        return False
    if "enabled" in policy:
        return bool(policy.get("enabled"))
    if "disabled" in policy:
        return not bool(policy.get("disabled"))
    return any(bool(item) for item in policy.values())


def _json(value: Any) -> Jsonb:
    return Jsonb(value, dumps=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True))


def _stable_payload_hash(payload: Mapping[str, Any], *, exclude: set[str]) -> str:
    normalized = {str(key): _stable_json_value(value) for key, value in payload.items() if str(key) not in exclude}
    encoded = json.dumps(
        postgres_safe_json(normalized),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _stable_json_value(value: Any) -> Any:
    if isinstance(value, Jsonb):
        return _stable_json_value(value.obj)
    if isinstance(value, Mapping):
        return {str(key): _stable_json_value(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_stable_json_value(item) for item in value]
    return value


def _compact_error(error: str | None) -> str | None:
    if not error:
        return None
    return _redact_error_text(str(error))[:2_000]


def _redact_error_text(value: str) -> str:
    text = _URL_USERINFO_RE.sub(rf"\1{_REDACTED}@", value)
    text = _SECRET_HEADER_RE.sub(lambda match: f"{match.group(1)}: {_REDACTED}", text)
    text = _BEARER_RE.sub(f"Bearer {_REDACTED}", text)
    text = _SECRET_QUERY_RE.sub(rf"\1{_REDACTED}", text)
    text = _SECRET_QUOTED_KEY_VALUE_RE.sub(
        lambda match: f"{match.group(1)}{match.group(2)}{_REDACTED}{match.group(2)}",
        text,
    )
    return _SECRET_KEY_VALUE_RE.sub(rf"\1\2{_REDACTED}\3", text)
