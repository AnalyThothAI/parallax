from __future__ import annotations

import json
import uuid
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from psycopg.types.json import Jsonb

from gmgn_twitter_intel.domains.news_intel._constants import NEWS_PAGE_PROJECTION_VERSION
from gmgn_twitter_intel.domains.news_intel.types import NewsSourceConfig
from gmgn_twitter_intel.domains.news_intel.types.source_classification import normalize_string_tuple

_DEFAULT_SOURCE_CLAIM_LEASE_MS = 60_000


class NewsRepository:
    def __init__(self, conn: Any):
        self.conn = conn

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
                source_id,
                provider_type,
                feed_url,
                source_domain,
                source_name,
                source_role,
                trust_tier,
                bool(managed_by_config),
                bool(enabled),
                max(1, int(refresh_interval_seconds)),
                _json(list(normalize_string_tuple(coverage_tags))),
                _json(list(normalize_string_tuple(asset_universe))),
                _json(_json_dict(authority_scope)),
                _json(_json_dict(fetch_policy)),
                _json(_json_dict(context_policy)),
                _json(_json_dict(cost_policy)),
                int(now_ms),
                int(now_ms),
            ),
        ).fetchone()
        if commit:
            self.conn.commit()
        return dict(row)

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
        self.disable_unconfigured_sources(
            configured_source_ids=configured_source_ids,
            now_ms=now_ms,
            commit=False,
        )
        if commit:
            self.conn.commit()
        return rows

    def disable_unconfigured_sources(
        self,
        *,
        configured_source_ids: Sequence[str] | None = None,
        active_source_ids: Sequence[str] | None = None,
        now_ms: int,
        commit: bool = True,
    ) -> int:
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
            """,
            (int(now_ms), normalized_ids),
        )
        if commit:
            self.conn.commit()
        return int(cursor.rowcount or 0)

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
        fetched_at_ms: int,
        commit: bool = True,
    ) -> dict[str, Any]:
        payload = dict(raw_payload if raw_payload is not None else raw_payload_json or {})
        existing = self.conn.execute(
            """
            SELECT *
              FROM news_provider_items
             WHERE source_id = %s
               AND source_item_key = %s
            """,
            (source_id, source_item_key),
        ).fetchone()
        status = "inserted"
        if existing is not None:
            status = "duplicate"
            if (
                existing["payload_hash"] != payload_hash
                or existing["canonical_url"] != canonical_url
                or dict(existing["raw_payload_json"]) != payload
            ):
                status = "updated"
        provider_item_id = (
            str(existing["provider_item_id"]) if existing is not None else f"news-provider-item-{uuid.uuid4().hex}"
        )
        row = self.conn.execute(
            """
            INSERT INTO news_provider_items (
              provider_item_id, source_id, fetch_run_id, source_item_key, canonical_url,
              payload_hash, raw_payload_json, fetched_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (source_id, source_item_key) DO UPDATE SET
              fetch_run_id = EXCLUDED.fetch_run_id,
              canonical_url = EXCLUDED.canonical_url,
              payload_hash = EXCLUDED.payload_hash,
              raw_payload_json = EXCLUDED.raw_payload_json,
              fetched_at_ms = EXCLUDED.fetched_at_ms
            RETURNING *
            """,
            (
                provider_item_id,
                source_id,
                fetch_run_id,
                source_item_key,
                canonical_url,
                payload_hash,
                _json(payload),
                int(fetched_at_ms),
            ),
        ).fetchone()
        if commit:
            self.conn.commit()
        return {**dict(row), "status": status}

    def upsert_news_item(
        self,
        *,
        provider_item_id: str,
        source_id: str,
        source_domain: str,
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
        news_item_id: str | None = None,
        commit: bool = True,
    ) -> dict[str, Any]:
        item_published_at_ms = int(published_at_ms if published_at_ms is not None else fetched_at_ms)
        existing = self.conn.execute(
            "SELECT * FROM news_items WHERE provider_item_id = %s",
            (provider_item_id,),
        ).fetchone()
        status = "inserted"
        if existing is not None:
            status = "duplicate"
            if (
                existing["canonical_url"] != canonical_url
                or existing["title"] != title
                or existing["summary"] != summary
                or existing["body_text"] != body_text
                or existing["language"] != language
                or existing["published_at_ms"] != item_published_at_ms
                or existing["content_hash"] != content_hash
                or existing["title_fingerprint"] != title_fingerprint
            ):
                status = "updated"
        item_id = (
            str(existing["news_item_id"])
            if existing is not None
            else news_item_id or f"news-item-{uuid.uuid4().hex}"
        )
        row = self.conn.execute(
            """
            INSERT INTO news_items (
              news_item_id, provider_item_id, source_id, source_domain, canonical_url,
              title, summary, body_text, language, published_at_ms, fetched_at_ms,
              content_hash, title_fingerprint, created_at_ms, updated_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (provider_item_id) DO UPDATE SET
              source_id = EXCLUDED.source_id,
              source_domain = EXCLUDED.source_domain,
              canonical_url = EXCLUDED.canonical_url,
              title = EXCLUDED.title,
              summary = EXCLUDED.summary,
              body_text = EXCLUDED.body_text,
              language = EXCLUDED.language,
              published_at_ms = EXCLUDED.published_at_ms,
              fetched_at_ms = EXCLUDED.fetched_at_ms,
              content_hash = EXCLUDED.content_hash,
              title_fingerprint = EXCLUDED.title_fingerprint,
              lifecycle_status = CASE
                WHEN news_items.content_hash = EXCLUDED.content_hash THEN news_items.lifecycle_status
                ELSE 'raw'
              END,
              updated_at_ms = EXCLUDED.updated_at_ms
            RETURNING *
            """,
            (
                item_id,
                provider_item_id,
                source_id,
                source_domain,
                canonical_url,
                title,
                summary,
                body_text,
                language,
                item_published_at_ms,
                int(fetched_at_ms),
                content_hash,
                title_fingerprint,
                int(now_ms),
                int(now_ms),
            ),
        ).fetchone()
        if status == "updated":
            story_rows = self.conn.execute(
                "SELECT DISTINCT story_id FROM news_story_members WHERE news_item_id = %s",
                (item_id,),
            ).fetchall()
            story_ids = [str(story_row["story_id"]) for story_row in story_rows]
            self.conn.execute("DELETE FROM news_fact_candidates WHERE news_item_id = %s", (item_id,))
            self.conn.execute("DELETE FROM news_token_mentions WHERE news_item_id = %s", (item_id,))
            self.conn.execute("DELETE FROM news_item_entities WHERE news_item_id = %s", (item_id,))
            self.conn.execute("DELETE FROM news_story_members WHERE news_item_id = %s", (item_id,))
            self.conn.execute("DELETE FROM news_page_rows WHERE news_item_id = %s", (item_id,))
            for story_id in story_ids:
                self._refresh_story_counts(story_id=story_id, now_ms=now_ms)
        if commit:
            self.conn.commit()
        return {**dict(row), "status": status}

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
              run_id, news_item_id, provider, model, backend, sdk_trace_id, workflow_name,
              agent_name, lane, artifact_version_hash, prompt_version, schema_version,
              validator_version, guardrail_version, input_hash, output_hash, execution_started,
              status, outcome, error_class, error, request_json, response_json,
              validation_errors_json, trace_metadata_json, usage_json, latency_ms,
              started_at_ms, finished_at_ms, created_at_ms
            )
            VALUES (
              %(run_id)s, %(news_item_id)s, %(provider)s, %(model)s, %(backend)s, %(sdk_trace_id)s,
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
        lane: str | None = None,
        source: str | None = None,
        target: str | None = None,
        provider_type: str | None = None,
        source_role: str | None = None,
        trust_tier: str | None = None,
        coverage_tag: str | None = None,
        content_class: str | None = None,
        q: str | None = None,
    ) -> list[dict[str, Any]]:
        cursor_time, cursor_id = _decode_page_cursor(cursor)
        filters: list[str] = []
        filter_params: list[Any] = []
        if status:
            filters.append("lifecycle_status = %s")
            filter_params.append(str(status))
        if direction:
            filters.append("LOWER(agent_brief_json ->> 'direction') = %s")
            filter_params.append(str(direction).strip().lower())
        if source:
            filters.append("source_domain = %s")
            filter_params.append(str(source))
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
            filters.append(
                """
                EXISTS (
                  SELECT 1
                    FROM jsonb_array_elements(fact_lanes_json) AS fact_lane(value)
                   WHERE fact_lane.value ->> 'content_class' = %s
                      OR fact_lane.value ->> 'event_type' = %s
                )
                """
            )
            normalized_content_class = str(content_class)
            filter_params.extend([normalized_content_class, normalized_content_class])
        if q:
            filters.append("(headline ILIKE %s OR summary ILIKE %s)")
            needle = f"%{str(q).strip()}%"
            filter_params.extend([needle, needle])
        if lane:
            filters.append("(token_lanes_json::text ILIKE %s OR fact_lanes_json::text ILIKE %s)")
            lane_needle = f"%{str(lane).strip()}%"
            filter_params.extend([lane_needle, lane_needle])
        if target:
            filters.append("token_lanes_json::text ILIKE %s")
            filter_params.append(f"%{str(target).strip()}%")
        filter_sql = " AND " + " AND ".join(filters) if filters else ""
        rows = self.conn.execute(
            f"""
            WITH visible_rows AS (
              SELECT
                row_id,
                news_item_id,
                story_id,
                latest_at_ms,
                lifecycle_status,
                headline,
                summary,
                source_domain,
                canonical_url,
                token_lanes_json,
                fact_lanes_json,
                story_json,
                source_json,
                agent_brief_json,
                agent_status,
                agent_status AS agent_brief_status,
                agent_brief_json AS agent_brief,
                agent_brief_computed_at_ms,
                computed_at_ms,
                projection_version
              FROM news_page_rows
              UNION ALL
              SELECT
                items.news_item_id AS row_id,
                items.news_item_id,
                NULL::text AS story_id,
                items.published_at_ms AS latest_at_ms,
                items.lifecycle_status,
                items.title AS headline,
                items.summary,
                items.source_domain,
                items.canonical_url,
                '[]'::jsonb AS token_lanes_json,
                '[]'::jsonb AS fact_lanes_json,
                '{{}}'::jsonb AS story_json,
                jsonb_build_object(
                  'source_id', items.source_id,
                  'provider_type', sources.provider_type,
                  'source_domain', items.source_domain,
                  'source_name', sources.source_name,
                  'source_role', sources.source_role,
                  'trust_tier', sources.trust_tier,
                  'coverage_tags', sources.coverage_tags_json,
                  'source_quality_status', sources.source_quality_status
                ) AS source_json,
                '{{"status":"pending"}}'::jsonb AS agent_brief_json,
                'pending'::text AS agent_status,
                'pending'::text AS agent_brief_status,
                '{{"status":"pending"}}'::jsonb AS agent_brief,
                NULL::bigint AS agent_brief_computed_at_ms,
                items.updated_at_ms AS computed_at_ms,
                %s AS projection_version
              FROM news_items AS items
              JOIN news_sources AS sources ON sources.source_id = items.source_id
              WHERE NOT EXISTS (
                SELECT 1
                  FROM news_page_rows AS projected
                 WHERE projected.news_item_id = items.news_item_id
              )
            )
            SELECT *
              FROM visible_rows
             WHERE (
               %s::bigint IS NULL
               OR (latest_at_ms, row_id) < (%s::bigint, %s::text)
             )
             {filter_sql}
             ORDER BY latest_at_ms DESC, row_id DESC
             LIMIT %s
            """,
            (
                NEWS_PAGE_PROJECTION_VERSION,
                cursor_time,
                cursor_time,
                cursor_id,
                *filter_params,
                max(0, int(limit)),
            ),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_unprocessed_items(self, *, limit: int, now_ms: int, commit: bool = True) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            WITH picked AS (
              SELECT news_item_id
                FROM news_items
               WHERE lifecycle_status IN ('raw', 'process_failed')
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
                   claimed.created_at_ms,
                   claimed.updated_at_ms,
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

    def list_items_missing_story(self, *, limit: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT items.*,
                   COALESCE(
                     jsonb_agg(DISTINCT mentions.target_type || ':' || mentions.target_id)
                       FILTER (WHERE mentions.target_id IS NOT NULL),
                     '[]'::jsonb
                   ) AS token_targets
              FROM news_items AS items
              LEFT JOIN news_story_members AS members ON members.news_item_id = items.news_item_id
              LEFT JOIN news_token_mentions AS mentions ON mentions.news_item_id = items.news_item_id
             WHERE members.news_item_id IS NULL
               AND items.lifecycle_status = 'processed'
             GROUP BY items.news_item_id
             ORDER BY items.published_at_ms ASC, items.news_item_id ASC
             LIMIT %s
            """,
            (max(0, int(limit)),),
        ).fetchall()
        return [dict(row) for row in rows]

    def find_story_candidates_for_item(self, item: Mapping[str, Any], *, limit: int = 25) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT story_id,
                   representative_title,
                   canonical_url,
                   latest_seen_at_ms,
                   token_targets_json AS token_targets,
                   CASE
                     WHEN canonical_url = %s THEN 1.0
                     ELSE similarity(representative_title, %s)
                   END AS candidate_score
              FROM news_story_groups
             WHERE status = 'active'
               AND (
                 canonical_url = %s
                 OR latest_seen_at_ms >= %s
                 OR similarity(representative_title, %s) >= 0.45
               )
             ORDER BY candidate_score DESC, latest_seen_at_ms DESC
             LIMIT %s
            """,
            (
                str(item.get("canonical_url") or ""),
                str(item.get("title_fingerprint") or item.get("title") or ""),
                str(item.get("canonical_url") or ""),
                int(item.get("published_at_ms") or 0) - 24 * 60 * 60 * 1000,
                str(item.get("title_fingerprint") or item.get("title") or ""),
                max(1, int(limit)),
            ),
        ).fetchall()
        return [dict(row) for row in rows]

    def create_story_from_item(
        self,
        *,
        story_id: str,
        item: Mapping[str, Any],
        policy_version: str,
        now_ms: int,
        commit: bool = True,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO news_story_groups (
              story_id, policy_version, representative_title, canonical_url,
              first_seen_at_ms, latest_seen_at_ms, source_count, item_count,
              token_targets_json, status, created_at_ms, updated_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, 0, 0, %s, 'active', %s, %s)
            ON CONFLICT (story_id) DO NOTHING
            """,
            (
                story_id,
                policy_version,
                str(item.get("title") or item.get("representative_title") or ""),
                str(item.get("canonical_url") or "") or None,
                int(item.get("published_at_ms") or now_ms),
                int(item.get("published_at_ms") or now_ms),
                _json(_json_list(item.get("token_targets"))),
                int(now_ms),
                int(now_ms),
            ),
        )
        if commit:
            self.conn.commit()

    def refresh_story_from_member(
        self,
        *,
        story_id: str,
        item: Mapping[str, Any],
        now_ms: int,
        commit: bool = True,
    ) -> None:
        self.conn.execute(
            """
            UPDATE news_story_groups
               SET latest_seen_at_ms = GREATEST(latest_seen_at_ms, %s),
                   updated_at_ms = %s
             WHERE story_id = %s
            """,
            (int(item.get("published_at_ms") or now_ms), int(now_ms), story_id),
        )
        if commit:
            self.conn.commit()

    def add_story_member(
        self,
        *,
        story_id: str,
        news_item_id: str,
        relation: str,
        match_reason: str,
        match_score: float,
        now_ms: int,
        commit: bool = True,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO news_story_members (
              story_id, news_item_id, relation, match_reason, match_score, created_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (story_id, news_item_id) DO UPDATE SET
              relation = EXCLUDED.relation,
              match_reason = EXCLUDED.match_reason,
              match_score = EXCLUDED.match_score
            """,
            (story_id, news_item_id, relation, match_reason, float(match_score), int(now_ms)),
        )
        self._refresh_story_counts(story_id=story_id, now_ms=now_ms)
        if commit:
            self.conn.commit()

    def _refresh_story_counts(self, *, story_id: str, now_ms: int) -> None:
        self.conn.execute(
            """
            WITH requested AS (
              SELECT %s::text AS story_id
            ),
            counts AS (
                SELECT members.story_id,
                       COUNT(DISTINCT items.news_item_id)::int AS item_count,
                       COUNT(DISTINCT items.source_domain)::int AS source_count,
                       COALESCE(
                         jsonb_agg(DISTINCT mentions.target_type || ':' || mentions.target_id)
                           FILTER (WHERE mentions.target_id IS NOT NULL),
                         '[]'::jsonb
                       ) AS token_targets_json,
                       MAX(items.published_at_ms) AS latest_seen_at_ms
                  FROM news_story_members AS members
                  JOIN news_items AS items ON items.news_item_id = members.news_item_id
                  LEFT JOIN news_token_mentions AS mentions ON mentions.news_item_id = items.news_item_id
                 WHERE members.story_id = (SELECT story_id FROM requested)
                 GROUP BY members.story_id
            )
            UPDATE news_story_groups AS story
               SET item_count = COALESCE(counts.item_count, 0),
                   source_count = COALESCE(counts.source_count, 0),
                   token_targets_json = COALESCE(counts.token_targets_json, '[]'::jsonb),
                   latest_seen_at_ms = COALESCE(counts.latest_seen_at_ms, story.latest_seen_at_ms),
                   status = CASE WHEN counts.story_id IS NULL THEN 'stale' ELSE 'active' END,
                   updated_at_ms = %s
              FROM requested
              LEFT JOIN counts ON counts.story_id = requested.story_id
             WHERE story.story_id = requested.story_id
            """,
            (story_id, int(now_ms)),
        )

    def list_items_for_page_projection(self, *, limit: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            WITH candidates AS (
              SELECT items.news_item_id,
                     items.published_at_ms,
                     GREATEST(
                       items.updated_at_ms,
                       COALESCE(stories.updated_at_ms, 0),
                       COALESCE(MAX(mentions.created_at_ms), 0),
                       COALESCE(MAX(facts.updated_at_ms), 0),
                       COALESCE(current_brief.updated_at_ms, 0),
                       COALESCE(current_brief.computed_at_ms, 0)
                     ) AS source_updated_at_ms,
                     page.row_id AS projected_row_id,
                     page.computed_at_ms AS projected_at_ms,
                     page.projection_version AS projected_version
                FROM news_items AS items
                JOIN news_sources AS sources ON sources.source_id = items.source_id
                LEFT JOIN news_story_members AS members ON members.news_item_id = items.news_item_id
                LEFT JOIN news_story_groups AS stories ON stories.story_id = members.story_id
                LEFT JOIN news_token_mentions AS mentions ON mentions.news_item_id = items.news_item_id
                LEFT JOIN news_fact_candidates AS facts ON facts.news_item_id = items.news_item_id
                LEFT JOIN news_item_agent_briefs AS current_brief ON current_brief.news_item_id = items.news_item_id
                LEFT JOIN news_page_rows AS page ON page.news_item_id = items.news_item_id
               GROUP BY items.news_item_id, sources.source_id, stories.story_id, current_brief.news_item_id, page.row_id
              HAVING page.row_id IS NULL
                  OR page.projection_version <> %s
                  OR page.computed_at_ms < GREATEST(
                       items.updated_at_ms,
                       COALESCE(stories.updated_at_ms, 0),
                       COALESCE(MAX(mentions.created_at_ms), 0),
                       COALESCE(MAX(facts.updated_at_ms), 0),
                       COALESCE(current_brief.updated_at_ms, 0),
                       COALESCE(current_brief.computed_at_ms, 0)
                     )
                  OR page.source_json ->> 'source_id' IS DISTINCT FROM items.source_id
                  OR page.source_json ->> 'provider_type' IS DISTINCT FROM sources.provider_type
                  OR page.source_json ->> 'source_domain' IS DISTINCT FROM items.source_domain
                  OR page.source_json ->> 'source_name' IS DISTINCT FROM sources.source_name
                  OR page.source_json ->> 'source_role' IS DISTINCT FROM sources.source_role
                  OR page.source_json ->> 'trust_tier' IS DISTINCT FROM sources.trust_tier
                  OR COALESCE(page.source_json -> 'coverage_tags', '[]'::jsonb) <> sources.coverage_tags_json
                  OR page.source_json ->> 'source_quality_status' IS DISTINCT FROM sources.source_quality_status
               ORDER BY (page.row_id IS NULL) DESC,
                        source_updated_at_ms ASC,
                        items.published_at_ms DESC,
                        items.news_item_id DESC
               LIMIT %s
            )
            SELECT
              to_jsonb(items.*)
                || jsonb_build_object(
                  'provider_type', sources.provider_type,
                  'source_name', sources.source_name,
                  'source_role', sources.source_role,
                  'trust_tier', sources.trust_tier,
                  'coverage_tags_json', sources.coverage_tags_json,
                  'source_quality_status', sources.source_quality_status
                ) AS item,
              CASE WHEN stories.story_id IS NULL THEN NULL ELSE to_jsonb(stories.*) END AS story,
              CASE
                WHEN current_brief.news_item_id IS NULL THEN NULL
                ELSE to_jsonb(current_brief.*)
              END AS current_brief,
              COALESCE(
                jsonb_agg(DISTINCT to_jsonb(mentions.*)) FILTER (WHERE mentions.mention_id IS NOT NULL),
                '[]'::jsonb
              ) AS token_mentions,
              COALESCE(
                jsonb_agg(DISTINCT to_jsonb(facts.*)) FILTER (WHERE facts.fact_candidate_id IS NOT NULL),
                '[]'::jsonb
              ) AS fact_candidates
            FROM candidates
            JOIN news_items AS items ON items.news_item_id = candidates.news_item_id
            JOIN news_sources AS sources ON sources.source_id = items.source_id
            LEFT JOIN news_story_members AS members ON members.news_item_id = items.news_item_id
            LEFT JOIN news_story_groups AS stories ON stories.story_id = members.story_id
            LEFT JOIN news_item_agent_briefs AS current_brief ON current_brief.news_item_id = items.news_item_id
            LEFT JOIN news_token_mentions AS mentions ON mentions.news_item_id = items.news_item_id
            LEFT JOIN news_fact_candidates AS facts ON facts.news_item_id = items.news_item_id
            GROUP BY items.news_item_id, sources.source_id, stories.story_id, current_brief.news_item_id
            ORDER BY MAX(candidates.source_updated_at_ms) ASC,
                     items.published_at_ms DESC,
                     items.news_item_id DESC
            """,
            (NEWS_PAGE_PROJECTION_VERSION, max(0, int(limit))),
        ).fetchall()
        return [
            {
                "item": _json_dict(row["item"]),
                "story": _json_dict(row["story"]) if row["story"] is not None else None,
                "current_brief": _json_dict(row["current_brief"]) if row["current_brief"] is not None else None,
                "token_mentions": _json_list(row["token_mentions"]),
                "fact_candidates": _json_list(row["fact_candidates"]),
            }
            for row in rows
        ]

    def list_items_for_brief(
        self,
        *,
        limit: int,
        now_ms: int,
        backpressure_cooldown_ms: int,
        artifact_version_hash: str,
        max_attempts: int,
    ) -> list[dict[str, Any]]:
        recent_backpressure_after_ms = int(now_ms) - max(1, int(backpressure_cooldown_ms))
        rows = self.conn.execute(
            """
            WITH candidates AS (
              SELECT
                items.news_item_id,
                member.story_id,
                items.published_at_ms,
                GREATEST(
                  items.updated_at_ms,
                  COALESCE(stories.updated_at_ms, 0),
                  COALESCE(mention_updates.updated_at_ms, 0),
                  COALESCE(fact_updates.updated_at_ms, 0),
                  COALESCE(context_updates.updated_at_ms, 0),
                  COALESCE(story_member_updates.updated_at_ms, 0)
                ) AS source_updated_at_ms,
                current_brief.status AS current_status,
                current_brief.computed_at_ms AS current_computed_at_ms,
                current_brief.input_hash AS current_input_hash,
                current_brief.artifact_version_hash AS current_artifact_version_hash,
                COALESCE(started_attempts.attempt_count, 0) AS started_attempt_count,
                (current_brief.news_item_id IS NULL) AS missing_current_brief,
                COALESCE(latest_attempt.backpressure_retry_priority, 0) AS backpressure_retry_priority
              FROM news_items AS items
              LEFT JOIN LATERAL (
                SELECT story_id
                  FROM news_story_members
                 WHERE news_item_id = items.news_item_id
                 ORDER BY created_at_ms DESC, story_id DESC
                 LIMIT 1
              ) AS member ON true
              LEFT JOIN news_story_groups AS stories ON stories.story_id = member.story_id
              LEFT JOIN news_item_agent_briefs AS current_brief
                ON current_brief.news_item_id = items.news_item_id
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
              LEFT JOIN LATERAL (
                SELECT MAX(created_at_ms) AS updated_at_ms
                  FROM news_story_members
                 WHERE story_id = member.story_id
              ) AS story_member_updates ON true
              LEFT JOIN LATERAL (
                SELECT COUNT(*)::int AS attempt_count
                  FROM news_item_agent_runs AS runs
                 WHERE runs.news_item_id = items.news_item_id
                   AND runs.artifact_version_hash = %s
                   AND runs.execution_started = true
              ) AS started_attempts ON true
              LEFT JOIN LATERAL (
                SELECT CASE
                         WHEN runs.execution_started = false
                          AND runs.status = 'backpressure'
                         THEN 1
                         ELSE 0
                       END AS backpressure_retry_priority
                  FROM news_item_agent_runs AS runs
                 WHERE runs.news_item_id = items.news_item_id
                 ORDER BY runs.finished_at_ms DESC, runs.run_id DESC
                 LIMIT 1
              ) AS latest_attempt ON true
              WHERE items.lifecycle_status = 'processed'
                AND NOT EXISTS (
                  SELECT 1
                    FROM news_item_agent_runs AS recent_runs
                   WHERE recent_runs.news_item_id = items.news_item_id
                     AND recent_runs.execution_started = false
                     AND recent_runs.status = 'backpressure'
                     AND recent_runs.finished_at_ms >= %s
                )
                AND (
                  current_brief.news_item_id IS NULL
                  OR current_brief.artifact_version_hash <> %s
                  OR current_brief.computed_at_ms < GREATEST(
                       items.updated_at_ms,
                       COALESCE(stories.updated_at_ms, 0),
                       COALESCE(mention_updates.updated_at_ms, 0),
                       COALESCE(fact_updates.updated_at_ms, 0),
                       COALESCE(context_updates.updated_at_ms, 0),
                       COALESCE(story_member_updates.updated_at_ms, 0)
                     )
                  OR (
                    current_brief.status = 'failed'
                    AND COALESCE(started_attempts.attempt_count, 0) < %s
                  )
                )
              ORDER BY (current_brief.news_item_id IS NULL) DESC,
                       items.published_at_ms DESC,
                       COALESCE(latest_attempt.backpressure_retry_priority, 0) ASC,
                       source_updated_at_ms DESC,
                       items.news_item_id DESC
              LIMIT %s
            )
            SELECT
              to_jsonb(items.*)
                || jsonb_build_object(
                  'source_name', sources.source_name,
                  'source_role', sources.source_role,
                  'trust_tier', sources.trust_tier
                ) AS item,
              CASE WHEN stories.story_id IS NULL THEN NULL ELSE to_jsonb(stories.*) END AS story,
              CASE
                WHEN current_brief.news_item_id IS NULL THEN NULL
                ELSE to_jsonb(current_brief.*)
              END AS current_brief,
              CASE WHEN latest_run.run_id IS NULL THEN NULL ELSE to_jsonb(latest_run.*) END AS latest_run,
              candidates.source_updated_at_ms,
              COALESCE(token_rows.rows, '[]'::jsonb) AS token_mentions,
              COALESCE(fact_rows.rows, '[]'::jsonb) AS fact_candidates,
              COALESCE(context_rows.rows, '[]'::jsonb) AS context_items,
              COALESCE(story_member_rows.rows, '[]'::jsonb) AS story_members
            FROM candidates
            JOIN news_items AS items ON items.news_item_id = candidates.news_item_id
            JOIN news_sources AS sources ON sources.source_id = items.source_id
            LEFT JOIN news_story_groups AS stories ON stories.story_id = candidates.story_id
            LEFT JOIN news_item_agent_briefs AS current_brief ON current_brief.news_item_id = items.news_item_id
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
            LEFT JOIN LATERAL (
              SELECT jsonb_agg(
                       to_jsonb(member_items.*)
                       ORDER BY member_items.published_at_ms DESC, member_items.news_item_id ASC
                     ) AS rows
                FROM news_story_members AS members
                JOIN news_items AS member_items ON member_items.news_item_id = members.news_item_id
               WHERE members.story_id = candidates.story_id
            ) AS story_member_rows ON true
            ORDER BY candidates.missing_current_brief DESC,
                     candidates.published_at_ms DESC,
                     candidates.backpressure_retry_priority ASC,
                     candidates.source_updated_at_ms DESC,
                     items.news_item_id DESC
            """,
            (
                str(artifact_version_hash),
                recent_backpressure_after_ms,
                str(artifact_version_hash),
                max(1, int(max_attempts)),
                max(0, int(limit)),
            ),
        ).fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            item = _json_dict(row["item"])
            context_items = _json_list(row["context_items"])
            item["context_items"] = context_items
            results.append(
                {
                    "item": item,
                    "story": _json_dict(row["story"]) if row["story"] is not None else None,
                    "token_mentions": _json_list(row["token_mentions"]),
                    "fact_candidates": _json_list(row["fact_candidates"]),
                    "context_items": context_items,
                    "story_members": _json_list(row["story_members"]),
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
                         'sdk_trace_id', runs.sdk_trace_id,
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
        story_rows = self.conn.execute(
            """
            SELECT to_jsonb(members.*)
                     || jsonb_build_object(
                       'representative_title', stories.representative_title,
                       'latest_seen_at_ms', stories.latest_seen_at_ms
                     ) AS story_member
              FROM news_story_members AS members
              JOIN news_story_groups AS stories ON stories.story_id = members.story_id
             WHERE members.news_item_id = %s
             ORDER BY members.created_at_ms DESC, members.story_id DESC
            """,
            (news_item_id,),
        ).fetchall()
        context_items = self.list_context_items_for_news_item(news_item_id, limit=25)
        return {
            **_json_dict(row["item"]),
            "source": _json_dict(row["source"]),
            "provider_item": _json_dict(row["provider_item"]),
            "fetch_run": _json_dict(row["fetch_run"]) if row["fetch_run"] is not None else None,
            "agent_brief": _detail_agent_brief(row["agent_brief"]),
            "agent_run": _json_dict(row["agent_run"]) if row["agent_run"] is not None else None,
            "story_members": [_json_dict(story_row["story_member"]) for story_row in story_rows],
            "entities": _json_list(row["entities"]),
            "token_mentions": _json_list(row["token_mentions"]),
            "fact_candidates": _json_list(row["fact_candidates"]),
            "context_items": context_items,
        }

    def get_news_story_detail(self, *, story_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT to_jsonb(stories.*) AS story,
                   COALESCE(
                     jsonb_agg(
                       DISTINCT jsonb_build_object(
                         'news_item_id', items.news_item_id,
                         'headline', items.title,
                         'source_domain', items.source_domain,
                         'canonical_url', items.canonical_url,
                         'published_at_ms', items.published_at_ms,
                         'relation', members.relation,
                         'match_reason', members.match_reason,
                         'match_score', members.match_score
                       )
                     ) FILTER (WHERE items.news_item_id IS NOT NULL),
                     '[]'::jsonb
                   ) AS members
              FROM news_story_groups AS stories
              LEFT JOIN news_story_members AS members ON members.story_id = stories.story_id
              LEFT JOIN news_items AS items ON items.news_item_id = members.news_item_id
             WHERE stories.story_id = %s
             GROUP BY stories.story_id
            """,
            (story_id,),
        ).fetchone()
        if row is None:
            return None
        token_mentions = self.conn.execute(
            """
            SELECT COALESCE(jsonb_agg(DISTINCT to_jsonb(mentions.*)), '[]'::jsonb) AS rows
              FROM news_story_members AS members
              JOIN news_token_mentions AS mentions ON mentions.news_item_id = members.news_item_id
             WHERE members.story_id = %s
            """,
            (story_id,),
        ).fetchone()
        fact_candidates = self.conn.execute(
            """
            SELECT COALESCE(jsonb_agg(DISTINCT to_jsonb(facts.*)), '[]'::jsonb) AS rows
              FROM news_story_members AS members
              JOIN news_fact_candidates AS facts ON facts.news_item_id = members.news_item_id
             WHERE members.story_id = %s
            """,
            (story_id,),
        ).fetchone()
        return {
            **_json_dict(row["story"]),
            "members": _json_list(row["members"]),
            "token_mentions": _json_list(token_mentions["rows"] if token_mentions is not None else []),
            "fact_candidates": _json_list(fact_candidates["rows"] if fact_candidates is not None else []),
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
        return dict(row) if row is not None else None

    def list_source_quality_inputs(
        self,
        *,
        window_ms: int,
        now_ms: int,
    ) -> list[dict[str, Any]]:
        window_start_ms = int(now_ms) - max(1, int(window_ms))
        rows = self.conn.execute(
            """
            WITH source_rows AS (
              SELECT source_id
                FROM news_sources
               ORDER BY enabled DESC, source_id ASC
            ),
            window_items AS (
              SELECT items.*
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
                      ON context_items.parent_news_item_id = items.news_item_id
                   WHERE COALESCE(context_items.published_at_ms, context_items.created_at_ms) >= %s
                     AND COALESCE(context_items.published_at_ms, context_items.created_at_ms) <= %s
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
    ) -> None:
        normalized_status_window = str(status_window).strip().lower() if status_window else None
        for row in rows:
            payload = _source_quality_payload(row)
            self.conn.execute(
                """
                INSERT INTO news_source_quality_rows (
                  row_id, source_id, "window", computed_at_ms, fetch_success_rate,
                  items_fetched, items_inserted, duplicate_rate, process_success_rate,
                  resolved_token_rate, attention_rate, accepted_fact_rate, brief_ready_rate,
                  median_lag_ms, quality_score, diagnostics_json, projection_version
                )
                VALUES (
                  %(row_id)s, %(source_id)s, %(window)s, %(computed_at_ms)s, %(fetch_success_rate)s,
                  %(items_fetched)s, %(items_inserted)s, %(duplicate_rate)s, %(process_success_rate)s,
                  %(resolved_token_rate)s, %(attention_rate)s, %(accepted_fact_rate)s, %(brief_ready_rate)s,
                  %(median_lag_ms)s, %(quality_score)s, %(diagnostics_json)s, %(projection_version)s
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
                  projection_version = EXCLUDED.projection_version
                """,
                payload,
            )
            if normalized_status_window and payload["window"] == normalized_status_window:
                status = _json_dict(row.get("diagnostics_json")).get("status")
                self.conn.execute(
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
        if commit:
            self.conn.commit()

    def list_source_status(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT sources.*,
                   COALESCE(item_counts.item_count, 0)::int AS item_count,
                   CASE
                     WHEN latest_quality.row_id IS NULL THEN NULL
                     ELSE to_jsonb(latest_quality.*)
                   END AS latest_quality_json
              FROM news_sources AS sources
              LEFT JOIN LATERAL (
                SELECT COUNT(items.news_item_id)::int AS item_count
                  FROM news_items AS items
                 WHERE items.source_id = sources.source_id
              ) AS item_counts ON true
              LEFT JOIN LATERAL (
                SELECT *
                  FROM news_source_quality_rows AS quality
                 WHERE quality.source_id = sources.source_id
                 ORDER BY
                   quality.computed_at_ms DESC,
                   CASE quality."window"
                     WHEN '24h' THEN 0
                     WHEN '4h' THEN 1
                     WHEN '1h' THEN 2
                     WHEN '7d' THEN 3
                     ELSE 4
                   END
                 LIMIT 1
              ) AS latest_quality ON true
             ORDER BY sources.enabled DESC, sources.source_domain ASC, sources.source_id ASC
            """
        ).fetchall()
        return [_source_status_payload(row) for row in rows]

    def replace_page_rows_for_items(
        self,
        *,
        news_item_ids: Sequence[str],
        rows: Sequence[Mapping[str, Any]],
        commit: bool = True,
    ) -> None:
        scoped_ids = list(dict.fromkeys(str(news_item_id) for news_item_id in news_item_ids))
        if scoped_ids:
            self.conn.execute("DELETE FROM news_page_rows WHERE news_item_id = ANY(%s::text[])", (scoped_ids,))
        for row in rows:
            self.conn.execute(
                """
                INSERT INTO news_page_rows (
                  row_id, news_item_id, story_id, latest_at_ms, lifecycle_status,
                  headline, summary, source_domain, canonical_url, token_lanes_json,
                  fact_lanes_json, story_json, source_json, agent_brief_json, agent_status,
                  agent_brief_computed_at_ms, computed_at_ms, projection_version
                )
                VALUES (
                  %(row_id)s, %(news_item_id)s, %(story_id)s, %(latest_at_ms)s, %(lifecycle_status)s,
                  %(headline)s, %(summary)s, %(source_domain)s, %(canonical_url)s, %(token_lanes_json)s,
                  %(fact_lanes_json)s, %(story_json)s, %(source_json)s, %(agent_brief_json)s, %(agent_status)s,
                  %(agent_brief_computed_at_ms)s, %(computed_at_ms)s, %(projection_version)s
                )
                ON CONFLICT (row_id) DO UPDATE SET
                  news_item_id = EXCLUDED.news_item_id,
                  story_id = EXCLUDED.story_id,
                  latest_at_ms = EXCLUDED.latest_at_ms,
                  lifecycle_status = EXCLUDED.lifecycle_status,
                  headline = EXCLUDED.headline,
                  summary = EXCLUDED.summary,
                  source_domain = EXCLUDED.source_domain,
                  canonical_url = EXCLUDED.canonical_url,
                  token_lanes_json = EXCLUDED.token_lanes_json,
                  fact_lanes_json = EXCLUDED.fact_lanes_json,
                  story_json = EXCLUDED.story_json,
                  source_json = EXCLUDED.source_json,
                  agent_brief_json = EXCLUDED.agent_brief_json,
                  agent_status = EXCLUDED.agent_status,
                  agent_brief_computed_at_ms = EXCLUDED.agent_brief_computed_at_ms,
                  computed_at_ms = EXCLUDED.computed_at_ms,
                  projection_version = EXCLUDED.projection_version
                """,
                _page_row_payload(row),
            )
        if commit:
            self.conn.commit()

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
            DELETE FROM news_page_rows rows
             USING news_items items
             WHERE rows.news_item_id = items.news_item_id
               AND (
                 (%s::text[] <> '{}'::text[] AND items.source_id = ANY(%s::text[]))
                 OR (%s::text[] <> '{}'::text[] AND items.source_domain = ANY(%s::text[]))
               )
            """,
            (normalized_source_ids, normalized_source_ids, normalized_domains, normalized_domains),
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


def _page_row_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    payload["latest_at_ms"] = int(payload["latest_at_ms"])
    payload["computed_at_ms"] = int(payload["computed_at_ms"])
    payload["headline"] = str(payload.get("headline") or payload.get("title") or "")
    payload["canonical_url"] = str(payload.get("canonical_url") or payload.get("url") or "")
    payload["summary"] = str(payload.get("summary") or "")
    payload["story_id"] = payload.get("story_id")
    payload["token_lanes_json"] = _json(payload.get("token_lanes_json", payload.get("token_lanes")) or [])
    payload["fact_lanes_json"] = _json(payload.get("fact_lanes_json", payload.get("fact_lanes")) or [])
    payload["story_json"] = _json(payload.get("story_json", payload.get("story")) or {})
    payload["source_json"] = _json(payload.get("source_json", payload.get("source")) or {})
    agent_brief = payload.get("agent_brief_json", payload.get("agent_brief")) or {"status": "pending"}
    agent_status = str(payload.get("agent_status") or payload.get("agent_brief_status") or "pending")
    payload["agent_brief_json"] = _json(agent_brief)
    payload["agent_status"] = agent_status
    payload["agent_brief_computed_at_ms"] = (
        int(payload["agent_brief_computed_at_ms"]) if payload.get("agent_brief_computed_at_ms") is not None else None
    )
    return payload


def _detail_agent_brief(value: Any) -> dict[str, Any]:
    if value is None:
        return {"status": "pending", "brief_json": {}}
    payload = _json_dict(value)
    payload["brief_json"] = _json_dict(payload.get("brief_json"))
    return payload


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
        "backend": str(payload.get("backend") or "openai_agents_sdk"),
        "sdk_trace_id": payload.get("sdk_trace_id"),
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
        "last_fetch_at_ms": int(row["last_fetch_at_ms"]) if row.get("last_fetch_at_ms") is not None else None,
        "last_success_at_ms": int(row["last_success_at_ms"]) if row.get("last_success_at_ms") is not None else None,
        "next_fetch_after_ms": int(row.get("next_fetch_after_ms") or 0),
        "consecutive_failures": int(row.get("consecutive_failures") or 0),
        "last_error": row.get("last_error"),
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


def _object_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    dump = getattr(value, "model_dump", None)
    if dump is not None:
        return dict(dump())
    if hasattr(value, "__dict__"):
        return dict(vars(value))
    return {name: getattr(value, name) for name in getattr(value, "__slots__", ()) if hasattr(value, name)}


def _json_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    return {}


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


def _json(value: Any) -> Jsonb:
    return Jsonb(value, dumps=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True))


def _compact_error(error: str | None) -> str | None:
    if not error:
        return None
    return str(error)[:2_000]
