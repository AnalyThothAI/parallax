from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any

from psycopg.types.json import Jsonb

from gmgn_twitter_intel.platform.db.postgres_client import transaction

from ..types.social_event_extraction import SocialEventExtraction

RUNNING_TIMEOUT_MS = 300_000
WATCHED_SOCIAL_EVENT_JOB_TYPE = "watched_social_event_extraction"

# Text-gate constants (kept in sync with services.watched_event_gate)
_HIGH_SIGNAL_TERMS = {
    "accumulated",
    "acquired",
    "airdrop",
    "binance",
    "bought",
    "burn",
    "buyback",
    "cex",
    "court",
    "delist",
    "deploy",
    "drain",
    "etf",
    "exploit",
    "funding",
    "hack",
    "launch",
    "lawsuit",
    "listing",
    "mainnet",
    "partnership",
    "raise",
    "sec",
    "sold",
    "treasury",
    "unlock",
    "upgrade",
    "whale",
}
_TOPIC_TERMS = {
    "agent",
    "ai",
    "base",
    "bnb",
    "bitcoin",
    "builder",
    "ecosystem",
    "ethereum",
    "grok",
    "liquidity",
    "market",
    "pump",
    "ready",
    "rotation",
    "scaling",
    "solana",
    "throughput",
}
_SERVICE_REPLY_TERMS = (
    "airdrop list",
    "already claimed",
    "api is down",
    "api returned",
    "checked your claim",
    "claim status",
    "eligibility",
    "merkle proof",
    "not eligible",
    "proof endpoint",
    "skill installed",
)


def _should_enqueue_watched_social_event_text(text: str | None) -> bool:
    if not text:
        return False
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    if _is_low_information_service_reply(normalized):
        return False
    return (
        sum(1 for term in (_HIGH_SIGNAL_TERMS | _TOPIC_TERMS) if re.search(rf"\b{re.escape(term)}\b", normalized)) > 0
        and len(normalized) >= 24
    )


def _is_low_information_service_reply(normalized: str) -> bool:
    if not any(term in normalized for term in _SERVICE_REPLY_TERMS):
        return False
    has_wallet_or_contract = bool(re.search(r"\b0x[a-f0-9]{8,}\b", normalized))
    return has_wallet_or_contract or "wallet" in normalized or "claim" in normalized


