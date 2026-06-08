from __future__ import annotations

from typing import Any

from parallax.domains.pulse_lab.repositories._pulse_repository_shared import (
    _decode_json_value,
    _json,
    _mapping,
    _now_ms,
    _optional_row,
    _row,
)


class PulseRunsRepository:
    def __init__(self, conn: Any, *, running_timeout_ms: int = 300_000):
        self.conn = conn
        self.running_timeout_ms = int(running_timeout_ms)

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
        runtime_version: str,
        runtime_hash: str,
        input_hash: str,
        outcome: str,
        request_json: dict[str, Any] | None = None,
        backend: str = "litellm_sdk",
        execution_trace_id: str | None = None,
        output_hash: str | None = None,
        trace_metadata_json: dict[str, Any] | None = None,
        usage_json: dict[str, Any] | None = None,
        latency_ms: int = 0,
        status: str = "running",
        decision_route: str = "research_only",
        decision_stage_count: int = 0,
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
              run_id, job_id, candidate_id, provider, model, backend, execution_trace_id,
              workflow_name, agent_name, artifact_version_hash, prompt_version,
              schema_version, runtime_version, runtime_hash, input_hash, output_hash, trace_metadata_json,
              usage_json, latency_ms, status, outcome, decision_route, decision_stage_count,
              request_json, response_json, error, started_at_ms, finished_at_ms
            )
            VALUES (
              %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
              %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
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
                execution_trace_id,
                workflow_name,
                agent_name,
                artifact_version_hash,
                prompt_version,
                schema_version,
                runtime_version,
                runtime_hash,
                input_hash,
                output_hash,
                _json(trace_metadata_json or {}),
                _json(usage_json or {}),
                max(0, int(latency_ms)),
                status,
                outcome,
                decision_route,
                max(0, int(decision_stage_count)),
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
        *,
        outcome: str,
        decision_route: str | None = None,
        decision_stage_count: int | None = None,
        evidence_packet_id: str | None = None,
        evidence_packet_hash: str | None = None,
        evidence_status: str | None = None,
        display_status: str | None = None,
        trace_metadata_json_patch: dict[str, Any] | None = None,
        finished_at_ms: int | None = None,
        commit: bool = True,
    ) -> dict[str, Any] | None:
        existing = self.conn.execute(
            "SELECT started_at_ms, usage_json, trace_metadata_json FROM pulse_agent_runs WHERE run_id = %s",
            (run_id,),
        ).fetchone()
        if existing is None:
            return None
        now = int(finished_at_ms if finished_at_ms is not None else _now_ms())
        latency_ms = max(0, now - int(existing["started_at_ms"]))
        next_usage = usage_json if usage_json is not None else _decode_json_value(existing["usage_json"])
        next_trace_metadata = _mapping(_decode_json_value(existing["trace_metadata_json"]))
        if trace_metadata_json_patch is not None:
            next_trace_metadata = {**next_trace_metadata, **_mapping(trace_metadata_json_patch)}
        row = self.conn.execute(
            """
            UPDATE pulse_agent_runs
            SET status = %s,
                response_json = %s,
                error = %s,
                output_hash = COALESCE(%s, output_hash),
                usage_json = %s,
                latency_ms = %s,
                outcome = %s,
                decision_route = COALESCE(%s, decision_route),
                decision_stage_count = COALESCE(%s, decision_stage_count),
                evidence_packet_id = COALESCE(%s, evidence_packet_id),
                evidence_packet_hash = COALESCE(%s, evidence_packet_hash),
                evidence_status = COALESCE(%s, evidence_status),
                display_status = COALESCE(%s, display_status),
                trace_metadata_json = %s,
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
                outcome,
                decision_route,
                max(0, int(decision_stage_count)) if decision_stage_count is not None else None,
                evidence_packet_id,
                evidence_packet_hash,
                evidence_status,
                display_status,
                _json(next_trace_metadata),
                now,
                run_id,
            ),
        ).fetchone()
        if commit:
            self.conn.commit()
        return _optional_row(row)

    def insert_agent_run_step(
        self,
        *,
        step_id: str,
        run_id: str,
        stage: str,
        route: str,
        attempt_index: int,
        provider: str,
        model: str,
        prompt_version: str,
        schema_version: str,
        input_json: dict[str, Any],
        prompt_text: str,
        response_json: dict[str, Any] | None,
        trace_metadata_json: dict[str, Any] | None = None,
        usage_json: dict[str, Any] | None = None,
        latency_ms: int = 0,
        status: str = "ok",
        error: str | None = None,
        started_at_ms: int | None = None,
        finished_at_ms: int | None = None,
        created_at_ms: int | None = None,
        safety_net_used: bool = False,
        safety_net_retries: int = 0,
        parse_mode: str = "strict",
        commit: bool = True,
    ) -> dict[str, Any]:
        started = int(started_at_ms if started_at_ms is not None else _now_ms())
        finished = int(finished_at_ms if finished_at_ms is not None else started)
        created = int(created_at_ms if created_at_ms is not None else finished)
        row = self.conn.execute(
            """
            INSERT INTO pulse_agent_run_steps(
              step_id, run_id, stage, route, attempt_index, provider, model,
              prompt_version, schema_version, input_json, prompt_text, response_json,
              trace_metadata_json, usage_json, latency_ms, status, error,
              started_at_ms, finished_at_ms, created_at_ms,
              safety_net_used, safety_net_retries, parse_mode
            )
            VALUES (
              %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
              %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
              %s, %s, %s
            )
            ON CONFLICT(run_id, stage, attempt_index) DO UPDATE SET
              step_id = excluded.step_id,
              route = excluded.route,
              provider = excluded.provider,
              model = excluded.model,
              prompt_version = excluded.prompt_version,
              schema_version = excluded.schema_version,
              input_json = excluded.input_json,
              prompt_text = excluded.prompt_text,
              response_json = excluded.response_json,
              trace_metadata_json = excluded.trace_metadata_json,
              usage_json = excluded.usage_json,
              latency_ms = excluded.latency_ms,
              status = excluded.status,
              error = excluded.error,
              started_at_ms = excluded.started_at_ms,
              finished_at_ms = excluded.finished_at_ms,
              created_at_ms = excluded.created_at_ms,
              safety_net_used = excluded.safety_net_used,
              safety_net_retries = excluded.safety_net_retries,
              parse_mode = excluded.parse_mode
            RETURNING *
            """,
            (
                step_id,
                run_id,
                stage,
                route,
                max(0, int(attempt_index)),
                provider,
                model,
                prompt_version,
                schema_version,
                _json(input_json),
                prompt_text,
                _json(response_json) if response_json is not None else None,
                _json(trace_metadata_json or {}),
                _json(usage_json or {}),
                max(0, int(latency_ms)),
                status,
                error,
                started,
                finished,
                created,
                bool(safety_net_used),
                max(0, int(safety_net_retries)),
                str(parse_mode or "strict"),
            ),
        ).fetchone()
        if commit:
            self.conn.commit()
        return _row(row)

    def list_agent_run_steps(self, run_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM pulse_agent_run_steps
            WHERE run_id = %s
            ORDER BY started_at_ms ASC, stage ASC, attempt_index ASC
            """,
            (run_id,),
        ).fetchall()
        return [_row(row) for row in rows]

    def latest_agent_run_for_candidate(self, candidate_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT *
            FROM pulse_agent_runs
            WHERE candidate_id = %s
            ORDER BY finished_at_ms DESC, started_at_ms DESC, run_id DESC
            LIMIT 1
            """,
            (candidate_id,),
        ).fetchone()
        return _optional_row(row)
