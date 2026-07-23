from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from parallax.domains.news_intel._constants import NEWS_PAGE_PROJECTION_VERSION, NEWS_STORY_IDENTITY_VERSION
from parallax.domains.news_intel.repositories.news_repository_support import (
    _NEWS_ITEM_WORKER_COLUMNS_SQL,
    _NEWS_ITEM_WORKER_JSON_SQL,
    _PUBLICATION_METADATA_FIELDS,
    _STORY_PROJECTION_WINDOW_MS,
    _apply_page_row_summary,
    _current_policy_material_duplicate_groups,
    _current_read_model_payload_hash,
    _decode_page_cursor,
    _json_dict,
    _news_page_row_filter_sql,
    _optional_returning_row,
    _page_row_payload,
    _projected_news_page_row_payload,
    _public_fetch_run_payload,
    _public_news_item_payload,
    _public_observation_edge_payload,
    _public_provider_observation_payload,
    _public_source_payload,
    _public_url,
    _required_news_dedup_diagnostics_list,
    _required_news_dedup_diagnostics_mapping,
    _required_news_dedup_diagnostics_nonnegative_int,
    _required_news_item_detail_list,
    _required_page_projection_input_list,
    _required_projected_page_list,
    _required_projected_page_mapping,
    _required_projected_page_text,
    _required_story_projection_payload_list,
    _story_projection_payload,
)
from parallax.domains.news_intel.types.news_page_search import build_news_page_search_text
from parallax.domains.news_intel.types.news_url_identity import public_url_identity_policy
from parallax.platform.db.write_contract import mutation_count
from parallax.platform.validation import require_nonnegative_int, require_positive_int