class EnrichmentRepository:
    def __init__(self, conn: Any, *, running_timeout_ms: int = RUNNING_TIMEOUT_MS):
        self.conn = conn
        self.running_timeout_ms = running_timeout_ms

    def enqueue_watched_event(
        self,
        *,
        event_id: str,
        received_at_ms: int,
        priority: int = 100,
        commit: bool = True,
    ) -> str | None:
        job_id = _id("job", event_id, WATCHED_SOCIAL_EVENT_JOB_TYPE)
        now_ms = _now_ms()
        cursor = self.conn.execute(
            """
            INSERT INTO enrichment_jobs(
              job_id, event_id, job_type, priority, status, attempt_count, max_attempts,
              next_run_at_ms, last_error, created_at_ms, updated_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(event_id, job_type) DO NOTHING
            """,
            (
                job_id,
                event_id,
                WATCHED_SOCIAL_EVENT_JOB_TYPE,
                priority,
                "pending",
                0,
                3,
                int(received_at_ms),
                None,
                now_ms,
                now_ms,
            ),
        )
        if commit:
            self.conn.commit()
        if cursor.rowcount == 0:
            return self._job_id_for_event(event_id, WATCHED_SOCIAL_EVENT_JOB_TYPE)
        return job_id

    def claim_next_job(self, *, now_ms: int | None = None) -> dict[str, Any] | None:
        now = now_ms if now_ms is not None else _now_ms()
        stale_before = now - self.running_timeout_ms
        self.conn.execute(
            """
            UPDATE enrichment_jobs
            SET status = 'dead',
                last_error = 'legacy_job_type_retired',
                updated_at_ms = %s
            WHERE job_type <> %s
              AND status IN ('pending', 'failed', 'running')
            """,
            (now, WATCHED_SOCIAL_EVENT_JOB_TYPE),
        )
        self.conn.execute(
            """
            UPDATE enrichment_jobs
            SET status = 'dead',
                last_error = 'stale_running_timeout',
                updated_at_ms = %s
            WHERE status = 'running'
              AND job_type = %s
              AND updated_at_ms < %s
              AND attempt_count >= max_attempts
            """,
            (now, WATCHED_SOCIAL_EVENT_JOB_TYPE, stale_before),
        )
        row = self.conn.execute(
            """
            WITH picked AS (
              SELECT job_id, status AS picked_status
              FROM enrichment_jobs
              WHERE job_type = %s
                AND (
                  (
                    status IN ('pending', 'failed')
                    AND attempt_count < max_attempts
                    AND next_run_at_ms <= %s
                  )
                  OR (
                    status = 'running'
                    AND updated_at_ms < %s
                    AND attempt_count < max_attempts
                  )
                )
              ORDER BY priority DESC, next_run_at_ms ASC, created_at_ms ASC, job_id ASC
              LIMIT 1
              FOR UPDATE SKIP LOCKED
            )
            UPDATE enrichment_jobs AS job
            SET status = 'running',
                attempt_count = job.attempt_count + 1,
                updated_at_ms = %s,
                last_error = NULL
            FROM picked
            WHERE job.job_id = picked.job_id
              AND job.job_type = %s
              AND (
                (
                  job.status IN ('pending', 'failed')
                  AND job.attempt_count < job.max_attempts
                  AND job.next_run_at_ms <= %s
                )
                OR (
                  job.status = 'running'
                  AND job.updated_at_ms < %s
                  AND job.attempt_count < job.max_attempts
                )
              )
            RETURNING job.*
            """,
            (WATCHED_SOCIAL_EVENT_JOB_TYPE, now, stale_before, now, WATCHED_SOCIAL_EVENT_JOB_TYPE, now, stale_before),
        ).fetchone()
        return dict(row) if row else None

    def complete_social_event_job(
        self,
        *,
        job: dict[str, Any],
        run_id: str,
        result: SocialEventExtraction,
        provider: str,
        model: str,
        request: dict[str, Any],
        started_at_ms: int | None = None,
        finished_at_ms: int | None = None,
        commit: bool = True,
    ) -> dict[str, Any]:
        now_ms = finished_at_ms if finished_at_ms is not None else _now_ms()
        started = started_at_ms if started_at_ms is not None else now_ms
        audit = result.agent_run_audit

        def write() -> None:
            self.conn.execute(
                """
                INSERT INTO model_runs(
                  run_id, job_id, event_id, provider, model, backend, sdk_trace_id,
                  workflow_name, agent_name, artifact_version_hash, prompt_version,
                  schema_version, input_hash, output_hash, trace_metadata_json,
                  usage_json, latency_ms, status, request_json, response_json, error,
                  started_at_ms, finished_at_ms,
                  safety_net_used, safety_net_retries, parse_mode
                )
                VALUES (
                  %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                  %s, %s, %s, %s, %s, %s, %s,
                  %s, %s, %s
                )
                """,
                (
                    run_id,
                    job["job_id"],
                    job["event_id"],
                    provider,
                    model,
                    str(audit.get("backend") or "openai_agents_sdk"),
                    audit.get("sdk_trace_id"),
                    audit.get("workflow_name"),
                    audit.get("agent_name"),
                    audit.get("artifact_version_hash"),
                    audit.get("prompt_version"),
                    audit.get("schema_version"),
                    audit.get("input_hash"),
                    audit.get("output_hash"),
                    _json(audit.get("trace_metadata") or {}),
                    _json(audit.get("usage") or {}),
                    max(0, int(now_ms) - int(started)),
                    "done",
                    _json(request),
                    _json(result.raw_response),
                    None,
                    started,
                    now_ms,
                    bool(audit.get("safety_net_used", False)),
                    max(0, int(audit.get("safety_net_retries") or 0)),
                    str(audit.get("parse_mode") or "strict"),
                ),
            )
            self.conn.execute(
                """
                UPDATE enrichment_jobs
                SET status = 'done', updated_at_ms = %s, last_error = NULL
                WHERE job_id = %s
                """,
                (now_ms, job["job_id"]),
            )

        if commit:
            with transaction(self.conn):
                write()
        else:
            write()
        row = self.conn.execute("SELECT * FROM model_runs WHERE run_id = %s", (run_id,)).fetchone()
        return dict(row) if row else {"run_id": run_id}

    def record_model_run_failure(
        self,
        *,
        job: dict[str, Any],
        run_id: str,
        provider: str,
        model: str,
        request: dict[str, Any],
        error: str,
        audit: dict[str, Any] | None = None,
        started_at_ms: int | None = None,
        finished_at_ms: int | None = None,
    ) -> dict[str, Any]:
        now_ms = finished_at_ms if finished_at_ms is not None else _now_ms()
        started = started_at_ms if started_at_ms is not None else now_ms
        run_audit = audit or {}
        self.conn.execute(
            """
            INSERT INTO model_runs(
              run_id, job_id, event_id, provider, model, backend, sdk_trace_id,
              workflow_name, agent_name, artifact_version_hash, prompt_version,
              schema_version, input_hash, output_hash, trace_metadata_json,
              usage_json, latency_ms, status, request_json, response_json, error,
              started_at_ms, finished_at_ms,
              safety_net_used, safety_net_retries, parse_mode
            )
            VALUES (
              %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
              %s, %s, %s, %s, %s, %s, %s,
              %s, %s, %s
            )
            ON CONFLICT(run_id) DO NOTHING
            """,
            (
                run_id,
                job["job_id"],
                job["event_id"],
                provider,
                model,
                str(run_audit.get("backend") or "openai_agents_sdk"),
                run_audit.get("sdk_trace_id"),
                run_audit.get("workflow_name"),
                run_audit.get("agent_name"),
                run_audit.get("artifact_version_hash"),
                run_audit.get("prompt_version"),
                run_audit.get("schema_version"),
                run_audit.get("input_hash"),
                run_audit.get("output_hash"),
                _json(run_audit.get("trace_metadata") or {}),
                _json(run_audit.get("usage") or {}),
                max(0, int(now_ms) - int(started)),
                "model_error",
                _json(request),
                _json({}),
                error[:1000],
                started,
                now_ms,
                bool(run_audit.get("safety_net_used", False)),
                max(0, int(run_audit.get("safety_net_retries") or 0)),
                str(run_audit.get("parse_mode") or "strict"),
            ),
        )
        self.conn.commit()
        row = self.conn.execute("SELECT * FROM model_runs WHERE run_id = %s", (run_id,)).fetchone()
        return dict(row) if row else {"run_id": run_id}

    def fail_job(self, *, job: dict[str, Any], error: str) -> None:
        now_ms = _now_ms()
        attempts = int(job.get("attempt_count") or 0)
        max_attempts = int(job.get("max_attempts") or 3)
        status = "dead" if attempts >= max_attempts else "failed"
        delay_ms = min(300_000, 5_000 * max(1, attempts))
        self.conn.execute(
            """
            UPDATE enrichment_jobs
            SET status = %s, last_error = %s, next_run_at_ms = %s, updated_at_ms = %s
            WHERE job_id = %s
            """,
            (status, error[:1000], now_ms + delay_ms, now_ms, job["job_id"]),
        )
        self.conn.commit()

    def release_job_for_backpressure(
        self,
        job: dict[str, Any],
        *,
        reason: str,
        now_ms: int,
        delay_ms: int = 30_000,
    ) -> dict[str, Any] | None:
        attempt_count = int(job.get("attempt_count") or 0)
        row = self.conn.execute(
            """
            UPDATE enrichment_jobs
            SET status = 'pending',
                attempt_count = GREATEST(0, attempt_count - 1),
                next_run_at_ms = %s,
                last_error = %s,
                updated_at_ms = %s
            WHERE job_id = %s
              AND status = 'running'
              AND attempt_count = %s
            RETURNING *
            """,
            (
                int(now_ms) + max(0, int(delay_ms)),
                f"agent_backpressure:{reason}"[:1000],
                int(now_ms),
                str(job["job_id"]),
                attempt_count,
            ),
        ).fetchone()
        self.conn.commit()
        return dict(row) if row else None

    def list_jobs(self, *, limit: int, status: str | None = None) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("status = %s")
            params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.conn.execute(
            f"""
            SELECT * FROM enrichment_jobs
            {where}
            ORDER BY priority DESC, next_run_at_ms ASC, created_at_ms ASC
            LIMIT %s
            """,
            (*params, max(0, int(limit))),
        ).fetchall()
        return [dict(row) for row in rows]

    def job_counts(self) -> dict[str, int]:
        rows = self.conn.execute("SELECT status, COUNT(*) AS count FROM enrichment_jobs GROUP BY status").fetchall()
        counts = {str(row["status"]): int(row["count"]) for row in rows}
        for status in ("pending", "running", "failed", "dead", "done"):
            counts.setdefault(status, 0)
        return counts

    def job_success_rate(self) -> float | None:
        counts = self.job_counts()
        terminal = counts["done"] + counts["dead"]
        return None if terminal == 0 else counts["done"] / terminal

    def enqueue_missing_watched_events(self, *, limit: int) -> dict[str, Any]:
        rows = self.conn.execute(
            """
            SELECT
              e.event_id,
              e.received_at_ms,
              COALESCE(NULLIF(e.search_text, ''), NULLIF(e.text_clean, ''), NULLIF(e.text, '')) AS event_text
            FROM events e
            WHERE e.is_watched = true
              AND COALESCE(NULLIF(e.search_text, ''), NULLIF(e.text_clean, ''), NULLIF(e.text, '')) IS NOT NULL
              AND NOT EXISTS (
                SELECT 1
                FROM enrichment_jobs j
                WHERE j.event_id = e.event_id
                  AND j.job_type = %s
              )
              AND NOT EXISTS (
                SELECT 1
                FROM social_event_extractions se
                WHERE se.event_id = e.event_id
              )
            ORDER BY e.received_at_ms ASC
            LIMIT %s
            """,
            (WATCHED_SOCIAL_EVENT_JOB_TYPE, max(0, int(limit))),
        ).fetchall()
        enqueued = 0
        with transaction(self.conn):
            for row in rows:
                if not _should_enqueue_watched_social_event_text(str(row["event_text"] or "")):
                    continue
                job_id = self.enqueue_watched_event(
                    event_id=str(row["event_id"]),
                    received_at_ms=int(row["received_at_ms"]),
                    commit=False,
                )
                if job_id is not None:
                    enqueued += 1
        return {
            "watched_events_scanned": len(rows),
            "jobs_enqueued": enqueued,
            "counts": self.job_counts(),
        }

    def _job_id_for_event(self, event_id: str, job_type: str) -> str | None:
        row = self.conn.execute(
            "SELECT job_id FROM enrichment_jobs WHERE event_id = %s AND job_type = %s",
            (event_id, job_type),
        ).fetchone()
        return str(row["job_id"]) if row else None


def _json(value: Any) -> Jsonb:
    return Jsonb(value, dumps=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True))


def _id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _now_ms() -> int:
    return int(time.time() * 1000)
