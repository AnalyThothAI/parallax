from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from parallax.domains.news_intel._constants import NEWS_STORY_IDENTITY_VERSION
from parallax.domains.news_intel.repositories.news_repository_support import (
    _NEWS_ITEM_WORKER_JSON_SQL,
    _json_dict,
    _required_returning_row,
    _required_story_brief_target_source_updated_at_ms,
    _required_story_item_json_value,
    _required_story_item_mapping,
    _required_story_item_text,
    _story_agent_brief_payload,
    _story_agent_run_payload,
    _story_brief_target_list,
    _story_projection_payload,
)
from parallax.platform.db.write_contract import mutation_count


class NewsStoryAgentRepository:
    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def insert_news_story_agent_run(
        self,
        *,
        run_id: str,
        story_brief_key: str,
        story_key: str,
        story_identity_version: str,
        representative_news_item_id: str,
        member_news_item_ids_json: Sequence[str],
        provider: str,
        model: str,
        backend: str,
        execution_trace_id: str | None = None,
        workflow_name: str,
        agent_name: str,
        lane: str,
        artifact_version_hash: str,
        prompt_version: str,
        schema_version: str,
        validator_version: str,
        guardrail_version: str,
        input_hash: str,
        output_hash: str | None = None,
        execution_started: bool,
        status: str,
        outcome: str,
        error_class: str | None = None,
        error: str | None = None,
        request_json: Mapping[str, Any],
        response_json: Any | None,
        validation_errors_json: list[Any],
        trace_metadata_json: Mapping[str, Any],
        usage_json: Mapping[str, Any],
        latency_ms: int,
        started_at_ms: int,
        finished_at_ms: int,
        created_at_ms: int,
    ) -> dict[str, Any]:
        payload = {
            "run_id": run_id,
            "story_brief_key": story_brief_key,
            "story_key": story_key,
            "story_identity_version": story_identity_version,
            "representative_news_item_id": representative_news_item_id,
            "member_news_item_ids_json": member_news_item_ids_json,
            "provider": provider,
            "model": model,
            "backend": backend,
            "execution_trace_id": execution_trace_id,
            "workflow_name": workflow_name,
            "agent_name": agent_name,
            "lane": lane,
            "artifact_version_hash": artifact_version_hash,
            "prompt_version": prompt_version,
            "schema_version": schema_version,
            "validator_version": validator_version,
            "guardrail_version": guardrail_version,
            "input_hash": input_hash,
            "output_hash": output_hash,
            "execution_started": execution_started,
            "status": status,
            "outcome": outcome,
            "error_class": error_class,
            "error": error,
            "request_json": request_json,
            "response_json": response_json,
            "validation_errors_json": validation_errors_json,
            "trace_metadata_json": trace_metadata_json,
            "usage_json": usage_json,
            "latency_ms": latency_ms,
            "started_at_ms": started_at_ms,
            "finished_at_ms": finished_at_ms,
            "created_at_ms": created_at_ms,
        }
        cursor = self.conn.execute(
            """
            INSERT INTO news_story_agent_runs (
              run_id, story_brief_key, story_key, story_identity_version, representative_news_item_id,
              member_news_item_ids_json, provider, model, backend, execution_trace_id, workflow_name,
              agent_name, lane, artifact_version_hash, prompt_version, schema_version,
              validator_version, guardrail_version, input_hash, output_hash, execution_started,
              status, outcome, error_class, error, request_json, response_json,
              validation_errors_json, trace_metadata_json, usage_json, latency_ms,
              started_at_ms, finished_at_ms, created_at_ms
            )
            VALUES (
              %(run_id)s, %(story_brief_key)s, %(story_key)s, %(story_identity_version)s,
              %(representative_news_item_id)s, %(member_news_item_ids_json)s,
              %(provider)s, %(model)s, %(backend)s, %(execution_trace_id)s,
              %(workflow_name)s, %(agent_name)s, %(lane)s, %(artifact_version_hash)s,
              %(prompt_version)s, %(schema_version)s, %(validator_version)s, %(guardrail_version)s,
              %(input_hash)s, %(output_hash)s, %(execution_started)s, %(status)s, %(outcome)s,
              %(error_class)s, %(error)s, %(request_json)s, %(response_json)s,
              %(validation_errors_json)s, %(trace_metadata_json)s, %(usage_json)s,
              %(latency_ms)s, %(started_at_ms)s, %(finished_at_ms)s, %(created_at_ms)s
            )
            RETURNING *
            """,
            _story_agent_run_payload(payload),
        )
        row = cursor.fetchone()
        returned_row = _required_returning_row(cursor, row)
        return returned_row

    def prune_unreferenced_story_agent_runs(self, *, cutoff_ms: int, limit: int) -> int:
        cursor = self.conn.execute(
            """
            WITH expired_story_runs AS (
              SELECT runs.run_id
              FROM news_story_agent_runs AS runs
              WHERE runs.finished_at_ms < %s
                AND NOT EXISTS (
                  SELECT 1
                  FROM news_story_agent_briefs AS briefs
                  WHERE briefs.agent_run_id = runs.run_id
                )
              ORDER BY runs.finished_at_ms ASC, runs.run_id ASC
              LIMIT %s
              FOR UPDATE SKIP LOCKED
            )
            DELETE FROM news_story_agent_runs AS runs
            USING expired_story_runs AS expired
            WHERE runs.run_id = expired.run_id
            """,
            (cutoff_ms, limit),
        )
        count = mutation_count(cursor, error_code="news_repository_rowcount_invalid")
        if count > limit:
            raise TypeError("news_repository_rowcount_invalid")
        return count

    def upsert_news_story_agent_brief(
        self,
        *,
        story_brief_key: str,
        story_key: str,
        story_identity_version: str,
        representative_news_item_id: str,
        member_news_item_ids_json: Sequence[str],
        agent_run_id: str,
        status: str,
        direction: str,
        decision_class: str,
        brief_json: Mapping[str, Any],
        input_hash: str,
        artifact_version_hash: str,
        prompt_version: str,
        schema_version: str,
        validator_version: str,
        computed_at_ms: int,
        created_at_ms: int,
        updated_at_ms: int,
    ) -> dict[str, Any]:
        payload = {
            "story_brief_key": story_brief_key,
            "story_key": story_key,
            "story_identity_version": story_identity_version,
            "representative_news_item_id": representative_news_item_id,
            "member_news_item_ids_json": member_news_item_ids_json,
            "agent_run_id": agent_run_id,
            "status": status,
            "direction": direction,
            "decision_class": decision_class,
            "brief_json": brief_json,
            "input_hash": input_hash,
            "artifact_version_hash": artifact_version_hash,
            "prompt_version": prompt_version,
            "schema_version": schema_version,
            "validator_version": validator_version,
            "computed_at_ms": computed_at_ms,
            "created_at_ms": created_at_ms,
            "updated_at_ms": updated_at_ms,
        }
        cursor = self.conn.execute(
            """
            INSERT INTO news_story_agent_briefs (
              story_brief_key, story_key, story_identity_version, representative_news_item_id,
              member_news_item_ids_json, agent_run_id, status, direction, decision_class, brief_json,
              input_hash, artifact_version_hash, prompt_version, schema_version,
              validator_version, computed_at_ms, created_at_ms, updated_at_ms
            )
            VALUES (
              %(story_brief_key)s, %(story_key)s, %(story_identity_version)s,
              %(representative_news_item_id)s, %(member_news_item_ids_json)s,
              %(agent_run_id)s, %(status)s, %(direction)s, %(decision_class)s,
              %(brief_json)s, %(input_hash)s, %(artifact_version_hash)s,
              %(prompt_version)s, %(schema_version)s, %(validator_version)s,
              %(computed_at_ms)s, %(created_at_ms)s, %(updated_at_ms)s
            )
            ON CONFLICT (story_brief_key) DO UPDATE SET
              story_key = EXCLUDED.story_key,
              story_identity_version = EXCLUDED.story_identity_version,
              representative_news_item_id = EXCLUDED.representative_news_item_id,
              member_news_item_ids_json = EXCLUDED.member_news_item_ids_json,
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
            _story_agent_brief_payload(payload),
        )
        row = cursor.fetchone()
        returned_row = _required_returning_row(cursor, row)
        return returned_row

    def get_news_story_agent_brief(self, story_brief_key: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT *
              FROM news_story_agent_briefs
             WHERE story_brief_key = %s
            """,
            (str(story_brief_key),),
        ).fetchone()
        return dict(row) if row is not None else None

    def load_story_brief_targets(self, *, story_keys: Sequence[str]) -> list[dict[str, Any]]:
        target_keys = [str(story_key) for story_key in dict.fromkeys(story_keys) if str(story_key)]
        if not target_keys:
            return []
        rows = self.conn.execute(
            f"""
            WITH target_keys(story_key, ordinal) AS (
              SELECT story_key, ordinal
                FROM unnest(%s::text[]) WITH ORDINALITY AS keys(story_key, ordinal)
            ),
            candidates AS (
              SELECT
                items.news_item_id,
                items.story_key,
                target_keys.ordinal,
                items.published_at_ms,
                GREATEST(
                  COALESCE(items.processed_at_ms, items.created_at_ms, 0),
                  COALESCE(entity_updates.updated_at_ms, 0),
                  COALESCE(mention_updates.updated_at_ms, 0),
                  COALESCE(fact_updates.updated_at_ms, 0)
                ) AS source_updated_at_ms
              FROM target_keys
              JOIN news_items AS items ON items.story_key = target_keys.story_key
              LEFT JOIN LATERAL (
                SELECT MAX(created_at_ms) AS updated_at_ms
                  FROM news_item_entities
                 WHERE news_item_id = items.news_item_id
              ) AS entity_updates ON true
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
              WHERE items.lifecycle_status = 'processed'
                AND items.story_key <> ''
                AND items.story_identity_version = %s
                AND EXISTS (
                  SELECT 1
                    FROM news_item_observation_edges AS edges
                    JOIN news_sources AS edge_sources ON edge_sources.source_id = edges.source_id
                   WHERE edges.news_item_id = items.news_item_id
                     AND edge_sources.enabled = true
                )
            )
            SELECT
              candidates.story_key,
              candidates.source_updated_at_ms,
              {_NEWS_ITEM_WORKER_JSON_SQL}
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
                WHEN current_brief.story_brief_key IS NULL THEN NULL
                ELSE to_jsonb(current_brief.*)
              END AS current_brief,
              latest_run.latest_run AS latest_run,
              COALESCE(entity_rows.rows, '[]'::jsonb) AS entities,
              COALESCE(token_rows.rows, '[]'::jsonb) AS token_mentions,
              COALESCE(fact_rows.rows, '[]'::jsonb) AS fact_candidates
            FROM candidates
            JOIN news_items AS items ON items.news_item_id = candidates.news_item_id
            JOIN news_sources AS sources ON sources.source_id = items.source_id
            LEFT JOIN news_story_agent_briefs AS current_brief
              ON current_brief.story_key = items.story_key
             AND current_brief.story_identity_version = items.story_identity_version
            LEFT JOIN LATERAL (
              SELECT to_jsonb(runs.*) AS latest_run
                FROM news_story_agent_runs AS runs
               WHERE runs.story_key = items.story_key
                 AND runs.story_identity_version = items.story_identity_version
               ORDER BY runs.finished_at_ms DESC, runs.run_id DESC
               LIMIT 1
            ) AS latest_run ON true
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
              SELECT jsonb_agg(to_jsonb(entities.*) ORDER BY entities.entity_id ASC) AS rows
                FROM news_item_entities AS entities
               WHERE entities.news_item_id = items.news_item_id
            ) AS entity_rows ON true
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
            ORDER BY candidates.ordinal ASC, candidates.published_at_ms ASC, candidates.news_item_id ASC
            """,
            (target_keys, NEWS_STORY_IDENTITY_VERSION),
        ).fetchall()
        grouped: dict[str, dict[str, Any]] = {}
        order: list[str] = []
        for row in rows:
            story_key = str(row["story_key"] or "")
            source_updated_at_ms = _required_story_brief_target_source_updated_at_ms(row)
            if story_key not in grouped:
                grouped[story_key] = {
                    "member_payloads": [],
                    "current_brief": _json_dict(row["current_brief"]) if row["current_brief"] is not None else None,
                    "latest_run": _json_dict(row["latest_run"]) if row["latest_run"] is not None else None,
                    "source_updated_at_ms": 0,
                }
                order.append(story_key)
            item = _json_dict(row["item"])
            grouped[story_key]["source_updated_at_ms"] = max(
                int(grouped[story_key]["source_updated_at_ms"]),
                source_updated_at_ms,
            )
            grouped[story_key]["member_payloads"].append(
                {
                    "item": item,
                    "entities": _story_brief_target_list(row, "entities"),
                    "token_mentions": _story_brief_target_list(row, "token_mentions"),
                    "fact_candidates": _story_brief_target_list(row, "fact_candidates"),
                }
            )

        results: list[dict[str, Any]] = []
        for story_key in order:
            group = grouped[story_key]
            member_payloads = list(group["member_payloads"])
            if not member_payloads:
                continue
            representative = member_payloads[0]
            representative_item = _json_dict(representative["item"])
            story = _story_projection_payload(story_key=story_key, member_payloads=member_payloads)
            story["story_identity_version"] = _required_story_item_text(
                representative_item,
                "story_identity_version",
            )
            story["market_scope_json"] = _required_story_item_json_value(representative_item, "market_scope_json")
            story["agent_admission_json"] = _required_story_item_mapping(
                representative_item,
                "agent_admission_json",
            )
            event_type = str(representative_item.get("event_type") or "").strip()
            if event_type:
                story["event_type"] = event_type
            results.append(
                {
                    "item": representative_item,
                    "current_brief": group["current_brief"],
                    "latest_run": group["latest_run"],
                    "token_mentions": [
                        token
                        for payload in member_payloads
                        for token in _story_brief_target_list(payload, "token_mentions")
                    ],
                    "fact_candidates": [
                        fact
                        for payload in member_payloads
                        for fact in _story_brief_target_list(payload, "fact_candidates")
                    ],
                    "entities": [
                        entity
                        for payload in member_payloads
                        for entity in _story_brief_target_list(payload, "entities")
                    ],
                    "story": story,
                    "member_items": [payload["item"] for payload in member_payloads],
                    "source_updated_at_ms": int(group["source_updated_at_ms"]),
                }
            )
        return results
