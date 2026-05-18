from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from typing import Any

from psycopg.types.json import Jsonb

from gmgn_twitter_intel.domains.narrative_intel._constants import NARRATIVE_SCHEMA_VERSION
from gmgn_twitter_intel.domains.narrative_intel.services.fingerprints import (
    label_fingerprint as build_label_fingerprint,
)
from gmgn_twitter_intel.domains.narrative_intel.services.fingerprints import (
    source_fingerprint as build_source_fingerprint,
)
from gmgn_twitter_intel.domains.narrative_intel.services.fingerprints import text_fingerprint


class NarrativeRepository:
    def __init__(self, conn: Any):
        self.conn = conn

    def upsert_admissions_from_radar_rows(
        self,
        rows: Sequence[dict[str, Any]],
        *,
        window: str,
        scope: str,
        schema_version: str,
        now_ms: int,
        source_limit: int,
    ) -> dict[str, int]:
        upserted = 0
        for row in list(rows)[: max(1, int(source_limit))]:
            target_type = _clean(row.get("target_type"))
            target_id = _clean(row.get("target_id"))
            if not target_type or not target_id:
                continue
            source_event_ids = list(row.get("source_event_ids") or row.get("source_event_ids_json") or [])
            source_max_received_at_ms = _int(row.get("source_max_received_at_ms") or row.get("computed_at_ms"))
            payload = {
                "admission_id": deterministic_admission_id(
                    target_type=target_type,
                    target_id=target_id,
                    window=window,
                    scope=scope,
                    schema_version=schema_version,
                ),
                "target_type": target_type,
                "target_id": target_id,
                "window": window,
                "scope": scope,
                "schema_version": schema_version,
                "status": str(row.get("status") or "admitted"),
                "reason": str(row.get("reason") or "radar_row"),
                "priority": _int(row.get("priority")) or 0,
                "last_radar_rank": _int(row.get("rank") or row.get("last_radar_rank")),
                "last_rank_score": _float(row.get("rank_score") or row.get("last_rank_score")),
                "source_event_ids_json": _json(source_event_ids),
                "source_fingerprint": build_source_fingerprint(source_event_ids, source_max_received_at_ms),
                "source_max_received_at_ms": source_max_received_at_ms,
                "admitted_at_ms": now_ms,
                "last_seen_at_ms": now_ms,
                "updated_at_ms": now_ms,
            }
            self.conn.execute(
                """
                INSERT INTO narrative_admissions (
                  admission_id, target_type, target_id, "window", scope, schema_version, status, reason,
                  priority, last_radar_rank, last_rank_score, source_event_ids_json, source_fingerprint,
                  source_max_received_at_ms, admitted_at_ms, last_seen_at_ms, updated_at_ms
                )
                VALUES (
                  %(admission_id)s, %(target_type)s, %(target_id)s, %(window)s, %(scope)s, %(schema_version)s,
                  %(status)s, %(reason)s, %(priority)s, %(last_radar_rank)s, %(last_rank_score)s,
                  %(source_event_ids_json)s, %(source_fingerprint)s, %(source_max_received_at_ms)s,
                  %(admitted_at_ms)s, %(last_seen_at_ms)s, %(updated_at_ms)s
                )
                ON CONFLICT (target_type, target_id, "window", scope, schema_version)
                DO UPDATE SET
                  status = EXCLUDED.status,
                  reason = EXCLUDED.reason,
                  priority = EXCLUDED.priority,
                  last_radar_rank = EXCLUDED.last_radar_rank,
                  last_rank_score = EXCLUDED.last_rank_score,
                  source_event_ids_json = EXCLUDED.source_event_ids_json,
                  source_fingerprint = EXCLUDED.source_fingerprint,
                  source_max_received_at_ms = EXCLUDED.source_max_received_at_ms,
                  last_seen_at_ms = EXCLUDED.last_seen_at_ms,
                  updated_at_ms = EXCLUDED.updated_at_ms
                """,
                payload,
            )
            upserted += 1
        _commit_if_available(self.conn)
        return {"upserted": upserted, "seen": len(rows)}

    def admitted_radar_rows(
        self,
        *,
        window: str,
        scope: str,
        limit: int,
        projection_version: str,
    ) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT row_id, target_type, target_id, rank, computed_at_ms,
                   NULLIF(factor_snapshot_json->'composite'->>'rank_score', '')::double precision AS rank_score,
                   source_event_ids_json
            FROM token_radar_rows
            WHERE "window" = %s
              AND scope = %s
              AND projection_version = %s
              AND target_type IS NOT NULL
              AND target_id IS NOT NULL
            ORDER BY computed_at_ms DESC, rank ASC
            LIMIT %s
            """,
            (window, scope, projection_version, int(limit)),
        ).fetchall()
        return [_row(row) for row in rows]

    def admissions_for_window_scope(
        self,
        *,
        window: str,
        scope: str,
        schema_version: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM narrative_admissions
            WHERE "window" = %s
              AND scope = %s
              AND schema_version = %s
            ORDER BY priority DESC, last_seen_at_ms DESC
            LIMIT %s
            """,
            (window, scope, schema_version, int(limit)),
        ).fetchall()
        return [_row(row) for row in rows]

    def due_admissions_for_semantics(self, *, now_ms: int, limit: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM narrative_admissions
            WHERE status = 'admitted' AND next_semantics_due_at_ms <= %s
            ORDER BY priority DESC, last_seen_at_ms DESC
            LIMIT %s
            """,
            (int(now_ms), int(limit)),
        ).fetchall()
        return [_row(row) for row in rows]

    def due_mentions_for_labeling(self, *, now_ms: int, limit: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT semantics.*,
                   events.text_clean AS text_clean,
                   events.author_handle,
                   events.tweet_id,
                   events.raw_json AS reference_json
            FROM token_mention_semantics AS semantics
            JOIN events ON events.event_id = semantics.event_id
            WHERE semantics.status IN ('queued', 'retryable_error', 'stale')
              AND semantics.next_retry_at_ms <= %s
            ORDER BY semantics.source_received_at_ms DESC, semantics.semantic_id ASC
            LIMIT %s
            """,
            (int(now_ms), int(limit)),
        ).fetchall()
        return [_row(row) for row in rows]

    def source_mentions_for_admission(
        self,
        *,
        target_type: str,
        target_id: str,
        since_ms: int,
        watched_only: bool,
        limit: int,
    ) -> list[dict[str, Any]]:
        watched_clause = "AND events.is_watched = true" if watched_only else ""
        rows = self.conn.execute(
            f"""
            SELECT
              events.event_id,
              resolution.target_type,
              resolution.target_id,
              events.text_clean AS text_clean,
              events.author_handle,
              events.received_at_ms AS source_received_at_ms,
              events.tweet_id,
              events.raw_json AS reference_json
            FROM token_intent_resolutions AS resolution
            JOIN events ON events.event_id = resolution.event_id
            WHERE resolution.target_type = %s
              AND resolution.target_id = %s
              AND COALESCE(resolution.is_current, true) = true
              AND events.received_at_ms >= %s
              {watched_clause}
            ORDER BY events.received_at_ms DESC, events.event_id DESC
            LIMIT %s
            """,
            (target_type, target_id, int(since_ms), int(limit)),
        ).fetchall()
        return [_row(row) for row in rows]

    def enqueue_missing_mention_semantics(
        self,
        source_rows: Sequence[dict[str, Any]],
        *,
        schema_version: str,
        model_version: str,
        now_ms: int,
    ) -> dict[str, int]:
        inserted = 0
        existing = 0
        for source in source_rows:
            event_id = _required(source, "event_id")
            target_type = _required(source, "target_type")
            target_id = _required(source, "target_id")
            fingerprint = str(source.get("text_fingerprint") or text_fingerprint(str(source.get("text_clean") or "")))
            semantic_id = deterministic_semantic_id(
                event_id=event_id,
                target_type=target_type,
                target_id=target_id,
                schema_version=schema_version,
                text_fingerprint=fingerprint,
            )
            cursor = self.conn.execute(
                """
                INSERT INTO token_mention_semantics (
                  semantic_id, event_id, target_type, target_id, schema_version, model_version,
                  text_fingerprint, status, source_received_at_ms, queued_at_ms, next_retry_at_ms
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'queued', %s, %s, 0)
                ON CONFLICT (event_id, target_type, target_id, schema_version, text_fingerprint)
                DO NOTHING
                """,
                (
                    semantic_id,
                    event_id,
                    target_type,
                    target_id,
                    schema_version,
                    model_version,
                    fingerprint,
                    _int(source.get("source_received_at_ms") or source.get("received_at_ms")) or now_ms,
                    now_ms,
                ),
            )
            if int(getattr(cursor, "rowcount", 0) or 0) > 0:
                inserted += 1
            else:
                existing += 1
        _commit_if_available(self.conn)
        return {"inserted": inserted, "existing": existing}

    def mark_admissions_semantics_scanned(
        self,
        admission_ids: Sequence[str],
        *,
        next_due_at_ms: int,
        now_ms: int,
    ) -> dict[str, int]:
        ids = _stable_ids(admission_ids)
        if not ids:
            return {"updated": 0}
        cursor = self.conn.execute(
            """
            UPDATE narrative_admissions
            SET next_semantics_due_at_ms = %s,
                updated_at_ms = %s
            WHERE admission_id = ANY(%s)
            """,
            (int(next_due_at_ms), int(now_ms), ids),
        )
        _commit_if_available(self.conn)
        return {"updated": int(getattr(cursor, "rowcount", 0) or 0)}

    def record_narrative_model_run(self, run: dict[str, Any], *, commit: bool = True) -> dict[str, Any]:
        payload = dict(run)
        payload.setdefault(
            "run_id",
            deterministic_run_id(
                stage=str(payload.get("stage") or ""),
                input_hash=str(payload.get("input_hash") or ""),
                started_at_ms=int(payload.get("started_at_ms") or 0),
            ),
        )
        payload.setdefault("schema_version", NARRATIVE_SCHEMA_VERSION)
        payload.setdefault("prompt_version", "unknown")
        payload.setdefault("request_json", {})
        payload.setdefault("response_json", None)
        payload.setdefault("usage_json", {})
        payload.setdefault("trace_metadata_json", {})
        payload.setdefault("target_type", None)
        payload.setdefault("target_id", None)
        payload.setdefault("window", None)
        payload.setdefault("scope", None)
        payload.setdefault("artifact_version_hash", None)
        payload.setdefault("output_hash", None)
        payload.setdefault("error", None)
        payload.setdefault("status", "done")
        payload.setdefault("finished_at_ms", payload.get("started_at_ms") or 0)
        payload.setdefault(
            "latency_ms",
            max(0, int(payload["finished_at_ms"]) - int(payload.get("started_at_ms") or 0)),
        )
        payload.setdefault("evidence_event_ids_json", [])
        self.conn.execute(
            """
            INSERT INTO narrative_model_runs (
              run_id, stage, target_type, target_id, "window", scope, provider, model, schema_version,
              prompt_version, artifact_version_hash, input_hash, output_hash, evidence_event_ids_json,
              request_json, response_json, usage_json, trace_metadata_json, status, error,
              started_at_ms, finished_at_ms, latency_ms
            )
            VALUES (
              %(run_id)s, %(stage)s, %(target_type)s, %(target_id)s, %(window)s, %(scope)s, %(provider)s,
              %(model)s, %(schema_version)s, %(prompt_version)s, %(artifact_version_hash)s,
              %(input_hash)s, %(output_hash)s, %(evidence_event_ids_json)s, %(request_json)s,
              %(response_json)s, %(usage_json)s, %(trace_metadata_json)s, %(status)s, %(error)s,
              %(started_at_ms)s, %(finished_at_ms)s, %(latency_ms)s
            )
            ON CONFLICT (run_id) DO UPDATE SET
              response_json = EXCLUDED.response_json,
              usage_json = EXCLUDED.usage_json,
              trace_metadata_json = EXCLUDED.trace_metadata_json,
              status = EXCLUDED.status,
              error = EXCLUDED.error,
              finished_at_ms = EXCLUDED.finished_at_ms,
              latency_ms = EXCLUDED.latency_ms
            """,
            {
                **payload,
                "evidence_event_ids_json": _json(payload.get("evidence_event_ids_json") or []),
                "request_json": _json(payload.get("request_json") or {}),
                "response_json": None if payload.get("response_json") is None else _json(payload.get("response_json")),
                "usage_json": _json(payload.get("usage_json") or {}),
                "trace_metadata_json": _json(payload.get("trace_metadata_json") or {}),
            },
        )
        if commit:
            _commit_if_available(self.conn)
        return payload

    def complete_mention_semantics_batch(
        self,
        *,
        run_id: str,
        labels: Sequence[dict[str, Any]],
        failures: Sequence[dict[str, Any]],
        now_ms: int,
    ) -> dict[str, int]:
        labeled = 0
        unavailable = 0
        failed = 0
        for label in labels:
            status = str(label.get("status") or "labeled")
            if status == "semantic_unavailable":
                unavailable += 1
            else:
                status = "labeled"
                labeled += 1
            self.conn.execute(
                """
                UPDATE token_mention_semantics
                SET status = %s,
                    trade_stance = %s,
                    attention_valence = %s,
                    narrative_cluster_key = %s,
                    claim_type = %s,
                    evidence_type = %s,
                    semantic_confidence = %s,
                    co_mentioned_targets_json = %s,
                    evidence_refs_json = %s,
                    raw_label_json = %s,
                    model_run_id = %s,
                    computed_at_ms = %s,
                    error = NULL
                WHERE event_id = %s AND target_type = %s AND target_id = %s
                """,
                (
                    status,
                    str(label.get("trade_stance") or "unknown"),
                    str(label.get("attention_valence") or "unknown"),
                    label.get("narrative_cluster_key"),
                    str(label.get("claim_type") or "other"),
                    str(label.get("evidence_type") or "unknown"),
                    float(label.get("semantic_confidence") or 0.0),
                    _json(label.get("co_mentioned_targets") or []),
                    _json(label.get("evidence_refs") or []),
                    _json(label.get("raw_label") or label),
                    run_id,
                    now_ms,
                    _required(label, "event_id"),
                    _required(label, "target_type"),
                    _required(label, "target_id"),
                ),
            )
        for failure in failures:
            failed += 1
            self.conn.execute(
                """
                UPDATE token_mention_semantics
                SET status = 'retryable_error',
                    retry_count = retry_count + 1,
                    next_retry_at_ms = %s,
                    error = %s
                WHERE event_id = %s AND target_type = %s AND target_id = %s
                """,
                (
                    int(failure.get("next_retry_at_ms") or now_ms + 60_000),
                    str(failure.get("error") or "provider_failure"),
                    _required(failure, "event_id"),
                    _required(failure, "target_type"),
                    _required(failure, "target_id"),
                ),
            )
        _commit_if_available(self.conn)
        return {"labeled": labeled, "semantic_unavailable": unavailable, "failed": failed}

    def due_digest_targets(self, *, now_ms: int, limit: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM narrative_admissions
            WHERE status = 'admitted' AND next_digest_due_at_ms <= %s
            ORDER BY priority DESC, last_seen_at_ms DESC
            LIMIT %s
            """,
            (int(now_ms), int(limit)),
        ).fetchall()
        return [_row(row) for row in rows]

    def digest_context(
        self,
        *,
        target_type: str,
        target_id: str,
        window: str,
        scope: str,
        since_ms: int,
        max_mentions: int,
    ) -> dict[str, Any]:
        semantic_rows = self.conn.execute(
            """
            SELECT semantics.*,
                   events.text_clean AS text_clean,
                   events.author_handle,
                   events.tweet_id,
                   events.raw_json AS reference_json
            FROM token_mention_semantics AS semantics
            JOIN events ON events.event_id = semantics.event_id
            WHERE semantics.target_type = %s
              AND semantics.target_id = %s
              AND semantics.source_received_at_ms >= %s
            ORDER BY semantics.source_received_at_ms DESC
            LIMIT %s
            """,
            (target_type, target_id, int(since_ms), int(max_mentions)),
        ).fetchall()
        semantics = [_row(row) for row in semantic_rows]
        return {
            "target_type": target_type,
            "target_id": target_id,
            "window": window,
            "scope": scope,
            "mentions": semantics,
            "semantic_rows": semantics,
            "source_event_count": len(semantics),
            "labeled_event_count": sum(1 for row in semantics if row.get("status") == "labeled"),
            "independent_author_count": _author_count(semantics),
            "allowed_refs": _allowed_refs_for_semantics(semantics),
        }

    def replace_current_digest(self, digest: dict[str, Any], *, now_ms: int) -> dict[str, Any]:
        payload = _digest_payload(digest, now_ms=now_ms)
        self.conn.execute(
            """
            UPDATE token_discussion_digests
            SET is_current = false,
                superseded_at_ms = %s
            WHERE target_type = %s
              AND target_id = %s
              AND "window" = %s
              AND scope = %s
              AND schema_version = %s
              AND is_current = true
            """,
            (
                now_ms,
                payload["target_type"],
                payload["target_id"],
                payload["window"],
                payload["scope"],
                payload["schema_version"],
            ),
        )
        self.conn.execute(
            """
            INSERT INTO token_discussion_digests (
              digest_id, target_type, target_id, "window", scope, schema_version, model_version,
              status, is_current, source_fingerprint, label_fingerprint, headline_zh,
              dominant_narratives_json, bull_view_json, bear_view_json, stance_mix_json,
              attention_valence_mix_json, propagation_read_json, reflexivity_read_json,
              watch_triggers_json, invalidation_conditions_json, data_gaps_json,
              semantic_coverage, source_event_count, labeled_event_count, independent_author_count,
              evidence_refs_json, model_run_id, computed_at_ms, expires_at_ms, superseded_at_ms
            )
            VALUES (
              %(digest_id)s, %(target_type)s, %(target_id)s, %(window)s, %(scope)s, %(schema_version)s,
              %(model_version)s, %(status)s, true, %(source_fingerprint)s, %(label_fingerprint)s,
              %(headline_zh)s, %(dominant_narratives_json)s, %(bull_view_json)s, %(bear_view_json)s,
              %(stance_mix_json)s, %(attention_valence_mix_json)s, %(propagation_read_json)s,
              %(reflexivity_read_json)s, %(watch_triggers_json)s, %(invalidation_conditions_json)s,
              %(data_gaps_json)s, %(semantic_coverage)s, %(source_event_count)s, %(labeled_event_count)s,
              %(independent_author_count)s, %(evidence_refs_json)s, %(model_run_id)s, %(computed_at_ms)s,
              %(expires_at_ms)s, %(superseded_at_ms)s
            )
            """,
            payload,
        )
        _commit_if_available(self.conn)
        return {
            **digest,
            "digest_id": payload["digest_id"],
            "computed_at_ms": payload["computed_at_ms"],
            "is_current": True,
        }

    def current_digests_for_targets(
        self,
        targets: Sequence[dict[str, str]],
        *,
        window: str,
        scope: str,
        schema_version: str,
    ) -> dict[tuple[str, str], dict[str, Any]]:
        result: dict[tuple[str, str], dict[str, Any]] = {}
        for target in targets:
            row = self.conn.execute(
                """
                SELECT *
                FROM token_discussion_digests
                WHERE target_type = %s
                  AND target_id = %s
                  AND "window" = %s
                  AND scope = %s
                  AND schema_version = %s
                  AND is_current = true
                """,
                (target["target_type"], target["target_id"], window, scope, schema_version),
            ).fetchone()
            if row:
                decoded = _row(row)
                result[(decoded["target_type"], decoded["target_id"])] = decoded
        return result

    def semantics_for_posts(
        self,
        posts: Sequence[dict[str, Any]],
        *,
        schema_version: str,
    ) -> dict[tuple[str, str, str], dict[str, Any]]:
        result: dict[tuple[str, str, str], dict[str, Any]] = {}
        for post in posts:
            row = self.conn.execute(
                """
                SELECT *
                FROM token_mention_semantics
                WHERE event_id = %s
                  AND target_type = %s
                  AND target_id = %s
                  AND schema_version = %s
                ORDER BY computed_at_ms DESC NULLS LAST, queued_at_ms DESC NULLS LAST
                LIMIT 1
                """,
                (
                    post["event_id"],
                    post["target_type"],
                    post["target_id"],
                    schema_version,
                ),
            ).fetchone()
            if row:
                decoded = _row(row)
                result[(decoded["event_id"], decoded["target_type"], decoded["target_id"])] = decoded
        return result


def deterministic_admission_id(
    *,
    target_type: str,
    target_id: str,
    window: str,
    scope: str,
    schema_version: str,
) -> str:
    return _stable_id("narrative_admission", target_type, target_id, window, scope, schema_version)


def deterministic_semantic_id(
    *,
    event_id: str,
    target_type: str,
    target_id: str,
    schema_version: str,
    text_fingerprint: str,
) -> str:
    return _stable_id("mention_semantic", event_id, target_type, target_id, schema_version, text_fingerprint)


def deterministic_digest_id(
    *,
    target_type: str,
    target_id: str,
    window: str,
    scope: str,
    schema_version: str,
    source_fingerprint: str | None,
    label_fingerprint: str | None,
) -> str:
    return _stable_id(
        "discussion_digest",
        target_type,
        target_id,
        window,
        scope,
        schema_version,
        source_fingerprint or "",
        label_fingerprint or "",
    )


def deterministic_run_id(*, stage: str, input_hash: str, started_at_ms: int) -> str:
    return _stable_id("narrative_model_run", stage, input_hash, str(started_at_ms))


def _stable_id(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(str(part) for part in parts).encode("utf-8")).hexdigest()


def _stable_ids(values: Sequence[str]) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value).strip()})


def _digest_payload(digest: dict[str, Any], *, now_ms: int) -> dict[str, Any]:
    source_fingerprint = digest.get("source_fingerprint")
    if not source_fingerprint:
        source_fingerprint = build_source_fingerprint(
            digest.get("source_event_ids") or [],
            digest.get("source_max_received_at_ms"),
        )
    label_fingerprint = digest.get("label_fingerprint")
    if not label_fingerprint:
        label_fingerprint = build_label_fingerprint(digest.get("semantic_rows") or [])
    digest_id = deterministic_digest_id(
        target_type=_required(digest, "target_type"),
        target_id=_required(digest, "target_id"),
        window=_required(digest, "window"),
        scope=_required(digest, "scope"),
        schema_version=str(digest.get("schema_version") or NARRATIVE_SCHEMA_VERSION),
        source_fingerprint=source_fingerprint,
        label_fingerprint=label_fingerprint,
    )
    return {
        "digest_id": digest_id,
        "target_type": _required(digest, "target_type"),
        "target_id": _required(digest, "target_id"),
        "window": _required(digest, "window"),
        "scope": _required(digest, "scope"),
        "schema_version": str(digest.get("schema_version") or NARRATIVE_SCHEMA_VERSION),
        "model_version": str(digest.get("model_version") or "unknown"),
        "status": str(digest.get("status") or "pending"),
        "source_fingerprint": source_fingerprint,
        "label_fingerprint": label_fingerprint,
        "headline_zh": digest.get("headline_zh"),
        "dominant_narratives_json": _json(digest.get("dominant_narratives") or []),
        "bull_view_json": _json(digest.get("bull_view") or {}),
        "bear_view_json": _json(digest.get("bear_view") or {}),
        "stance_mix_json": _json(digest.get("stance_mix") or {}),
        "attention_valence_mix_json": _json(digest.get("attention_valence_mix") or {}),
        "propagation_read_json": _json(digest.get("propagation_read") or {}),
        "reflexivity_read_json": _json(digest.get("reflexivity_read") or {}),
        "watch_triggers_json": _json(digest.get("watch_triggers") or []),
        "invalidation_conditions_json": _json(digest.get("invalidation_conditions") or []),
        "data_gaps_json": _json(digest.get("data_gaps") or []),
        "semantic_coverage": float(digest.get("semantic_coverage") or 0.0),
        "source_event_count": int(digest.get("source_event_count") or 0),
        "labeled_event_count": int(digest.get("labeled_event_count") or 0),
        "independent_author_count": int(digest.get("independent_author_count") or 0),
        "evidence_refs_json": _json(digest.get("evidence_refs") or []),
        "model_run_id": digest.get("model_run_id"),
        "computed_at_ms": int(digest.get("computed_at_ms") or now_ms),
        "expires_at_ms": digest.get("expires_at_ms"),
        "superseded_at_ms": digest.get("superseded_at_ms"),
    }


def _allowed_refs_for_semantics(semantics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for row in semantics:
        if row.get("event_id"):
            refs.append({"ref_id": f"event:{row['event_id']}", "kind": "event", "source_table": "events"})
        if row.get("semantic_id"):
            refs.append(
                {
                    "ref_id": f"semantic:{row['semantic_id']}",
                    "kind": "semantic",
                    "source_table": "token_mention_semantics",
                }
            )
    return refs


def _author_count(rows: Sequence[dict[str, Any]]) -> int:
    return len({str(row.get("author_handle") or "").strip() for row in rows if str(row.get("author_handle") or "")})


def _json(value: Any) -> Jsonb:
    return Jsonb(value, dumps=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True, default=str))


def _row(row: Any) -> dict[str, Any]:
    return dict(row)


def _required(row: dict[str, Any], key: str) -> str:
    value = _clean(row.get(key))
    if not value:
        raise ValueError(f"missing required narrative repository value: {key}")
    return value


def _clean(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _commit_if_available(conn: Any) -> None:
    commit = getattr(conn, "commit", None)
    if commit is not None:
        commit()
