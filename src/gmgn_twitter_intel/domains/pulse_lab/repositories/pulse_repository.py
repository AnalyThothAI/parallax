from __future__ import annotations

import base64
import binascii
import hashlib
import json
import time
from typing import Any

from psycopg.types.json import Jsonb

DISPLAY_PULSE_STATUSES = ("trade_candidate", "token_watch", "theme_watch", "risk_rejected_high_info")
SUMMARY_PULSE_STATUSES = (*DISPLAY_PULSE_STATUSES, "blocked_low_information")
DISPLAY_PULSE_STATUS_SQL = "('trade_candidate', 'token_watch', 'theme_watch', 'risk_rejected_high_info')"


class PulseRepository:
    def __init__(self, conn: Any, *, running_timeout_ms: int = 300_000):
        self.conn = conn
        self.running_timeout_ms = int(running_timeout_ms)

    def enqueue_job(
        self,
        *,
        candidate_id: str,
        candidate_type: str,
        subject_key: str,
        window: str,
        scope: str,
        trigger_signature: str,
        timeline_signature: str,
        priority: int,
        job_id: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        context_json: dict[str, Any] | None = None,
        status: str = "pending",
        attempt_count: int = 0,
        max_attempts: int = 3,
        next_run_at_ms: int | None = None,
        cooldown_until_ms: int = 0,
        last_error: str | None = None,
        now_ms: int | None = None,
        commit: bool = True,
    ) -> dict[str, Any]:
        now = int(now_ms if now_ms is not None else _now_ms())
        run_at = int(next_run_at_ms if next_run_at_ms is not None else now)
        resolved_job_id = job_id or _id("pulse-job", candidate_id, trigger_signature, timeline_signature)
        row = self.conn.execute(
            """
            INSERT INTO pulse_agent_jobs(
              job_id, candidate_id, candidate_type, subject_key, target_type, target_id,
              "window", scope, trigger_signature, timeline_signature, context_json, priority, status,
              attempt_count, max_attempts, next_run_at_ms, cooldown_until_ms, last_error,
              created_at_ms, updated_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(candidate_id) DO UPDATE SET
              candidate_type = excluded.candidate_type,
              subject_key = excluded.subject_key,
              target_type = excluded.target_type,
              target_id = excluded.target_id,
              "window" = excluded."window",
              scope = excluded.scope,
              trigger_signature = CASE
                WHEN pulse_agent_jobs.status IN ('pending', 'running', 'failed')
                 AND pulse_agent_jobs.attempt_count < pulse_agent_jobs.max_attempts
                THEN pulse_agent_jobs.trigger_signature
                ELSE excluded.trigger_signature
              END,
              timeline_signature = CASE
                WHEN pulse_agent_jobs.status IN ('pending', 'running', 'failed')
                 AND pulse_agent_jobs.attempt_count < pulse_agent_jobs.max_attempts
                THEN pulse_agent_jobs.timeline_signature
                ELSE excluded.timeline_signature
              END,
              context_json = CASE
                WHEN pulse_agent_jobs.status IN ('pending', 'running', 'failed')
                 AND pulse_agent_jobs.attempt_count < pulse_agent_jobs.max_attempts
                THEN pulse_agent_jobs.context_json
                ELSE excluded.context_json
              END,
              priority = GREATEST(pulse_agent_jobs.priority, excluded.priority),
              status = CASE
                WHEN pulse_agent_jobs.status IN ('pending', 'running', 'failed')
                 AND pulse_agent_jobs.attempt_count < pulse_agent_jobs.max_attempts
                THEN pulse_agent_jobs.status
                ELSE excluded.status
              END,
              attempt_count = CASE
                WHEN pulse_agent_jobs.status IN ('pending', 'running', 'failed')
                 AND pulse_agent_jobs.attempt_count < pulse_agent_jobs.max_attempts
                THEN pulse_agent_jobs.attempt_count
                ELSE excluded.attempt_count
              END,
              max_attempts = excluded.max_attempts,
              next_run_at_ms = CASE
                WHEN pulse_agent_jobs.status IN ('pending', 'running', 'failed')
                 AND pulse_agent_jobs.attempt_count < pulse_agent_jobs.max_attempts
                THEN pulse_agent_jobs.next_run_at_ms
                ELSE excluded.next_run_at_ms
              END,
              cooldown_until_ms = excluded.cooldown_until_ms,
              last_error = CASE
                WHEN pulse_agent_jobs.status IN ('pending', 'running', 'failed')
                 AND pulse_agent_jobs.attempt_count < pulse_agent_jobs.max_attempts
                THEN pulse_agent_jobs.last_error
                ELSE excluded.last_error
              END,
              updated_at_ms = excluded.updated_at_ms
            RETURNING *
            """,
            (
                resolved_job_id,
                candidate_id,
                candidate_type,
                _normalize_subject(subject_key),
                target_type,
                target_id,
                window,
                scope,
                trigger_signature,
                timeline_signature,
                _json(context_json or {}),
                int(priority),
                status,
                int(attempt_count),
                max(1, int(max_attempts)),
                run_at,
                int(cooldown_until_ms),
                last_error,
                now,
                now,
            ),
        ).fetchone()
        if commit:
            self.conn.commit()
        return _row(row)

    def claim_due_job(self, now_ms: int | None = None) -> dict[str, Any] | None:
        now = int(now_ms if now_ms is not None else _now_ms())
        stale_before = now - self.running_timeout_ms
        self.conn.execute(
            """
            UPDATE pulse_agent_jobs
            SET status = 'dead',
                last_error = 'stale_running_timeout',
                updated_at_ms = %s
            WHERE status = 'running'
              AND updated_at_ms < %s
              AND attempt_count >= max_attempts
            """,
            (now, stale_before),
        )
        row = self.conn.execute(
            """
            WITH picked AS (
              SELECT job_id
              FROM pulse_agent_jobs
              WHERE (
                  status IN ('pending', 'failed')
                  AND attempt_count < max_attempts
                  AND next_run_at_ms <= %s
                  AND cooldown_until_ms <= %s
                )
                OR (
                  status = 'running'
                  AND updated_at_ms < %s
                  AND attempt_count < max_attempts
                )
              ORDER BY priority DESC, next_run_at_ms ASC, created_at_ms ASC, job_id ASC
              LIMIT 1
              FOR UPDATE SKIP LOCKED
            )
            UPDATE pulse_agent_jobs AS job
            SET status = 'running',
                attempt_count = job.attempt_count + 1,
                last_error = NULL,
                updated_at_ms = %s
            FROM picked
            WHERE job.job_id = picked.job_id
              AND (
                (
                  job.status IN ('pending', 'failed')
                  AND job.attempt_count < job.max_attempts
                  AND job.next_run_at_ms <= %s
                  AND job.cooldown_until_ms <= %s
                )
                OR (
                  job.status = 'running'
                  AND job.updated_at_ms < %s
                  AND job.attempt_count < job.max_attempts
                )
              )
            RETURNING job.*
            """,
            (now, now, stale_before, now, now, now, stale_before),
        ).fetchone()
        return _optional_row(row)

    def mark_job_succeeded(
        self,
        job_id: str,
        now_ms: int | None = None,
        commit: bool = True,
    ) -> dict[str, Any] | None:
        now = int(now_ms if now_ms is not None else _now_ms())
        row = self.conn.execute(
            """
            UPDATE pulse_agent_jobs
            SET status = 'done',
                last_error = NULL,
                updated_at_ms = %s
            WHERE job_id = %s
            RETURNING *
            """,
            (now, job_id),
        ).fetchone()
        if commit:
            self.conn.commit()
        return _optional_row(row)

    def mark_job_failed(
        self,
        job: dict[str, Any],
        error: str,
        now_ms: int | None = None,
        commit: bool = True,
    ) -> dict[str, Any] | None:
        if job is None:
            return None
        now = int(now_ms if now_ms is not None else _now_ms())
        attempts = int(job.get("attempt_count") or 0)
        max_attempts = int(job.get("max_attempts") or 3)
        status = "dead" if attempts >= max_attempts else "failed"
        delay_ms = 0 if status == "dead" else min(300_000, 5_000 * max(1, attempts))
        row = self.conn.execute(
            """
            UPDATE pulse_agent_jobs
            SET status = %s,
                next_run_at_ms = %s,
                last_error = %s,
                updated_at_ms = %s
            WHERE job_id = %s
            RETURNING *
            """,
            (status, now + delay_ms, str(error)[:1000], now, job["job_id"]),
        ).fetchone()
        if commit:
            self.conn.commit()
        return _optional_row(row)

    def job_for_candidate(self, candidate_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT *
            FROM pulse_agent_jobs
            WHERE candidate_id = %s
            ORDER BY updated_at_ms DESC, created_at_ms DESC, job_id DESC
            LIMIT 1
            """,
            (candidate_id,),
        ).fetchone()
        return _optional_row(row)

    def insert_agent_run(
        self,
        *,
        run_id: str,
        job_id: str,
        candidate_id: str,
        provider: str,
        model: str,
        workflow_name: str,
        agent_name: str,
        artifact_version_hash: str,
        prompt_version: str,
        schema_version: str,
        input_hash: str,
        request_json: dict[str, Any] | None = None,
        backend: str = "openai_agents_sdk",
        sdk_trace_id: str | None = None,
        output_hash: str | None = None,
        trace_metadata_json: dict[str, Any] | None = None,
        usage_json: dict[str, Any] | None = None,
        latency_ms: int = 0,
        status: str = "running",
        response_json: dict[str, Any] | None = None,
        error: str | None = None,
        started_at_ms: int | None = None,
        finished_at_ms: int | None = None,
        commit: bool = True,
    ) -> dict[str, Any]:
        started = int(started_at_ms if started_at_ms is not None else _now_ms())
        finished = int(finished_at_ms if finished_at_ms is not None else started)
        row = self.conn.execute(
            """
            INSERT INTO pulse_agent_runs(
              run_id, job_id, candidate_id, provider, model, backend, sdk_trace_id,
              workflow_name, agent_name, artifact_version_hash, prompt_version,
              schema_version, input_hash, output_hash, trace_metadata_json,
              usage_json, latency_ms, status, request_json, response_json, error,
              started_at_ms, finished_at_ms
            )
            VALUES (
              %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
              %s, %s, %s, %s, %s, %s, %s
            )
            RETURNING *
            """,
            (
                run_id,
                job_id,
                candidate_id,
                provider,
                model,
                backend,
                sdk_trace_id,
                workflow_name,
                agent_name,
                artifact_version_hash,
                prompt_version,
                schema_version,
                input_hash,
                output_hash,
                _json(trace_metadata_json or {}),
                _json(usage_json or {}),
                max(0, int(latency_ms)),
                status,
                _json(request_json or {}),
                _json(response_json) if response_json is not None else None,
                error,
                started,
                finished,
            ),
        ).fetchone()
        if commit:
            self.conn.commit()
        return _row(row)

    def finish_agent_run(
        self,
        run_id: str,
        status: str,
        response_json: dict[str, Any] | None = None,
        error: str | None = None,
        output_hash: str | None = None,
        usage_json: dict[str, Any] | None = None,
        finished_at_ms: int | None = None,
        commit: bool = True,
    ) -> dict[str, Any] | None:
        existing = self.conn.execute(
            "SELECT started_at_ms, usage_json FROM pulse_agent_runs WHERE run_id = %s",
            (run_id,),
        ).fetchone()
        if existing is None:
            return None
        now = int(finished_at_ms if finished_at_ms is not None else _now_ms())
        latency_ms = max(0, now - int(existing["started_at_ms"]))
        next_usage = usage_json if usage_json is not None else _decode_json_value(existing["usage_json"])
        row = self.conn.execute(
            """
            UPDATE pulse_agent_runs
            SET status = %s,
                response_json = %s,
                error = %s,
                output_hash = COALESCE(%s, output_hash),
                usage_json = %s,
                latency_ms = %s,
                finished_at_ms = %s
            WHERE run_id = %s
            RETURNING *
            """,
            (
                status,
                _json(response_json) if response_json is not None else None,
                error,
                output_hash,
                _json(next_usage or {}),
                latency_ms,
                now,
                run_id,
            ),
        ).fetchone()
        if commit:
            self.conn.commit()
        return _optional_row(row)

    def upsert_candidate(
        self,
        *,
        candidate_id: str,
        candidate_type: str,
        subject_key: str,
        window: str,
        scope: str,
        pulse_status: str,
        verdict: str,
        social_phase: str,
        narrative_type: str,
        candidate_score: float,
        score_band: str,
        trigger_signature: str,
        timeline_signature: str,
        pulse_version: str,
        gate_version: str,
        prompt_version: str,
        schema_version: str,
        factor_snapshot_json: dict[str, Any],
        gate_json: dict[str, Any],
        thesis_json: dict[str, Any] | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        symbol: str | None = None,
        agent_recommendation_json: dict[str, Any] | None = None,
        gate_reasons_json: list[Any] | None = None,
        risk_reasons_json: list[Any] | None = None,
        evidence_event_ids_json: list[Any] | None = None,
        source_event_ids_json: list[Any] | None = None,
        agent_run_id: str | None = None,
        created_at_ms: int | None = None,
        updated_at_ms: int | None = None,
        commit: bool = True,
    ) -> dict[str, Any]:
        now = int(updated_at_ms if updated_at_ms is not None else _now_ms())
        created = int(created_at_ms if created_at_ms is not None else now)
        row = self.conn.execute(
            """
            INSERT INTO pulse_candidates(
              candidate_id, candidate_type, subject_key, target_type, target_id, symbol,
              "window", scope, pulse_status, verdict, social_phase, narrative_type,
              candidate_score, score_band, trigger_signature, timeline_signature,
              thesis_json, factor_snapshot_json, agent_recommendation_json, gate_json,
              gate_reasons_json, risk_reasons_json, evidence_event_ids_json, source_event_ids_json,
              agent_run_id, pulse_version, gate_version, prompt_version, schema_version,
              created_at_ms, updated_at_ms
            )
            VALUES (
              %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
              %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT(candidate_id) DO UPDATE SET
              candidate_type = excluded.candidate_type,
              subject_key = excluded.subject_key,
              target_type = excluded.target_type,
              target_id = excluded.target_id,
              symbol = excluded.symbol,
              "window" = excluded."window",
              scope = excluded.scope,
              pulse_status = excluded.pulse_status,
              verdict = excluded.verdict,
              social_phase = excluded.social_phase,
              narrative_type = excluded.narrative_type,
              candidate_score = excluded.candidate_score,
              score_band = excluded.score_band,
              trigger_signature = excluded.trigger_signature,
              timeline_signature = excluded.timeline_signature,
              thesis_json = excluded.thesis_json,
              factor_snapshot_json = excluded.factor_snapshot_json,
              agent_recommendation_json = excluded.agent_recommendation_json,
              gate_json = excluded.gate_json,
              gate_reasons_json = excluded.gate_reasons_json,
              risk_reasons_json = excluded.risk_reasons_json,
              evidence_event_ids_json = excluded.evidence_event_ids_json,
              source_event_ids_json = excluded.source_event_ids_json,
              agent_run_id = excluded.agent_run_id,
              pulse_version = excluded.pulse_version,
              gate_version = excluded.gate_version,
              prompt_version = excluded.prompt_version,
              schema_version = excluded.schema_version,
              updated_at_ms = excluded.updated_at_ms
            RETURNING *
            """,
            (
                candidate_id,
                candidate_type,
                _normalize_subject(subject_key),
                target_type,
                target_id,
                _normalize_symbol(symbol),
                window,
                scope,
                pulse_status,
                verdict,
                social_phase,
                narrative_type,
                float(candidate_score),
                score_band,
                trigger_signature,
                timeline_signature,
                _json(thesis_json or {}),
                _json(factor_snapshot_json),
                _json(agent_recommendation_json or {}),
                _json(gate_json),
                _json(gate_reasons_json or []),
                _json(risk_reasons_json or []),
                _json(evidence_event_ids_json or []),
                _json(source_event_ids_json or []),
                agent_run_id,
                pulse_version,
                gate_version,
                prompt_version,
                schema_version,
                created,
                now,
            ),
        ).fetchone()
        if commit:
            self.conn.commit()
        return _row(row)

    def list_candidates(
        self,
        window: str,
        scope: str,
        status: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
        q: str | None = None,
        handle: str | None = None,
        displayable_only: bool = False,
    ) -> dict[str, Any]:
        bounded_limit = max(0, min(int(limit), 200))
        clauses = ['candidate."window" = %s', "candidate.scope = %s"]
        params: list[Any] = [window, scope]
        if status:
            clauses.append("candidate.pulse_status = %s")
            params.append(status)
        if displayable_only:
            clauses.append(f"candidate.pulse_status IN {DISPLAY_PULSE_STATUS_SQL}")
            clauses.append("candidate.verdict IS DISTINCT FROM 'blocked_low_information'")
        if handle:
            handle_clause, handle_params = _candidate_handle_filter_clause("candidate", handle)
            if handle_clause:
                clauses.append(handle_clause)
                params.extend(handle_params)
        if q:
            pattern = f"%{q.strip()}%"
            clauses.append(
                "(candidate.symbol ILIKE %s OR candidate.subject_key ILIKE %s OR candidate.target_id ILIKE %s)"
            )
            params.extend([pattern, pattern, pattern])
        cursor_payload = _decode_cursor(cursor)
        if cursor_payload is not None:
            clauses.append("(candidate.updated_at_ms, candidate.candidate_id) < (%s, %s)")
            params.extend([int(cursor_payload["updated_at_ms"]), str(cursor_payload["candidate_id"])])

        rows = self.conn.execute(
            f"""
            SELECT candidate.*
            FROM pulse_candidates AS candidate
            WHERE {" AND ".join(clauses)}
            ORDER BY candidate.updated_at_ms DESC, candidate.candidate_id DESC
            LIMIT %s
            """,
            (*params, bounded_limit + 1),
        ).fetchall()
        decoded = [_row(row) for row in rows]
        items = decoded[:bounded_limit]
        next_cursor = None
        if len(decoded) > bounded_limit and items:
            last = items[-1]
            next_cursor = _encode_cursor(last["updated_at_ms"], last["candidate_id"])
        return {"items": items, "next_cursor": next_cursor}

    def pulse_summary(
        self,
        window: str,
        scope: str,
        q: str | None = None,
        handle: str | None = None,
    ) -> dict[str, Any]:
        clauses = ['candidate."window" = %s', "candidate.scope = %s"]
        params: list[Any] = [window, scope]
        if handle:
            handle_clause, handle_params = _candidate_handle_filter_clause("candidate", handle)
            if handle_clause:
                clauses.append(handle_clause)
                params.extend(handle_params)
        if q:
            pattern = f"%{q.strip()}%"
            clauses.append(
                "(candidate.symbol ILIKE %s OR candidate.subject_key ILIKE %s OR candidate.target_id ILIKE %s)"
            )
            params.extend([pattern, pattern, pattern])
        candidate_row = self.conn.execute(
            f"""
            SELECT
              COUNT(*) AS candidate_count,
              COUNT(*) FILTER (WHERE pulse_status = 'trade_candidate') AS trade_candidate_count,
              COUNT(*) FILTER (WHERE pulse_status = 'token_watch') AS token_watch_count,
              COUNT(*) FILTER (WHERE pulse_status = 'theme_watch') AS theme_watch_count,
              COUNT(*) FILTER (WHERE pulse_status = 'risk_rejected_high_info') AS risk_rejected_high_info_count,
              COUNT(*) FILTER (WHERE pulse_status = 'blocked_low_information') AS blocked_low_information_status_count,
              COUNT(*) FILTER (
                WHERE pulse_status = 'blocked_low_information'
                   OR verdict = 'blocked_low_information'
                   OR gate_reasons_json @> '["low_information"]'::jsonb
              ) AS blocked_low_information_count,
              COUNT(*) FILTER (
                WHERE pulse_status IN {DISPLAY_PULSE_STATUS_SQL}
                  AND verdict IS DISTINCT FROM 'blocked_low_information'
              ) AS displayable_count,
              COUNT(*) FILTER (
                WHERE pulse_status IN {DISPLAY_PULSE_STATUS_SQL}
                  AND verdict IS DISTINCT FROM 'blocked_low_information'
                  AND factor_snapshot_json #>> '{{families,market_quality,facts,market_status}}' = 'fresh'
              ) AS market_fresh_count
            FROM pulse_candidates
            AS candidate
            WHERE {" AND ".join(clauses)}
            """,
            tuple(params),
        ).fetchone()
        job_clauses = ['job."window" = %s', "job.scope = %s", "job.status = 'dead'"]
        job_params: list[Any] = [window, scope]
        if handle:
            normalized_handle = _normalize_subject(handle)
            candidate_handle_clause, candidate_handle_params = _candidate_handle_filter_clause("candidate", handle)
            if normalized_handle and candidate_handle_clause:
                job_clauses.append(f"(lower(job.subject_key) = %s OR {candidate_handle_clause})")
                job_params.extend([normalized_handle, *candidate_handle_params])
        if q:
            pattern = f"%{q.strip()}%"
            job_clauses.append(
                "(candidate.symbol ILIKE %s OR job.subject_key ILIKE %s OR job.target_id ILIKE %s)"
            )
            job_params.extend([pattern, pattern, pattern])
        job_row = self.conn.execute(
            f"""
            SELECT COUNT(*) AS dead_job_count
            FROM pulse_agent_jobs AS job
            LEFT JOIN pulse_candidates AS candidate
              ON candidate.candidate_id = job.candidate_id
            WHERE {" AND ".join(job_clauses)}
            """,
            tuple(job_params),
        ).fetchone()
        row = dict(candidate_row) if candidate_row else {}
        summary = {
            "trade_candidate": int(row.get("trade_candidate_count") or 0),
            "token_watch": int(row.get("token_watch_count") or 0),
            "theme_watch": int(row.get("theme_watch_count") or 0),
            "risk_rejected_high_info": int(row.get("risk_rejected_high_info_count") or 0),
            "blocked_low_information": int(row.get("blocked_low_information_status_count") or 0),
        }
        displayable_count = int(row.get("displayable_count") or 0)
        market_fresh_count = int(row.get("market_fresh_count") or 0)
        return {
            "window": window,
            "scope": scope,
            "summary": summary,
            "candidate_count": int(row.get("candidate_count") or 0),
            "blocked_low_information_count": int(row.get("blocked_low_information_count") or 0),
            "dead_job_count": int(job_row["dead_job_count"] if job_row else 0),
            "market_ready_rate": 0.0 if displayable_count == 0 else market_fresh_count / displayable_count,
        }

    def candidate_by_id(self, candidate_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT *
            FROM pulse_candidates
            WHERE candidate_id = %s
            """,
            (candidate_id,),
        ).fetchone()
        return _optional_row(row)

    def get_health(self, window: str, scope: str) -> dict[str, Any]:
        candidate_row = self.conn.execute(
            """
            SELECT
              COUNT(*) AS candidate_count,
              COUNT(*) FILTER (
                WHERE pulse_status = 'blocked_low_information'
                   OR verdict = 'blocked_low_information'
                   OR gate_reasons_json @> '["low_information"]'::jsonb
              ) AS blocked_low_information_count
            FROM pulse_candidates
            WHERE "window" = %s AND scope = %s
            """,
            (window, scope),
        ).fetchone()
        job_rows = self.conn.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM pulse_agent_jobs
            WHERE "window" = %s AND scope = %s
            GROUP BY status
            """,
            (window, scope),
        ).fetchall()
        job_counts = {str(row["status"]): int(row["count"]) for row in job_rows}
        return {
            "window": window,
            "scope": scope,
            "candidate_count": int(candidate_row["candidate_count"] if candidate_row else 0),
            "blocked_low_information_count": int(
                candidate_row["blocked_low_information_count"] if candidate_row else 0
            ),
            "dead_job_count": int(job_counts.get("dead", 0)),
            "job_counts": job_counts,
        }

    def upsert_playbook_snapshot(
        self,
        *,
        playbook_id: str,
        candidate_id: str,
        horizon: str,
        decision_time_ms: int,
        playbook_status: str,
        side: str,
        setup: dict[str, Any],
        confirmation: dict[str, Any],
        invalidation: dict[str, Any],
        risk: dict[str, Any],
        playbook_version: str,
        target_type: str | None = None,
        target_id: str | None = None,
        entry_market: dict[str, Any] | None = None,
        outcome_status: str = "pending",
        created_at_ms: int | None = None,
        commit: bool = True,
    ) -> dict[str, Any]:
        created = int(created_at_ms if created_at_ms is not None else _now_ms())
        row = self.conn.execute(
            """
            INSERT INTO pulse_playbook_snapshots(
              playbook_id, candidate_id, target_type, target_id, horizon, decision_time_ms,
              playbook_status, side, setup_json, confirmation_json, invalidation_json,
              risk_json, entry_market_json, playbook_version, outcome_status, created_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(candidate_id, horizon, playbook_version) DO UPDATE SET
              target_type = excluded.target_type,
              target_id = excluded.target_id,
              decision_time_ms = excluded.decision_time_ms,
              playbook_status = excluded.playbook_status,
              side = excluded.side,
              setup_json = excluded.setup_json,
              confirmation_json = excluded.confirmation_json,
              invalidation_json = excluded.invalidation_json,
              risk_json = excluded.risk_json,
              entry_market_json = excluded.entry_market_json,
              outcome_status = excluded.outcome_status,
              created_at_ms = excluded.created_at_ms
            RETURNING *
            """,
            (
                playbook_id,
                candidate_id,
                target_type,
                target_id,
                horizon,
                int(decision_time_ms),
                playbook_status,
                side,
                _json(setup),
                _json(confirmation),
                _json(invalidation),
                _json(risk),
                _json(entry_market or {}),
                playbook_version,
                outcome_status,
                created,
            ),
        ).fetchone()
        if commit:
            self.conn.commit()
        return _row(row)

    def upsert_playbook_outcome(
        self,
        *,
        playbook_id: str,
        settled_at_ms: int,
        actual_return: float | None = None,
        benchmark_return: float | None = None,
        abnormal_return: float | None = None,
        max_favorable_excursion: float | None = None,
        max_adverse_excursion: float | None = None,
        confirmation_hit: bool = False,
        invalidation_hit: bool = False,
        outcome: dict[str, Any] | None = None,
        outcome_json: dict[str, Any] | None = None,
        created_at_ms: int | None = None,
        commit: bool = True,
    ) -> dict[str, Any]:
        created = int(created_at_ms if created_at_ms is not None else _now_ms())
        resolved_outcome = outcome if outcome is not None else outcome_json
        row = self.conn.execute(
            """
            INSERT INTO pulse_playbook_outcomes(
              playbook_id, settled_at_ms, actual_return, benchmark_return, abnormal_return,
              max_favorable_excursion, max_adverse_excursion, confirmation_hit,
              invalidation_hit, outcome_json, created_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(playbook_id) DO UPDATE SET
              settled_at_ms = excluded.settled_at_ms,
              actual_return = excluded.actual_return,
              benchmark_return = excluded.benchmark_return,
              abnormal_return = excluded.abnormal_return,
              max_favorable_excursion = excluded.max_favorable_excursion,
              max_adverse_excursion = excluded.max_adverse_excursion,
              confirmation_hit = excluded.confirmation_hit,
              invalidation_hit = excluded.invalidation_hit,
              outcome_json = excluded.outcome_json,
              created_at_ms = excluded.created_at_ms
            RETURNING *
            """,
            (
                playbook_id,
                int(settled_at_ms),
                actual_return,
                benchmark_return,
                abnormal_return,
                max_favorable_excursion,
                max_adverse_excursion,
                bool(confirmation_hit),
                bool(invalidation_hit),
                _json(resolved_outcome or {}),
                created,
            ),
        ).fetchone()
        if commit:
            self.conn.commit()
        return _row(row)


def _row(row: Any) -> dict[str, Any]:
    return {str(key): _decode_json_value(value) for key, value in dict(row).items()}


def _optional_row(row: Any) -> dict[str, Any] | None:
    return _row(row) if row else None


def _json(value: Any) -> Jsonb:
    return Jsonb(_json_ready(value), dumps=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True))


def _decode_json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _decode_json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_decode_json_value(item) for item in value]
    return value


def _json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return value


def _encode_cursor(updated_at_ms: int, candidate_id: str) -> str:
    payload = json.dumps(
        {"updated_at_ms": int(updated_at_ms), "candidate_id": str(candidate_id)},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii")


def _decode_cursor(cursor: str | None) -> dict[str, Any] | None:
    if not cursor:
        return None
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
    except (binascii.Error, UnicodeEncodeError, UnicodeDecodeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or "updated_at_ms" not in payload or "candidate_id" not in payload:
        return None
    candidate_id = payload["candidate_id"]
    if not isinstance(candidate_id, str):
        return None
    try:
        updated_at_ms = int(payload["updated_at_ms"])
    except (TypeError, ValueError):
        return None
    return {"updated_at_ms": updated_at_ms, "candidate_id": candidate_id}


def _id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _normalize_subject(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lstrip("@").lower()
    return normalized or None


def _candidate_handle_filter_clause(candidate_alias: str, handle: str | None) -> tuple[str, list[Any]]:
    normalized = _normalize_subject(handle)
    if not normalized:
        return "", []
    event_ids_sql = f"""
        (
          CASE
            WHEN jsonb_typeof({candidate_alias}.source_event_ids_json) = 'array'
            THEN {candidate_alias}.source_event_ids_json
            ELSE '[]'::jsonb
          END
          ||
          CASE
            WHEN jsonb_typeof({candidate_alias}.evidence_event_ids_json) = 'array'
            THEN {candidate_alias}.evidence_event_ids_json
            ELSE '[]'::jsonb
          END
        )
    """
    return (
        f"""
        (
          lower({candidate_alias}.subject_key) = %s
          OR EXISTS (
            SELECT 1
            FROM jsonb_array_elements_text({event_ids_sql}) AS pulse_event(event_id)
            LEFT JOIN events ON events.event_id = pulse_event.event_id
            LEFT JOIN social_event_extractions
              ON social_event_extractions.event_id = pulse_event.event_id
            WHERE lower(coalesce(social_event_extractions.author_handle, events.author_handle, '')) = %s
          )
        )
        """,
        [normalized, normalized],
    )


def _normalize_symbol(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lstrip("$").upper()
    return normalized or None


def _now_ms() -> int:
    return int(time.time() * 1000)