class NewsPageRepository:
    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def list_news_page_rows(
        self,
        *,
        limit: int,
        cursor: str | None = None,
        status: str | None = None,
        q: str | None = None,
    ) -> list[dict[str, Any]]:
        return self._list_projected_news_page_rows(
            limit=limit,
            cursor=cursor,
            status=status,
            q=q,
        )

    def _list_projected_news_page_rows(
        self,
        *,
        limit: int,
        cursor: str | None = None,
        status: str | None = None,
        q: str | None = None,
    ) -> list[dict[str, Any]]:
        parsed_limit = require_nonnegative_int(
            limit,
            error_code="news_page_rows_limit_required",
        )
        cursor_time, cursor_id = _decode_page_cursor(cursor)
        filter_sql, filter_params = _news_page_row_filter_sql(status=status, q=q)
        rows = self.conn.execute(
            f"""
            SELECT
              row_id,
              news_item_id,
              representative_news_item_id,
              story_key,
              story_json AS story,
              latest_at_ms,
              lifecycle_status,
              headline,
              summary,
              source_domain,
              canonical_url,
              canonical_item_key,
              duplicate_count,
              source_ids_json AS source_ids,
              source_domains_json AS source_domains,
              provider_article_keys_json AS provider_article_keys,
              token_lanes_json AS token_lanes,
              fact_lanes_json AS fact_lanes,
              provider_rating_json AS provider_rating,
              content_class,
              content_tags_json AS content_tags,
              content_classification_json AS content_classification,
              source_json AS source,
              market_scope_json AS market_scope,
              computed_at_ms,
              projection_version
            FROM news_page_rows
            WHERE projection_version = %s
              AND (
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
              AND (
                COALESCE(source_json ->> 'source_id', '') = ''
                OR EXISTS (
                  SELECT 1
                    FROM news_sources AS projected_source
                   WHERE projected_source.source_id = source_json ->> 'source_id'
                     AND projected_source.enabled = true
                )
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
                parsed_limit,
            ),
        ).fetchall()
        return [_projected_news_page_row_payload(row, require_full_sections=True) for row in rows]

    def load_items_for_page_projection(self, *, news_item_ids: Sequence[str]) -> list[dict[str, Any]]:
        target_ids = list(dict.fromkeys(str(news_item_id) for news_item_id in news_item_ids if str(news_item_id)))
        if not target_ids:
            return []
        rows = self.conn.execute(
            f"""
            WITH target_items AS (
              SELECT
{_NEWS_ITEM_WORKER_COLUMNS_SQL}
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
              {_NEWS_ITEM_WORKER_JSON_SQL}
                || jsonb_build_object(
                  'provider_item_id', source_rep.provider_item_id,
                  'source_id', source_rep.source_id,
                  'source_domain', source_rep.source_domain,
                  'canonical_url', COALESCE(source_rep.item_payload ->> 'canonical_url', items.canonical_url),
                  'title', COALESCE(source_rep.item_payload ->> 'title', items.title),
                  'summary', COALESCE(source_rep.item_payload ->> 'summary', items.summary),
                  'body_text', COALESCE(source_rep.item_payload ->> 'body_text', items.body_text),
                  'language', COALESCE(source_rep.item_payload ->> 'language', items.language),
                  'published_at_ms',
                    COALESCE(NULLIF(source_rep.item_payload ->> 'published_at_ms', '')::bigint, items.published_at_ms),
                  'fetched_at_ms',
                    COALESCE(NULLIF(source_rep.item_payload ->> 'fetched_at_ms', '')::bigint, items.fetched_at_ms),
                  'content_hash', COALESCE(source_rep.item_payload ->> 'content_hash', items.content_hash),
                  'title_fingerprint',
                    COALESCE(source_rep.item_payload ->> 'title_fingerprint', items.title_fingerprint),
                  'provider_signal_json',
                    COALESCE(source_rep.item_payload -> 'provider_signal_json', items.provider_signal_json),
                  'provider_token_impacts_json',
                    COALESCE(
                      source_rep.item_payload -> 'provider_token_impacts_json',
                      items.provider_token_impacts_json
                    ),
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
              COALESCE(mentions.token_mentions, '[]'::jsonb) AS token_mentions,
              COALESCE(facts.fact_candidates, '[]'::jsonb) AS fact_candidates
            FROM target_items AS items
            JOIN LATERAL (
              SELECT provider_items.provider_item_id,
                     edge_sources.source_id,
                     edge_sources.source_domain,
                     edge_sources.provider_type,
                     edge_sources.source_name,
                     edge_sources.source_role,
                     edge_sources.trust_tier,
                     edge_sources.coverage_tags_json,
                     edge_sources.source_quality_status,
                     COALESCE(edges.evidence_json -> 'item_payload', '{{}}'::jsonb) AS item_payload
                FROM news_item_observation_edges AS edges
                JOIN news_sources AS edge_sources ON edge_sources.source_id = edges.source_id
                JOIN news_provider_items AS provider_items ON provider_items.provider_item_id = edges.provider_item_id
               WHERE edges.news_item_id = items.news_item_id
                 AND edge_sources.enabled = true
               ORDER BY
                 CASE WHEN provider_items.provider_payload_status = 'ready' THEN 0 ELSE 1 END,
                 CASE WHEN edges.evidence_json #>> '{{item_payload,url_identity_kind}}' = 'article' THEN 0 ELSE 1 END,
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
                "token_mentions": _required_page_projection_input_list(row, "token_mentions"),
                "fact_candidates": _required_page_projection_input_list(row, "fact_candidates"),
            }
            for row in rows
        ]

    def load_story_projection_payloads_for_items(self, *, news_item_ids: Sequence[str]) -> list[dict[str, Any]]:
        target_ids = list(dict.fromkeys(str(news_item_id) for news_item_id in news_item_ids if str(news_item_id)))
        if not target_ids:
            return []
        story_scope_rows = self.conn.execute(
            """
            WITH target_items AS (
              SELECT news_item_id, story_key, published_at_ms
                FROM news_items
               WHERE news_item_id = ANY(%s::text[])
                 AND lifecycle_status = 'processed'
                 AND story_key <> ''
                 AND story_identity_version = %s
            ),
            story_bounds AS (
              SELECT story_key,
                     MIN(published_at_ms) - %s::bigint AS lower_bound_ms,
                     MAX(published_at_ms) + %s::bigint AS upper_bound_ms,
                     MIN(array_position(%s::text[], news_item_id)) AS first_target_ordinal
                FROM target_items
               GROUP BY story_key
            )
            SELECT items.news_item_id,
                   items.story_key,
                   story_bounds.first_target_ordinal,
                   items.published_at_ms
              FROM story_bounds
              JOIN news_items AS items ON items.story_key = story_bounds.story_key
             WHERE items.published_at_ms BETWEEN story_bounds.lower_bound_ms AND story_bounds.upper_bound_ms
               AND items.lifecycle_status = 'processed'
               AND items.story_key <> ''
               AND items.story_identity_version = %s
               AND EXISTS (
                 SELECT 1
                   FROM news_item_observation_edges AS edges
                   JOIN news_sources AS sources ON sources.source_id = edges.source_id
                  WHERE edges.news_item_id = items.news_item_id
                    AND sources.enabled = true
               )
             ORDER BY first_target_ordinal ASC NULLS LAST,
                      story_key ASC,
                      published_at_ms DESC,
                      news_item_id DESC
            """,
            (
                target_ids,
                NEWS_STORY_IDENTITY_VERSION,
                _STORY_PROJECTION_WINDOW_MS,
                _STORY_PROJECTION_WINDOW_MS,
                target_ids,
                NEWS_STORY_IDENTITY_VERSION,
            ),
        ).fetchall()
        scoped_item_ids = [str(row["news_item_id"]) for row in story_scope_rows]
        item_payloads = self.load_items_for_page_projection(news_item_ids=scoped_item_ids)
        item_payloads_by_id = {str(payload["item"]["news_item_id"]): payload for payload in item_payloads}
        grouped_ids: dict[str, list[str]] = {}
        group_order: list[str] = []
        for row in story_scope_rows:
            news_item_id = str(row["news_item_id"])
            if news_item_id not in item_payloads_by_id:
                continue
            story_key = str(row["story_key"])
            if story_key not in grouped_ids:
                grouped_ids[story_key] = []
                group_order.append(story_key)
            grouped_ids[story_key].append(news_item_id)

        payloads: list[dict[str, Any]] = []
        for story_key in group_order:
            member_payloads = [item_payloads_by_id[item_id] for item_id in grouped_ids[story_key]]
            representative = member_payloads[0]
            payloads.append(
                {
                    "item": representative["item"],
                    "token_mentions": _required_story_projection_payload_list(representative, "token_mentions"),
                    "fact_candidates": _required_story_projection_payload_list(representative, "fact_candidates"),
                    "story": _story_projection_payload(story_key=story_key, member_payloads=member_payloads),
                    "member_items": [payload["item"] for payload in member_payloads],
                }
            )
        return payloads

    def get_news_item_detail(self, *, news_item_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT to_jsonb(items.*) AS item,
                   to_jsonb(sources.*) AS source,
                   to_jsonb(provider_items.*) AS provider_item,
                   CASE WHEN fetch_runs.fetch_run_id IS NULL THEN NULL ELSE to_jsonb(fetch_runs.*) END AS fetch_run,
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
              LEFT JOIN news_item_entities AS entities ON entities.news_item_id = items.news_item_id
              LEFT JOIN news_token_mentions AS mentions ON mentions.news_item_id = items.news_item_id
              LEFT JOIN news_fact_candidates AS facts ON facts.news_item_id = items.news_item_id
             WHERE items.news_item_id = %s
             GROUP BY items.news_item_id, sources.source_id, provider_items.provider_item_id, fetch_runs.fetch_run_id
            """,
            (news_item_id,),
        ).fetchone()
        if row is None:
            return None
        page_row = self.conn.execute(
            """
            SELECT row_id,
                   representative_news_item_id,
                   story_key,
                   story_json AS story,
                   latest_at_ms,
                   lifecycle_status,
                   token_lanes_json AS token_lanes,
                   fact_lanes_json AS fact_lanes,
                   provider_rating_json AS provider_rating,
                   content_class,
                   content_tags_json AS content_tags,
                   content_classification_json AS content_classification,
                   market_scope_json AS market_scope,
                   computed_at_ms,
                   projection_version
              FROM news_page_rows
             WHERE news_item_id = %s
               AND projection_version = %s
             ORDER BY latest_at_ms DESC, row_id DESC
             LIMIT 1
            """,
            (news_item_id, NEWS_PAGE_PROJECTION_VERSION),
        ).fetchone()
        if page_row is None:
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
        projected = dict(page_row)
        item_payload = _json_dict(row["item"])
        return {
            **_public_news_item_payload(item_payload),
            "representative_news_item_id": _required_projected_page_text(
                projected,
                "representative_news_item_id",
            ),
            "story_key": _required_projected_page_text(projected, "story_key"),
            "story": _required_projected_page_mapping(projected, "story"),
            "content_class": _required_projected_page_text(projected, "content_class"),
            "content_tags": _required_projected_page_list(projected, "content_tags"),
            "content_classification": _required_projected_page_mapping(
                projected,
                "content_classification",
            ),
            "provider_rating": _required_projected_page_mapping(projected, "provider_rating"),
            "market_scope": _required_projected_page_mapping(projected, "market_scope"),
            "token_lanes": _required_projected_page_list(projected, "token_lanes"),
            "fact_lanes": _required_projected_page_list(projected, "fact_lanes"),
            "source": _public_source_payload(_json_dict(row["source"])),
            "provider_item": _public_provider_observation_payload(_json_dict(row["provider_item"])),
            "fetch_run": (
                _public_fetch_run_payload(_json_dict(row["fetch_run"])) if row["fetch_run"] is not None else None
            ),
            "observation_edges": [
                _public_observation_edge_payload(_json_dict(observation_row["observation_edge"]))
                for observation_row in observation_rows
            ],
            "provider_observations": [
                _public_provider_observation_payload(_json_dict(observation_row["provider_observation"]))
                for observation_row in observation_rows
            ],
            "entities": _required_news_item_detail_list(row, "entities"),
            "token_mentions": _required_news_item_detail_list(row, "token_mentions"),
            "fact_candidates": _required_news_item_detail_list(row, "fact_candidates"),
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

    def news_dedup_diagnostics(
        self,
        *,
        window_ms: int = 8 * 3_600_000,
        now_ms: int | None = None,
    ) -> dict[str, Any]:
        parsed_window_ms = require_positive_int(
            window_ms,
            error_code="news_dedup_diagnostics_window_ms_required",
        )
        resolved_now_ms = int(now_ms) if now_ms is not None else 0
        row = self.conn.execute(
            """
            WITH params AS (
              SELECT
                CASE
                  WHEN %(now_ms)s::bigint > 0 THEN %(now_ms)s::bigint
                  ELSE (extract(epoch FROM clock_timestamp()) * 1000)::bigint
                END AS now_ms,
                %(window_ms)s::bigint AS window_ms
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
               WHERE rows.projection_version = %(projection_version)s
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
                     items.created_at_ms
                FROM news_items AS items
                CROSS JOIN params
               WHERE COALESCE(NULLIF(items.created_at_ms, 0), items.fetched_at_ms, 0)
                     >= params.now_ms - params.window_ms
            ),
            material_title_duplicates AS (
              SELECT scoped_items.source_id,
                     scoped_items.title_fingerprint,
                     COUNT(*)::int AS row_count
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
                       'news_item_ids',
                         (
                           SELECT COALESCE(jsonb_agg(items.news_item_id ORDER BY items.news_item_id), '[]'::jsonb)
                             FROM scoped_items AS items
                            WHERE items.source_id = duplicates.source_id
                              AND items.title_fingerprint = duplicates.title_fingerprint
                         )
                     ) AS payload
                FROM material_title_duplicates AS duplicates
               ORDER BY duplicates.row_count DESC, duplicates.source_id ASC, duplicates.title_fingerprint ASC
               LIMIT 20
            ),
            case_insensitive_url_duplicates AS (
              SELECT lower(scoped_items.canonical_url) AS normalized_url,
                     COUNT(*)::int AS row_count
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
                       'news_item_ids',
                         (
                           SELECT COALESCE(jsonb_agg(items.news_item_id ORDER BY items.news_item_id), '[]'::jsonb)
                             FROM scoped_items AS items
                            WHERE lower(items.canonical_url) = duplicates.normalized_url
                         )
                     ) AS payload
                FROM case_insensitive_url_duplicates AS duplicates
               ORDER BY duplicates.row_count DESC, duplicates.normalized_url ASC
               LIMIT 20
            ),
            preview_or_generic_url_rows AS (
              SELECT COUNT(*)::int AS row_count
                FROM scoped_items
                CROSS JOIN params
               WHERE scoped_items.canonical_url ~* '^https?://news\\.6551\\.io/preview/'
                  OR scoped_items.canonical_url ~* '^https?://([^/]+\\.)?treeofalpha\\.com/preview_article'
                  OR scoped_items.canonical_url ~* '^https?://([^/]+\\.)?binance\\.com/[^?]*/support/announcement/?$'
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
                'top_groups',
                  COALESCE((SELECT jsonb_agg(payload) FROM top_material_title_duplicate_groups), '[]'::jsonb)
              ) AS material_title_duplicate_groups,
              jsonb_build_object(
                'groups', COALESCE((SELECT COUNT(*)::int FROM case_insensitive_url_duplicates), 0),
                'rows', COALESCE((SELECT SUM(row_count)::int FROM case_insensitive_url_duplicates), 0),
                'duplicate_rows', COALESCE((SELECT SUM(row_count - 1)::int FROM case_insensitive_url_duplicates), 0),
                'top_groups',
                  COALESCE((SELECT jsonb_agg(payload) FROM top_case_insensitive_url_duplicate_groups), '[]'::jsonb)
              ) AS case_insensitive_url_duplicate_groups,
              jsonb_build_object(
                'rows', COALESCE((SELECT row_count FROM preview_or_generic_url_rows), 0)
              ) AS preview_or_generic_url_rows,
              COALESCE((SELECT jsonb_agg(payload) FROM source_sync), '[]'::jsonb) AS source_sync_diagnostics
            """,
            {
                "now_ms": resolved_now_ms,
                "window_ms": parsed_window_ms,
                "projection_version": NEWS_PAGE_PROJECTION_VERSION,
            },
        ).fetchone()
        if row is None:
            payload = {
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
                "source_sync_diagnostics": [],
            }
        else:
            payload = {
                "raw_observation_count": _required_news_dedup_diagnostics_nonnegative_int(row, "raw_observation_count"),
                "canonical_item_count": _required_news_dedup_diagnostics_nonnegative_int(row, "canonical_item_count"),
                "observation_edge_count": _required_news_dedup_diagnostics_nonnegative_int(
                    row, "observation_edge_count"
                ),
                "enabled_serving_row_count": _required_news_dedup_diagnostics_nonnegative_int(
                    row, "enabled_serving_row_count"
                ),
                "disabled_serving_row_count": _required_news_dedup_diagnostics_nonnegative_int(
                    row, "disabled_serving_row_count"
                ),
                "enabled_exact_content_visible_duplicate_excess": _required_news_dedup_diagnostics_nonnegative_int(
                    row, "enabled_exact_content_visible_duplicate_excess"
                ),
                "top_visible_content_duplicate_groups": _required_news_dedup_diagnostics_list(
                    row, "top_visible_content_duplicate_groups"
                ),
                "top_visible_canonical_duplicate_groups": _required_news_dedup_diagnostics_list(
                    row, "top_visible_canonical_duplicate_groups"
                ),
                "material_title_duplicate_groups": _required_news_dedup_diagnostics_mapping(
                    row, "material_title_duplicate_groups"
                ),
                "case_insensitive_url_duplicate_groups": _required_news_dedup_diagnostics_mapping(
                    row, "case_insensitive_url_duplicate_groups"
                ),
                "preview_or_generic_url_rows": _required_news_dedup_diagnostics_mapping(
                    row, "preview_or_generic_url_rows"
                ),
                "source_sync_diagnostics": _required_news_dedup_diagnostics_list(row, "source_sync_diagnostics"),
            }
        current_policy = self._news_dedup_current_policy_diagnostics(
            window_ms=parsed_window_ms,
            now_ms=resolved_now_ms,
        )
        return {**payload, **current_policy}

    def _news_dedup_current_policy_diagnostics(self, *, window_ms: int, now_ms: int) -> dict[str, Any]:
        parsed_window_ms = require_positive_int(
            window_ms,
            error_code="news_dedup_diagnostics_window_ms_required",
        )
        visible_rows = self.conn.execute(
            """
            SELECT rows.row_id,
                   rows.news_item_id,
                   items.source_id,
                   lower(trim(sources.provider_type)) AS provider_type,
                   items.canonical_url,
                   items.title,
                   items.published_at_ms,
                   items.fetched_at_ms,
                   items.created_at_ms,
                   items.provider_token_impacts_json
              FROM news_page_rows AS rows
              JOIN news_items AS items ON items.news_item_id = rows.news_item_id
              JOIN news_sources AS sources ON sources.source_id = items.source_id
             WHERE rows.projection_version = %(projection_version)s
               AND EXISTS (
                     SELECT 1
                       FROM news_item_observation_edges AS edges
                       JOIN news_sources AS edge_sources ON edge_sources.source_id = edges.source_id
                      WHERE edges.news_item_id = rows.news_item_id
                        AND edge_sources.enabled = true
                   )
             ORDER BY rows.news_item_id ASC, rows.row_id ASC
            """,
            {"projection_version": NEWS_PAGE_PROJECTION_VERSION},
        ).fetchall()
        fact_rows = self.conn.execute(
            """
            WITH params AS (
              SELECT
                CASE
                  WHEN %(now_ms)s::bigint > 0 THEN %(now_ms)s::bigint
                  ELSE (extract(epoch FROM clock_timestamp()) * 1000)::bigint
                END AS now_ms,
                %(window_ms)s::bigint AS window_ms
            )
            SELECT items.news_item_id,
                   items.source_id,
                   lower(trim(sources.provider_type)) AS provider_type,
                   items.canonical_url,
                   items.title,
                   items.published_at_ms,
                   items.fetched_at_ms,
                   items.created_at_ms,
                   items.provider_token_impacts_json
              FROM news_items AS items
              JOIN news_sources AS sources ON sources.source_id = items.source_id
              CROSS JOIN params
             WHERE COALESCE(NULLIF(items.created_at_ms, 0), items.fetched_at_ms, 0)
                   >= params.now_ms - params.window_ms
             ORDER BY items.source_id ASC, items.published_at_ms ASC, items.news_item_id ASC
            """,
            {"now_ms": int(now_ms), "window_ms": parsed_window_ms},
        ).fetchall()
        stale_dirty_row = self.conn.execute(
            """
            SELECT COUNT(*)::int AS row_count
             FROM news_projection_dirty_targets AS targets
              LEFT JOIN news_items AS items ON items.news_item_id = targets.target_id
             WHERE targets.target_kind = 'news_item'
               AND targets.projection_name = 'page'
               AND (
                 items.news_item_id IS NULL
                 OR NOT EXISTS (
                      SELECT 1
                        FROM news_item_observation_edges AS edges
                       WHERE edges.news_item_id = targets.target_id
                    )
               )
            """
        ).fetchone()

        hard_public_groups: dict[str, set[str]] = defaultdict(set)
        generic_public_url_visible_rows = 0
        for row in visible_rows:
            policy = public_url_identity_policy(row["canonical_url"])
            if policy.allowed:
                hard_public_groups[policy.identity_key].add(str(row["news_item_id"]))
            elif policy.normalized_url.startswith(("http://", "https://")):
                generic_public_url_visible_rows += 1

        visible_material_groups = _current_policy_material_duplicate_groups(visible_rows)
        fact_material_groups = _current_policy_material_duplicate_groups(fact_rows)
        return {
            "hard_public_url_visible_duplicate_excess": sum(
                max(0, len(news_item_ids) - 1) for news_item_ids in hard_public_groups.values()
            ),
            "generic_public_url_visible_rows": int(generic_public_url_visible_rows),
            "material_title_visible_duplicate_excess": sum(
                int(group["duplicate_rows"]) for group in visible_material_groups
            ),
            "fact_layer_material_duplicate_excess": sum(int(group["duplicate_rows"]) for group in fact_material_groups),
            "stale_duplicate_dirty_targets": int(stale_dirty_row["row_count"] if stale_dirty_row else 0),
            "top_material_title_duplicate_groups": fact_material_groups[:20],
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
            deleted = mutation_count(cursor, error_code="news_repository_rowcount_invalid")

        inserted = updated = unchanged = 0
        for payload in row_payloads:
            payload["search_text"] = build_news_page_search_text(payload)
            payload["payload_hash"] = _current_read_model_payload_hash(
                payload,
                exclude=_PUBLICATION_METADATA_FIELDS,
            )
            cursor = self.conn.execute(
                """
                INSERT INTO news_page_rows (
                  row_id, news_item_id, representative_news_item_id, story_key, story_json,
                  latest_at_ms, lifecycle_status, headline, summary, source_domain,
                  canonical_url, canonical_item_key, search_text, token_lanes_json,
                  fact_lanes_json, provider_rating_json, content_class, content_tags_json,
                  content_classification_json, source_json, market_scope_json, duplicate_count,
                  source_ids_json, source_domains_json, provider_article_keys_json,
                  computed_at_ms, projection_version, payload_hash
                )
                VALUES (
                  %(row_id)s, %(news_item_id)s, %(representative_news_item_id)s, %(story_key)s,
                  %(story_json)s, %(latest_at_ms)s, %(lifecycle_status)s, %(headline)s,
                  %(summary)s, %(source_domain)s, %(canonical_url)s, %(canonical_item_key)s,
                  %(search_text)s, %(token_lanes_json)s, %(fact_lanes_json)s,
                  %(provider_rating_json)s, %(content_class)s, %(content_tags_json)s,
                  %(content_classification_json)s, %(source_json)s, %(market_scope_json)s,
                  %(duplicate_count)s, %(source_ids_json)s, %(source_domains_json)s,
                  %(provider_article_keys_json)s, %(computed_at_ms)s, %(projection_version)s,
                  %(payload_hash)s
                )
                ON CONFLICT (row_id) DO UPDATE SET
                  news_item_id = EXCLUDED.news_item_id,
                  representative_news_item_id = EXCLUDED.representative_news_item_id,
                  story_key = EXCLUDED.story_key,
                  story_json = EXCLUDED.story_json,
                  latest_at_ms = EXCLUDED.latest_at_ms,
                  lifecycle_status = EXCLUDED.lifecycle_status,
                  headline = EXCLUDED.headline,
                  summary = EXCLUDED.summary,
                  source_domain = EXCLUDED.source_domain,
                  canonical_url = EXCLUDED.canonical_url,
                  canonical_item_key = EXCLUDED.canonical_item_key,
                  search_text = EXCLUDED.search_text,
                  token_lanes_json = EXCLUDED.token_lanes_json,
                  fact_lanes_json = EXCLUDED.fact_lanes_json,
                  provider_rating_json = EXCLUDED.provider_rating_json,
                  content_class = EXCLUDED.content_class,
                  content_tags_json = EXCLUDED.content_tags_json,
                  content_classification_json = EXCLUDED.content_classification_json,
                  source_json = EXCLUDED.source_json,
                  market_scope_json = EXCLUDED.market_scope_json,
                  duplicate_count = EXCLUDED.duplicate_count,
                  source_ids_json = EXCLUDED.source_ids_json,
                  source_domains_json = EXCLUDED.source_domains_json,
                  provider_article_keys_json = EXCLUDED.provider_article_keys_json,
                  computed_at_ms = EXCLUDED.computed_at_ms,
                  projection_version = EXCLUDED.projection_version,
                  payload_hash = EXCLUDED.payload_hash
                WHERE news_page_rows.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash
                RETURNING (xmax = 0) AS inserted
                """,
                payload,
            )
            returned_row = _optional_returning_row(cursor, cursor.fetchone())
            if returned_row is None:
                unchanged += 1
            elif bool(returned_row["inserted"]):
                inserted += 1
            else:
                updated += 1
        return {"inserted": inserted, "updated": updated, "unchanged": unchanged, "deleted": deleted}

    def replace_page_rows_for_story_targets(
        self,
        *,
        news_item_ids: Sequence[str],
        story_keys: Sequence[str],
        rows: Sequence[Mapping[str, Any]],
    ) -> dict[str, int]:
        row_payloads = [_page_row_payload(row) for row in rows]
        claimed_member_ids = list(
            dict.fromkeys(str(news_item_id) for news_item_id in news_item_ids if str(news_item_id))
        )
        scoped_story_keys = list(
            dict.fromkeys(
                [
                    *(str(story_key) for story_key in story_keys if str(story_key)),
                    *(
                        str(payload.get("story_key") or "")
                        for payload in row_payloads
                        if str(payload.get("story_key") or "")
                    ),
                ]
            )
        )
        if claimed_member_ids:
            story_key_rows = self.conn.execute(
                """
                SELECT DISTINCT story_key
                  FROM news_items
                 WHERE news_item_id = ANY(%s::text[])
                   AND story_key <> ''
                """,
                (claimed_member_ids,),
            ).fetchall()
            scoped_story_keys = list(
                dict.fromkeys([*scoped_story_keys, *(str(row["story_key"]) for row in story_key_rows)])
            )
        scoped_member_ids = list(claimed_member_ids)
        if scoped_story_keys:
            member_rows = self.conn.execute(
                """
                SELECT news_item_id
                  FROM news_items
                 WHERE story_key = ANY(%s::text[])
                """,
                (scoped_story_keys,),
            ).fetchall()
            scoped_member_ids = list(
                dict.fromkeys([*scoped_member_ids, *(str(row["news_item_id"]) for row in member_rows)])
            )
        incoming_row_ids = list(dict.fromkeys(str(payload["row_id"]) for payload in row_payloads))
        deleted = 0
        if scoped_story_keys or scoped_member_ids:
            incoming_filter = "AND NOT (row_id = ANY(%s::text[]))" if incoming_row_ids else ""
            delete_params = (
                (
                    NEWS_PAGE_PROJECTION_VERSION,
                    scoped_story_keys,
                    scoped_story_keys,
                    scoped_member_ids,
                    scoped_member_ids,
                    claimed_member_ids,
                    claimed_member_ids,
                    incoming_row_ids,
                )
                if incoming_row_ids
                else (
                    NEWS_PAGE_PROJECTION_VERSION,
                    scoped_story_keys,
                    scoped_story_keys,
                    scoped_member_ids,
                    scoped_member_ids,
                    claimed_member_ids,
                    claimed_member_ids,
                )
            )
            cursor = self.conn.execute(
                f"""
                DELETE FROM news_page_rows
                 WHERE projection_version = %s
                   AND (
                     (%s::text[] <> '{{}}'::text[] AND story_key = ANY(%s::text[]))
                     OR (%s::text[] <> '{{}}'::text[] AND news_item_id = ANY(%s::text[]))
                     OR (
                       %s::text[] <> '{{}}'::text[]
                       AND COALESCE(story_json -> 'member_news_item_ids', '[]'::jsonb) ?| %s::text[]
                     )
                   )
                   {incoming_filter}
                """,
                delete_params,
            )
            deleted = mutation_count(cursor, error_code="news_repository_rowcount_invalid")
        result = self.replace_page_rows_for_items(news_item_ids=[], rows=row_payloads)
        result["deleted"] = int(result.get("deleted", 0)) + deleted
        return result

    def delete_page_rows_for_sources(
        self,
        *,
        source_ids: Sequence[str] | None = None,
        source_domains: Sequence[str] | None = None,
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
        return mutation_count(cursor, error_code="news_repository_rowcount_invalid")
