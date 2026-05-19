from __future__ import annotations

import json
import time
import uuid
from collections.abc import Sequence
from typing import Any

from psycopg.types.json import Jsonb

from gmgn_twitter_intel.domains.evidence.interfaces import decode_event_row
from gmgn_twitter_intel.domains.token_intel.interfaces import EventTokenProjectionQuery
from gmgn_twitter_intel.domains.watchlist_intel.types import (
    WatchlistTimelineCursorError,
    decode_watchlist_timeline_cursor,
    encode_watchlist_timeline_cursor,
    json_default,
    normalize_watchlist_handle,
)
from gmgn_twitter_intel.platform.db.postgres_client import transaction


class WatchlistIntelRepository:
    def __init__(self, conn: Any):
        self.conn = conn

    def enqueue_handle_summary_job(
        self,
        *,
        handle: str,
        next_run_at_ms: int,
        pending_signal_count: int,
        trigger_reason: str,
        max_attempts: int = 3,
        commit: bool = True,
    ) -> dict[str, Any]:
        normalized = normalize_watchlist_handle(handle)
        now_ms = _now_ms()
        row = self.conn.execute(
            """
            INSERT INTO watchlist_handle_summary_jobs(
              handle, status, next_run_at_ms, pending_signal_count, trigger_reason,
              lease_expires_at_ms, lease_token, attempt_count, max_attempts, last_error, created_at_ms, updated_at_ms
            )
            VALUES (%s, 'pending', %s, %s, %s, NULL, NULL, 0, %s, NULL, %s, %s)
            ON CONFLICT(handle) DO UPDATE SET
              status = CASE
                WHEN watchlist_handle_summary_jobs.status = 'running' THEN 'running'
                ELSE 'pending'
              END,
              next_run_at_ms = LEAST(watchlist_handle_summary_jobs.next_run_at_ms, excluded.next_run_at_ms),
              pending_signal_count = GREATEST(
                watchlist_handle_summary_jobs.pending_signal_count,
                excluded.pending_signal_count
              ),
              trigger_reason = excluded.trigger_reason,
              lease_token = CASE
                WHEN watchlist_handle_summary_jobs.status = 'running' THEN watchlist_handle_summary_jobs.lease_token
                ELSE NULL
              END,
              lease_expires_at_ms = CASE
                WHEN watchlist_handle_summary_jobs.status = 'running'
                  THEN watchlist_handle_summary_jobs.lease_expires_at_ms
                ELSE NULL
              END,
              max_attempts = excluded.max_attempts,
              attempt_count = CASE
                WHEN watchlist_handle_summary_jobs.status = 'dead' THEN 0
                ELSE watchlist_handle_summary_jobs.attempt_count
              END,
              last_error = NULL,
              updated_at_ms = excluded.updated_at_ms
            RETURNING *
            """,
            (
                normalized,
                int(next_run_at_ms),
                max(0, int(pending_signal_count)),
                str(trigger_reason or "signal"),
                max(1, int(max_attempts)),
                now_ms,
                now_ms,
            ),
        ).fetchone()
        if commit:
            self.conn.commit()
        return dict(row)

    def claim_next_summary_job(self, *, now_ms: int, lease_ms: int) -> dict[str, Any] | None:
        self.conn.execute(
            """
            UPDATE watchlist_handle_summary_jobs
            SET status = 'dead',
                lease_token = NULL,
                last_error = COALESCE(last_error, 'summary_job_attempts_exhausted'),
                updated_at_ms = %s
            WHERE status = 'running'
              AND lease_expires_at_ms IS NOT NULL
              AND lease_expires_at_ms <= %s
              AND attempt_count >= max_attempts
            """,
            (int(now_ms), int(now_ms)),
        )
        lease_token = f"lease-{uuid.uuid4().hex}"
        row = self.conn.execute(
            """
            WITH picked AS (
              SELECT handle
              FROM watchlist_handle_summary_jobs
              WHERE next_run_at_ms <= %s
                AND attempt_count < max_attempts
                AND (
                  status IN ('pending', 'failed')
                  OR (
                    status = 'running'
                    AND lease_expires_at_ms IS NOT NULL
                    AND lease_expires_at_ms <= %s
                  )
                )
              ORDER BY next_run_at_ms ASC, updated_at_ms ASC, handle ASC
              LIMIT 1
              FOR UPDATE SKIP LOCKED
            )
            UPDATE watchlist_handle_summary_jobs jobs
            SET status = 'running',
                lease_expires_at_ms = %s,
                lease_token = %s,
                attempt_count = jobs.attempt_count + 1,
                last_error = NULL,
                updated_at_ms = %s
            FROM picked
            WHERE jobs.handle = picked.handle
            RETURNING jobs.*
            """,
            (int(now_ms), int(now_ms), int(now_ms) + max(1, int(lease_ms)), lease_token, int(now_ms)),
        ).fetchone()
        self.conn.commit()
        return dict(row) if row else None

    def mark_summary_job_failed(
        self,
        job: dict[str, Any],
        error: str,
        *,
        now_ms: int,
        retry_delay_ms: int = 30_000,
        commit: bool = True,
    ) -> dict[str, Any] | None:
        handle = normalize_watchlist_handle(str(job.get("handle") or ""))
        lease_token = str(job.get("lease_token") or "")
        if not lease_token:
            return None
        attempt_count = int(job.get("attempt_count") or 0)
        max_attempts = max(1, int(job.get("max_attempts") or 1))
        status = "dead" if attempt_count >= max_attempts else "failed"
        row = self.conn.execute(
            """
            UPDATE watchlist_handle_summary_jobs
            SET status = %s,
                lease_expires_at_ms = NULL,
                lease_token = NULL,
                next_run_at_ms = %s,
                last_error = %s,
                updated_at_ms = %s
            WHERE handle = %s
              AND status = 'running'
              AND lease_token = %s
            RETURNING *
            """,
            (
                status,
                int(now_ms) + max(0, int(retry_delay_ms)),
                _compact_error(error),
                int(now_ms),
                handle,
                lease_token,
            ),
        ).fetchone()
        if commit:
            self.conn.commit()
        return dict(row) if row else None

    def release_job_for_backpressure(
        self,
        job: dict[str, Any],
        *,
        reason: str,
        now_ms: int,
        delay_ms: int = 30_000,
        commit: bool = True,
    ) -> dict[str, Any] | None:
        handle = normalize_watchlist_handle(str(job.get("handle") or ""))
        lease_token = str(job.get("lease_token") or "")
        if not lease_token:
            return None
        attempt_count = int(job.get("attempt_count") or 0)
        row = self.conn.execute(
            """
            UPDATE watchlist_handle_summary_jobs
            SET status = 'pending',
                lease_expires_at_ms = NULL,
                lease_token = NULL,
                attempt_count = GREATEST(0, attempt_count - 1),
                next_run_at_ms = %s,
                last_error = %s,
                updated_at_ms = %s
            WHERE handle = %s
              AND status = 'running'
              AND lease_token = %s
              AND attempt_count = %s
            RETURNING *
            """,
            (
                int(now_ms) + max(0, int(delay_ms)),
                _compact_error(f"agent_backpressure:{reason}"),
                int(now_ms),
                handle,
                lease_token,
                attempt_count,
            ),
        ).fetchone()
        if commit:
            self.conn.commit()
        return dict(row) if row else None

    def delete_summary_job(self, handle: str, *, commit: bool = True) -> bool:
        cursor = self.conn.execute(
            "DELETE FROM watchlist_handle_summary_jobs WHERE handle = %s",
            (normalize_watchlist_handle(handle),),
        )
        if commit:
            self.conn.commit()
        return bool(cursor.rowcount)

    def pending_summary_job(self, handle: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM watchlist_handle_summary_jobs WHERE handle = %s",
            (normalize_watchlist_handle(handle),),
        ).fetchone()
        return dict(row) if row else None

    def upsert_handle_summary(
        self,
        *,
        handle: str,
        generated_at_ms: int,
        input_window_start_ms: int,
        input_window_end_ms: int,
        input_event_count: int,
        signal_count_at_generation: int,
        model: str,
        summary_zh: str,
        topics: list[dict[str, Any]],
        raw_response: dict[str, Any],
        commit: bool = True,
    ) -> dict[str, Any]:
        now_ms = _now_ms()
        row = self.conn.execute(
            """
            INSERT INTO watchlist_handle_summaries(
              handle, generated_at_ms, input_window_start_ms, input_window_end_ms, input_event_count,
              signal_count_at_generation, model, summary_zh, topics_json, raw_response_json,
              created_at_ms, updated_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(handle) DO UPDATE SET
              generated_at_ms = excluded.generated_at_ms,
              input_window_start_ms = excluded.input_window_start_ms,
              input_window_end_ms = excluded.input_window_end_ms,
              input_event_count = excluded.input_event_count,
              signal_count_at_generation = excluded.signal_count_at_generation,
              model = excluded.model,
              summary_zh = excluded.summary_zh,
              topics_json = excluded.topics_json,
              raw_response_json = excluded.raw_response_json,
              updated_at_ms = excluded.updated_at_ms
            RETURNING *
            """,
            (
                normalize_watchlist_handle(handle),
                int(generated_at_ms),
                int(input_window_start_ms),
                int(input_window_end_ms),
                max(0, int(input_event_count)),
                max(0, int(signal_count_at_generation)),
                str(model or ""),
                str(summary_zh or ""),
                _json(topics),
                _json(raw_response),
                now_ms,
                now_ms,
            ),
        ).fetchone()
        if commit:
            self.conn.commit()
        return _decode_summary(dict(row))

    def insert_summary_run(
        self,
        *,
        run_id: str,
        handle: str,
        status: str,
        model: str,
        request_json: dict[str, Any],
        response_json: dict[str, Any] | None,
        input_event_count: int,
        usage_json: dict[str, Any] | None,
        error: str | None,
        started_at_ms: int,
        finished_at_ms: int,
        safety_net_used: bool = False,
        safety_net_retries: int = 0,
        parse_mode: str = "strict",
        commit: bool = True,
    ) -> dict[str, Any]:
        row = self.conn.execute(
            """
            INSERT INTO watchlist_handle_summary_runs(
              run_id, handle, status, model, request_json, response_json, input_event_count,
              usage_json, error, started_at_ms, finished_at_ms, created_at_ms,
              safety_net_used, safety_net_retries, parse_mode
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                str(run_id),
                normalize_watchlist_handle(handle),
                str(status),
                str(model or ""),
                _json(request_json),
                _json(response_json) if response_json is not None else None,
                max(0, int(input_event_count)),
                _json(usage_json or {}),
                _compact_error(error) if error else None,
                int(started_at_ms),
                int(finished_at_ms),
                _now_ms(),
                bool(safety_net_used),
                max(0, int(safety_net_retries)),
                str(parse_mode or "strict"),
            ),
        ).fetchone()
        if commit:
            self.conn.commit()
        return dict(row)

    def complete_handle_summary(
        self,
        *,
        job: dict[str, Any],
        summary: dict[str, Any],
        run: dict[str, Any],
        handle: str,
    ) -> dict[str, Any] | None:
        if normalize_watchlist_handle(handle) != normalize_watchlist_handle(str(job.get("handle") or "")):
            return None
        with transaction(self.conn):
            if not self.delete_claimed_summary_job(job, commit=False):
                return None
            stored_summary = self.upsert_handle_summary(**summary, commit=False)
            self.insert_summary_run(**run, commit=False)
        return stored_summary

    def delete_claimed_summary_job(self, job: dict[str, Any], *, commit: bool = True) -> bool:
        handle = normalize_watchlist_handle(str(job.get("handle") or ""))
        lease_token = str(job.get("lease_token") or "")
        if not lease_token:
            return False
        cursor = self.conn.execute(
            """
            DELETE FROM watchlist_handle_summary_jobs
            WHERE handle = %s
              AND status = 'running'
              AND lease_token = %s
            """,
            (handle, lease_token),
        )
        if commit:
            self.conn.commit()
        return bool(cursor.rowcount)

    def get_handle_summary(self, handle: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM watchlist_handle_summaries WHERE handle = %s",
            (normalize_watchlist_handle(handle),),
        ).fetchone()
        return _decode_summary(dict(row)) if row else None

    def count_signal_events_total(self, handle: str) -> int:
        row = self.conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM social_event_extractions se
            JOIN events e ON e.event_id = se.event_id
            WHERE lower(coalesce(se.author_handle, e.author_handle, '')) = %s
              AND se.is_signal_event = TRUE
            """,
            (normalize_watchlist_handle(handle),),
        ).fetchone()
        return int(row["count"] if row else 0)

    def signal_events_for_summary(self, *, handle: str, since_ms: int, limit: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT
              se.*,
              e.text_clean AS event_text,
              e.canonical_url AS canonical_url,
              e.cashtags_json AS event_cashtags_json,
              e.hashtags_json AS event_hashtags_json
            FROM social_event_extractions se
            JOIN events e ON e.event_id = se.event_id
            WHERE lower(coalesce(se.author_handle, e.author_handle, '')) = %s
              AND se.is_signal_event = TRUE
              AND btrim(se.summary_zh) <> ''
              AND se.received_at_ms >= %s
            ORDER BY se.received_at_ms DESC, se.event_id DESC
            LIMIT %s
            """,
            (normalize_watchlist_handle(handle), int(since_ms), max(0, int(limit))),
        ).fetchall()
        return [_decode_social_event(dict(row)) for row in rows]

    def timeline(self, *, handle: str, scope: str, cursor: str | None, limit: int) -> dict[str, Any]:
        normalized = normalize_watchlist_handle(handle)
        parsed_scope = _timeline_scope(scope)
        parsed_limit = max(0, int(limit))
        clauses = ["lower(e.author_handle) = %s"]
        params: list[Any] = [normalized]
        if parsed_scope == "signal":
            clauses.append("se.is_signal_event = TRUE")
        if cursor:
            try:
                cursor_received_at_ms, cursor_event_id = decode_watchlist_timeline_cursor(cursor)
            except WatchlistTimelineCursorError:
                raise
            clauses.append("(e.received_at_ms, e.event_id) < (%s, %s)")
            params.extend([cursor_received_at_ms, cursor_event_id])
        rows = self.conn.execute(
            f"""
            SELECT
              e.*,
              se.extraction_id AS se_extraction_id,
              se.schema_version AS se_schema_version,
              se.model_version AS se_model_version,
              se.event_type AS se_event_type,
              se.source_action AS se_source_action,
              se.subject AS se_subject,
              se.direction_hint AS se_direction_hint,
              se.attention_mechanism AS se_attention_mechanism,
              se.impact_hint AS se_impact_hint,
              se.semantic_novelty_hint AS se_semantic_novelty_hint,
              se.confidence AS se_confidence,
              se.is_signal_event AS se_is_signal_event,
              se.anchor_terms_json AS se_anchor_terms_json,
              se.token_candidates_json AS se_token_candidates_json,
              se.semantic_risks_json AS se_semantic_risks_json,
              se.summary_zh AS se_summary_zh,
              se.raw_response_json AS se_raw_response_json
            FROM events e
            LEFT JOIN social_event_extractions se ON se.event_id = e.event_id
            WHERE {" AND ".join(clauses)}
            ORDER BY e.received_at_ms DESC, e.event_id DESC
            LIMIT %s
            """,
            (*params, parsed_limit + 1),
        ).fetchall()
        decoded = [_decode_timeline_row(dict(row)) for row in rows]
        visible = decoded[:parsed_limit]
        resolutions = self.token_resolutions_for_events(tuple(str(item["event_id"]) for item in visible))
        for item in visible:
            item["token_resolutions"] = resolutions.get(str(item["event_id"]), [])
        has_more = len(decoded) > parsed_limit
        next_cursor = None
        if has_more and visible:
            last = visible[-1]
            next_cursor = encode_watchlist_timeline_cursor(
                received_at_ms=int(last["received_at_ms"]),
                event_id=str(last["event_id"]),
            )
        return {
            "query": {"handle": normalized, "scope": parsed_scope, "limit": parsed_limit},
            "items": visible,
            "has_more": has_more,
            "next_cursor": next_cursor,
        }

    def handles_overview(self, *, handles: Sequence[str], since_ms: int) -> list[dict[str, Any]]:
        normalized = [normalize_watchlist_handle(handle) for handle in handles]
        if not normalized:
            return []
        return [self._handle_overview_counts(handle=handle, since_ms=since_ms) for handle in normalized]

    def _handle_overview_counts(self, *, handle: str, since_ms: int) -> dict[str, Any]:
        last_event = self.conn.execute(
            """
            SELECT received_at_ms
            FROM events
            WHERE lower(author_handle) = %s
            ORDER BY received_at_ms DESC, event_id DESC
            LIMIT 1
            """,
            (handle,),
        ).fetchone()
        recent_source = self.conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM events
            WHERE lower(author_handle) = %s
              AND received_at_ms >= %s
            """,
            (handle, int(since_ms)),
        ).fetchone()
        recent_signal = self.conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM social_event_extractions
            WHERE author_handle = %s
              AND received_at_ms >= %s
              AND is_signal_event = TRUE
            """,
            (handle, int(since_ms)),
        ).fetchone()
        summary = self.conn.execute(
            """
            SELECT generated_at_ms, signal_count_at_generation
            FROM watchlist_handle_summaries
            WHERE handle = %s
            """,
            (handle,),
        ).fetchone()
        summary_row = dict(summary) if summary else {}
        recent_signal_count = int(recent_signal["count"] if recent_signal else 0)
        return _decode_handle_overview_row(
            {
                "handle": handle,
                "last_source_event_at_ms": last_event["received_at_ms"] if last_event else None,
                "recent_source_event_count": int(recent_source["count"] if recent_source else 0),
                "recent_signal_event_count": recent_signal_count,
                "total_signal_event_count": max(
                    int(summary_row.get("signal_count_at_generation") or 0),
                    recent_signal_count,
                ),
                "summary_generated_at_ms": summary_row.get("generated_at_ms"),
            }
        )

    def handle_overview(self, *, handle: str, scope: str, since_ms: int, limit: int = 500) -> dict[str, Any]:
        normalized = normalize_watchlist_handle(handle)
        parsed_scope = _timeline_scope(scope)
        cluster_limit = max(0, int(limit))
        clauses = ["lower(e.author_handle) = %s", "e.received_at_ms >= %s"]
        params: list[Any] = [normalized, int(since_ms)]
        if parsed_scope == "signal":
            clauses.append("se.is_signal_event = TRUE")
        rows = self.conn.execute(
            f"""
            SELECT
              e.*,
              se.extraction_id AS se_extraction_id,
              se.schema_version AS se_schema_version,
              se.model_version AS se_model_version,
              se.event_type AS se_event_type,
              se.source_action AS se_source_action,
              se.subject AS se_subject,
              se.direction_hint AS se_direction_hint,
              se.attention_mechanism AS se_attention_mechanism,
              se.impact_hint AS se_impact_hint,
              se.semantic_novelty_hint AS se_semantic_novelty_hint,
              se.confidence AS se_confidence,
              se.is_signal_event AS se_is_signal_event,
              se.anchor_terms_json AS se_anchor_terms_json,
              se.token_candidates_json AS se_token_candidates_json,
              se.semantic_risks_json AS se_semantic_risks_json,
              se.summary_zh AS se_summary_zh,
              se.raw_response_json AS se_raw_response_json
            FROM events e
            LEFT JOIN social_event_extractions se ON se.event_id = e.event_id
            WHERE {" AND ".join(clauses)}
            ORDER BY e.received_at_ms DESC, e.event_id DESC
            """,
            tuple(params),
        ).fetchall()
        events = [_decode_timeline_row(dict(row)) for row in rows]
        event_ids = tuple(str(item["event_id"]) for item in events)
        resolutions_by_event = self.token_resolutions_for_events(event_ids)
        for item in events:
            item["token_resolutions"] = resolutions_by_event.get(str(item["event_id"]), [])
        clusters = _overview_clusters(events)
        source_event_count = len(events)
        signal_event_count = sum(
            1
            for item in events
            if isinstance(item.get("social_event"), dict) and item["social_event"].get("is_signal_event")
        )
        last_source_event_at_ms = max((int(item.get("received_at_ms") or 0) for item in events), default=None)
        candidate_mention_count = _cluster_count(clusters["candidate_mention_clusters"])
        resolved_token_count = _cluster_count(clusters["resolved_token_clusters"])
        public_clusters = _limit_overview_clusters(clusters, cluster_limit)
        risk_notes = list(clusters["risk_notes"])
        if candidate_mention_count:
            risk_notes.append("candidate_mentions_unresolved")
        return {
            "query": {"handle": normalized, "scope": parsed_scope},
            "metrics": {
                "source_event_count": source_event_count,
                "signal_event_count": signal_event_count,
                "resolved_token_count": resolved_token_count,
                "candidate_mention_count": candidate_mention_count,
                "narrative_count": _cluster_count(clusters["narrative_clusters"]),
                "last_source_event_at_ms": last_source_event_at_ms,
            },
            "resolved_token_clusters": public_clusters["resolved_token_clusters"],
            "candidate_mention_clusters": public_clusters["candidate_mention_clusters"],
            "narrative_clusters": public_clusters["narrative_clusters"],
            "clusters_truncated": _overview_clusters_truncated(clusters, cluster_limit),
            "risk_notes": sorted(dict.fromkeys(risk_notes)),
        }

    def token_resolutions_for_events(self, event_ids: tuple[str, ...]) -> dict[str, list[dict[str, Any]]]:
        return EventTokenProjectionQuery(self.conn).for_events(event_ids)

    def handles_missing_summary_jobs(
        self,
        *,
        handles: tuple[str, ...],
        since_ms: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        normalized = [normalize_watchlist_handle(handle) for handle in handles]
        if not normalized:
            return []
        placeholders = ",".join("%s" for _ in normalized)
        rows = self.conn.execute(
            f"""
            SELECT lower(coalesce(se.author_handle, e.author_handle, '')) AS handle,
                   COUNT(*) AS signal_count,
                   MAX(se.received_at_ms) AS latest_signal_at_ms
            FROM social_event_extractions se
            JOIN events e ON e.event_id = se.event_id
            LEFT JOIN watchlist_handle_summaries s
              ON s.handle = lower(coalesce(se.author_handle, e.author_handle, ''))
            LEFT JOIN watchlist_handle_summary_jobs j
              ON j.handle = lower(coalesce(se.author_handle, e.author_handle, ''))
             AND j.status IN ('pending', 'running', 'failed')
            WHERE lower(coalesce(se.author_handle, e.author_handle, '')) IN ({placeholders})
              AND se.is_signal_event = TRUE
              AND se.received_at_ms >= %s
              AND j.handle IS NULL
              AND (s.handle IS NULL OR s.signal_count_at_generation < (
                SELECT COUNT(*)
                FROM social_event_extractions latest_se
                JOIN events latest_e ON latest_e.event_id = latest_se.event_id
                WHERE lower(coalesce(latest_se.author_handle, latest_e.author_handle, ''))
                  = lower(coalesce(se.author_handle, e.author_handle, ''))
                  AND latest_se.is_signal_event = TRUE
              ))
            GROUP BY lower(coalesce(se.author_handle, e.author_handle, ''))
            ORDER BY latest_signal_at_ms DESC
            LIMIT %s
            """,
            (*normalized, int(since_ms), max(0, int(limit))),
        ).fetchall()
        return [dict(row) for row in rows]


def _decode_timeline_row(row: dict[str, Any]) -> dict[str, Any]:
    event = decode_event_row(row)
    social_event = _decode_social_event_alias(row) if row.get("se_extraction_id") else None
    return {
        "event_id": str(row.get("event_id") or ""),
        "received_at_ms": int(row.get("received_at_ms") or 0),
        "author_handle": row.get("author_handle"),
        "action": row.get("action"),
        "text_clean": row.get("text_clean") or row.get("text"),
        "canonical_url": row.get("canonical_url"),
        "cashtags": _loads(row.get("cashtags_json"), []),
        "hashtags": _loads(row.get("hashtags_json"), []),
        "mentions": _loads(row.get("mentions_json"), []),
        "event": event,
        "social_event": social_event,
    }


def _decode_social_event_alias(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "extraction_id": row.get("se_extraction_id"),
        "schema_version": row.get("se_schema_version"),
        "model_version": row.get("se_model_version"),
        "event_type": row.get("se_event_type"),
        "source_action": row.get("se_source_action"),
        "subject": row.get("se_subject"),
        "direction_hint": row.get("se_direction_hint"),
        "attention_mechanism": row.get("se_attention_mechanism"),
        "impact_hint": row.get("se_impact_hint"),
        "semantic_novelty_hint": row.get("se_semantic_novelty_hint"),
        "confidence": row.get("se_confidence"),
        "is_signal_event": bool(row.get("se_is_signal_event")),
        "anchor_terms": _loads(row.get("se_anchor_terms_json"), []),
        "token_candidates": _loads(row.get("se_token_candidates_json"), []),
        "semantic_risks": _loads(row.get("se_semantic_risks_json"), []),
        "summary_zh": row.get("se_summary_zh") or "",
        "raw_response": _loads(row.get("se_raw_response_json"), {}),
    }


def _decode_social_event(row: dict[str, Any]) -> dict[str, Any]:
    row["anchor_terms"] = _loads(row.pop("anchor_terms_json", []), [])
    row["token_candidates"] = _loads(row.pop("token_candidates_json", []), [])
    row["semantic_risks"] = _loads(row.pop("semantic_risks_json", []), [])
    row["raw_response"] = _loads(row.pop("raw_response_json", {}), {})
    row["cashtags"] = _loads(row.pop("event_cashtags_json", []), [])
    row["hashtags"] = _loads(row.pop("event_hashtags_json", []), [])
    row["is_signal_event"] = bool(row.get("is_signal_event"))
    return row


def _decode_summary(row: dict[str, Any]) -> dict[str, Any]:
    row["topics"] = _loads(row.pop("topics_json", []), [])
    row["raw_response"] = _loads(row.pop("raw_response_json", {}), {})
    return row


def _decode_handle_overview_row(row: dict[str, Any]) -> dict[str, Any]:
    summary_generated_at_ms = row.get("summary_generated_at_ms")
    return {
        "handle": str(row.get("handle") or ""),
        "last_source_event_at_ms": _optional_int(row.get("last_source_event_at_ms")),
        "recent_source_event_count": int(row.get("recent_source_event_count") or 0),
        "recent_signal_event_count": int(row.get("recent_signal_event_count") or 0),
        "total_signal_event_count": int(row.get("total_signal_event_count") or 0),
        "summary_status": "ready" if summary_generated_at_ms is not None else "not_ready",
        "summary_is_stale": False,
        "summary_generated_at_ms": _optional_int(summary_generated_at_ms),
    }


def _overview_clusters(events: list[dict[str, Any]]) -> dict[str, Any]:
    resolved: dict[str, dict[str, Any]] = {}
    candidates: dict[str, dict[str, Any]] = {}
    narratives: dict[str, dict[str, Any]] = {}
    resolved_symbols: set[str] = set()

    for item in events:
        for resolution in _list(item.get("token_resolutions")):
            symbol = _token_symbol(resolution)
            target_id = str(resolution.get("target_id") or "")
            target_type = str(resolution.get("target_type") or "")
            key = f"{target_type}:{target_id}" if target_id else f"symbol:{symbol}"
            label = _money_label(symbol or target_id.rsplit(":", maxsplit=1)[-1])
            resolved_symbols.add(_symbol_key(symbol or label))
            cluster = resolved.setdefault(
                key,
                {
                    "label": label,
                    "count": 0,
                    "query": label,
                    "kind": "resolved_token",
                    "target_type": target_type or None,
                    "target_id": target_id or None,
                    "symbol": symbol,
                    "source": "token_resolutions",
                },
            )
            cluster["count"] += 1

    for item in events:
        raw_social_event = item.get("social_event")
        social_event = raw_social_event if isinstance(raw_social_event, dict) else {}
        for candidate in _list(social_event.get("token_candidates")):
            symbol = _candidate_symbol(candidate)
            if not symbol:
                continue
            key = _symbol_key(symbol)
            if key in resolved_symbols:
                continue
            _increment_cluster(
                candidates,
                key,
                label=_money_label(symbol),
                query=_money_label(symbol),
                kind="candidate_mention",
                source="social_event_candidates",
            )
        for cashtag in _list(item.get("cashtags")):
            symbol = _clean_symbol(cashtag)
            if not symbol:
                continue
            key = _symbol_key(symbol)
            if key in resolved_symbols or key in candidates:
                continue
            _increment_cluster(
                candidates,
                key,
                label=_money_label(symbol),
                query=_money_label(symbol),
                kind="candidate_mention",
                source="event_cashtags",
            )
        for hashtag in _list(item.get("hashtags")):
            term = _clean_hashtag(hashtag)
            if term:
                _increment_cluster(
                    narratives,
                    f"hashtag:{term.lower()}",
                    label=f"#{term}",
                    query=f"#{term}",
                    kind="narrative",
                    source="event_hashtags",
                )
        for anchor in _list(social_event.get("anchor_terms")):
            term = _anchor_term(anchor)
            if term and _symbol_key(term) not in resolved_symbols:
                _increment_cluster(
                    narratives,
                    f"anchor:{term.lower()}",
                    label=term,
                    query=term,
                    kind="narrative",
                    source="anchor_terms",
                )

    return {
        "resolved_token_clusters": _sorted_clusters(resolved.values()),
        "candidate_mention_clusters": _sorted_clusters(candidates.values()),
        "narrative_clusters": _sorted_clusters(narratives.values()),
        "risk_notes": [],
    }


def _increment_cluster(
    clusters: dict[str, dict[str, Any]],
    key: str,
    *,
    label: str,
    query: str,
    kind: str,
    source: str,
) -> None:
    cluster = clusters.setdefault(
        key,
        {
            "label": label,
            "count": 0,
            "query": query,
            "kind": kind,
            "source": source,
        },
    )
    cluster["count"] += 1


def _sorted_clusters(clusters: Any) -> list[dict[str, Any]]:
    return sorted(
        (dict(cluster) for cluster in clusters),
        key=lambda item: (-int(item.get("count") or 0), str(item.get("label") or "").lower()),
    )


def _cluster_count(clusters: list[dict[str, Any]]) -> int:
    return sum(int(cluster.get("count") or 0) for cluster in clusters)


def _limit_overview_clusters(clusters: dict[str, Any], limit: int) -> dict[str, Any]:
    return {
        "resolved_token_clusters": clusters["resolved_token_clusters"][:limit],
        "candidate_mention_clusters": clusters["candidate_mention_clusters"][:limit],
        "narrative_clusters": clusters["narrative_clusters"][:limit],
    }


def _overview_clusters_truncated(clusters: dict[str, Any], limit: int) -> bool:
    return any(
        len(clusters[key]) > limit
        for key in ("resolved_token_clusters", "candidate_mention_clusters", "narrative_clusters")
    )


def _token_symbol(value: dict[str, Any]) -> str | None:
    symbol = _clean_symbol(value.get("symbol"))
    if symbol:
        return symbol
    target_id = str(value.get("target_id") or "")
    if str(value.get("target_type") or "") == "CexToken" and target_id:
        return _clean_symbol(target_id.rsplit(":", maxsplit=1)[-1])
    return None


def _candidate_symbol(value: Any) -> str | None:
    if isinstance(value, dict):
        return _clean_symbol(value.get("symbol") or value.get("ticker") or value.get("token"))
    return _clean_symbol(value)


def _anchor_term(value: Any) -> str | None:
    if isinstance(value, dict):
        term = str(value.get("term") or value.get("label") or "").strip()
    else:
        term = str(value or "").strip()
    if not term or term.startswith(("$", "#", "@")):
        return None
    if len(term) > 48:
        return None
    return term


def _clean_symbol(value: Any) -> str | None:
    symbol = str(value or "").strip().lstrip("$").upper()
    return symbol or None


def _clean_hashtag(value: Any) -> str | None:
    tag = str(value or "").strip().lstrip("#")
    return tag or None


def _money_label(value: str) -> str:
    symbol = _clean_symbol(value) or str(value or "").strip()
    return f"${symbol}" if symbol and not symbol.startswith("$") else symbol


def _symbol_key(value: Any) -> str:
    return (_clean_symbol(value) or "").upper()


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _optional_int(value: Any) -> int | None:
    return int(value) if value is not None else None


def _timeline_scope(value: str) -> str:
    if value in {"signal", "all"}:
        return value
    raise ValueError("invalid_scope")


def _loads(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if not isinstance(value, str):
        return value
    if not value.strip():
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _json(value: Any) -> Jsonb:
    return Jsonb(value, dumps=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, default=json_default))


def _compact_error(error: Any) -> str:
    return str(error or "")[:1000]


def _now_ms() -> int:
    return int(time.time() * 1000)


__all__ = ["WatchlistIntelRepository"]
