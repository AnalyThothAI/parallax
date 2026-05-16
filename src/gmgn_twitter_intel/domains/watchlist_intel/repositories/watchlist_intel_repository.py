from __future__ import annotations

import json
import time
import uuid
from typing import Any

from psycopg.types.json import Jsonb

from gmgn_twitter_intel.domains.asset_market.read_models.message_price_payload import message_price_payload
from gmgn_twitter_intel.domains.evidence.interfaces import decode_event_row
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
        commit: bool = True,
    ) -> dict[str, Any]:
        row = self.conn.execute(
            """
            INSERT INTO watchlist_handle_summary_runs(
              run_id, handle, status, model, request_json, response_json, input_event_count,
              usage_json, error, started_at_ms, finished_at_ms, created_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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

    def token_resolutions_for_events(self, event_ids: tuple[str, ...]) -> dict[str, list[dict[str, Any]]]:
        ids = tuple(str(item) for item in event_ids if str(item or "").strip())
        if not ids:
            return {}
        placeholders = ",".join("%s" for _ in ids)
        rows = self.conn.execute(
            f"""
            SELECT
              tir.resolution_id,
              tir.intent_id,
              tir.event_id,
              tir.asset_id,
              tir.primary_venue_id,
              tir.target_type,
              tir.target_id,
              COALESCE(tir.pricefeed_id, preferred_price_feed.pricefeed_id) AS pricefeed_id,
              tir.resolution_status,
              tir.identity_status,
              tir.confidence,
              tir.resolver_policy_version,
              tir.reasons_json,
              tir.risks_json,
              tir.decision_time_ms,
              tir.created_at_ms,
              tir.reason_codes_json,
              tir.candidate_ids_json,
              tir.lookup_keys_json,
              tir.registry_version,
              tir.record_status,
              tir.is_current,
              tir.superseded_at_ms,
              COALESCE(
                asset_identity_current.canonical_symbol,
                cex_tokens.base_symbol,
                price_feeds.base_symbol
              ) AS symbol,
              price_feeds.quote_symbol AS quote_symbol,
              event_tick.tick_id AS market_tick_id,
              event_tick.source_provider AS market_tick_provider,
              event_tick.observed_at_ms AS market_tick_observed_at_ms,
              event_tick.price_usd,
              NULL::numeric AS price_quote,
              NULL::text AS price_quote_symbol,
              event_market_capture.capture_method AS market_capture_method,
              event_market_capture.tick_lag_ms AS market_tick_lag_ms
            FROM token_intent_resolutions tir
            LEFT JOIN asset_identity_current
              ON tir.target_type = 'Asset'
             AND asset_identity_current.asset_id = tir.target_id
            LEFT JOIN cex_tokens
              ON tir.target_type = 'CexToken'
             AND cex_tokens.cex_token_id = tir.target_id
            LEFT JOIN LATERAL (
              SELECT *
              FROM price_feeds
              WHERE tir.target_type = 'CexToken'
                AND price_feeds.subject_type = 'CexToken'
                AND price_feeds.subject_id = tir.target_id
                AND price_feeds.feed_type LIKE 'cex_%%'
                AND price_feeds.status IN ('candidate', 'canonical')
              ORDER BY
                CASE
                  WHEN price_feeds.feed_type = 'cex_spot' THEN 0
                  WHEN price_feeds.feed_type = 'cex_swap' THEN 1
                  ELSE 2
                END,
                CASE
                  WHEN price_feeds.quote_symbol = 'USDT' THEN 0
                  WHEN price_feeds.quote_symbol = 'USD' THEN 1
                  WHEN price_feeds.quote_symbol = 'USDC' THEN 2
                  ELSE 9
                END,
                price_feeds.updated_at_ms DESC,
                price_feeds.native_market_id ASC
              LIMIT 1
            ) preferred_price_feed ON true
            LEFT JOIN price_feeds
              ON price_feeds.pricefeed_id = COALESCE(tir.pricefeed_id, preferred_price_feed.pricefeed_id)
            LEFT JOIN enriched_events event_market_capture
              ON event_market_capture.event_id = tir.event_id
             AND event_market_capture.intent_id = tir.intent_id
             AND event_market_capture.resolution_id = tir.resolution_id
            LEFT JOIN market_ticks event_tick
              ON event_tick.tick_id = event_market_capture.tick_id
            WHERE tir.event_id IN ({placeholders})
              AND tir.is_current = TRUE
              AND tir.target_type IN ('Asset', 'CexToken')
              AND tir.target_id IS NOT NULL
            ORDER BY tir.event_id, tir.decision_time_ms, tir.resolution_id
            """,
            ids,
        ).fetchall()
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            decoded = _decode_token_resolution(dict(row))
            grouped.setdefault(str(decoded.get("event_id") or ""), []).append(decoded)
        return grouped

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


def _decode_token_resolution(row: dict[str, Any]) -> dict[str, Any]:
    row["reason_codes_json"] = _loads(row.get("reason_codes_json"), [])
    row["candidate_ids_json"] = _loads(row.get("candidate_ids_json"), [])
    row["lookup_keys_json"] = _loads(row.get("lookup_keys_json"), [])
    price = message_price_payload(row)
    row["symbol"] = _resolution_symbol(row)
    for key in _TOKEN_RESOLUTION_PRIVATE_PRICE_KEYS:
        row.pop(key, None)
    row["price"] = price
    return row


_TOKEN_RESOLUTION_PRIVATE_PRICE_KEYS = {
    "market_tick_id",
    "market_tick_provider",
    "market_tick_observed_at_ms",
    "market_capture_method",
    "market_tick_lag_ms",
    "price_usd",
    "price_quote",
    "price_quote_symbol",
    "quote_symbol",
}


def _resolution_symbol(row: dict[str, Any]) -> str | None:
    symbol = _clean_text(row.get("symbol"))
    if symbol:
        return symbol
    if row.get("target_type") != "CexToken":
        return None
    target_id = _clean_text(row.get("target_id"))
    if not target_id:
        return None
    return target_id.rsplit(":", maxsplit=1)[-1].upper()


def _clean_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _decode_summary(row: dict[str, Any]) -> dict[str, Any]:
    row["topics"] = _loads(row.pop("topics_json", []), [])
    row["raw_response"] = _loads(row.pop("raw_response_json", {}), {})
    return row


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
