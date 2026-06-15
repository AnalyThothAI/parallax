from __future__ import annotations

from typing import Any

from parallax.domains.pulse_lab.repositories._pulse_repository_shared import (
    _json,
    _now_ms,
    _optional_row,
    _row,
    _run_repository_write,
)


def _cursor_rowcount(cursor: Any) -> int:
    try:
        rowcount: object = cursor.rowcount
    except AttributeError as exc:
        raise TypeError("pulse_agent_eval_repository_rowcount_required") from exc
    if isinstance(rowcount, bool) or not isinstance(rowcount, int) or rowcount < 0:
        raise TypeError("pulse_agent_eval_repository_rowcount_invalid")
    return rowcount


def _required_returning_row(cursor: Any, row: Any) -> dict[str, Any]:
    if _cursor_rowcount(cursor) != 1 or row is None:
        raise TypeError("pulse_agent_eval_repository_rowcount_invalid")
    return _row(row)


class PulseAgentEvalRepository:
    def __init__(self, conn: Any):
        self.conn = conn

    def upsert_agent_runtime_version(
        self,
        *,
        runtime_version: str,
        runtime_hash: str,
        strategy: str,
        provider: str,
        model: str,
        prompt_version: str,
        schema_version: str,
        manifest_json: dict[str, Any],
        created_at_ms: int | None = None,
        commit: bool = True,
    ) -> dict[str, Any]:
        def _upsert_agent_runtime_version() -> dict[str, Any]:
            created = int(created_at_ms if created_at_ms is not None else _now_ms())
            cursor = self.conn.execute(
                """
                INSERT INTO pulse_agent_runtime_versions(
                  runtime_hash, runtime_version, strategy, provider, model, prompt_version,
                  schema_version, manifest_json, created_at_ms
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(runtime_hash) DO UPDATE SET
                  runtime_version = excluded.runtime_version,
                  strategy = excluded.strategy,
                  provider = excluded.provider,
                  model = excluded.model,
                  prompt_version = excluded.prompt_version,
                  schema_version = excluded.schema_version,
                  manifest_json = excluded.manifest_json
                RETURNING *
                """,
                (
                    runtime_hash,
                    runtime_version,
                    strategy,
                    provider,
                    model,
                    prompt_version,
                    schema_version,
                    _json(manifest_json),
                    created,
                ),
            )
            row = cursor.fetchone()
            return _required_returning_row(cursor, row)

        return _run_repository_write(self.conn, commit, _upsert_agent_runtime_version)

    def agent_runtime_version(self, runtime_hash: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT *
            FROM pulse_agent_runtime_versions
            WHERE runtime_hash = %s
            """,
            (runtime_hash,),
        ).fetchone()
        return _optional_row(row)

    def insert_agent_eval_case(
        self,
        *,
        eval_case_id: str,
        source_run_id: str,
        runtime_hash: str,
        eval_type: str,
        route: str,
        recommendation: str,
        input_json: dict[str, Any],
        expected_json: dict[str, Any],
        rubric_json: dict[str, Any],
        status: str = "active",
        created_at_ms: int | None = None,
        commit: bool = True,
    ) -> dict[str, Any]:
        def _insert_agent_eval_case() -> dict[str, Any]:
            created = int(created_at_ms if created_at_ms is not None else _now_ms())
            cursor = self.conn.execute(
                """
                INSERT INTO pulse_agent_eval_cases(
                  eval_case_id, source_run_id, runtime_hash, eval_type, route, recommendation,
                  input_json, expected_json, rubric_json, status, created_at_ms
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(source_run_id, eval_type) DO UPDATE SET
                  runtime_hash = excluded.runtime_hash,
                  route = excluded.route,
                  recommendation = excluded.recommendation,
                  input_json = excluded.input_json,
                  expected_json = excluded.expected_json,
                  rubric_json = excluded.rubric_json,
                  status = excluded.status,
                  created_at_ms = excluded.created_at_ms
                RETURNING *
                """,
                (
                    eval_case_id,
                    source_run_id,
                    runtime_hash,
                    eval_type,
                    route,
                    recommendation,
                    _json(input_json),
                    _json(expected_json),
                    _json(rubric_json),
                    status,
                    created,
                ),
            )
            row = cursor.fetchone()
            return _required_returning_row(cursor, row)

        return _run_repository_write(self.conn, commit, _insert_agent_eval_case)

    def list_agent_eval_cases(self, *, source_run_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM pulse_agent_eval_cases
            WHERE source_run_id = %s
            ORDER BY created_at_ms ASC, eval_case_id ASC
            """,
            (source_run_id,),
        ).fetchall()
        return [_row(row) for row in rows]

    def upsert_agent_eval_result(
        self,
        *,
        eval_result_id: str,
        eval_case_id: str,
        runtime_hash: str,
        status: str,
        score: float,
        grader_version: str,
        details_json: dict[str, Any],
        created_at_ms: int | None = None,
        commit: bool = True,
    ) -> dict[str, Any]:
        def _upsert_agent_eval_result() -> dict[str, Any]:
            created = int(created_at_ms if created_at_ms is not None else _now_ms())
            cursor = self.conn.execute(
                """
                INSERT INTO pulse_agent_eval_results(
                  eval_result_id, eval_case_id, runtime_hash, status, score,
                  grader_version, details_json, created_at_ms
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(eval_case_id, runtime_hash, grader_version) DO UPDATE SET
                  eval_result_id = excluded.eval_result_id,
                  status = excluded.status,
                  score = excluded.score,
                  details_json = excluded.details_json,
                  created_at_ms = excluded.created_at_ms
                RETURNING *
                """,
                (
                    eval_result_id,
                    eval_case_id,
                    runtime_hash,
                    status,
                    float(score),
                    grader_version,
                    _json(details_json),
                    created,
                ),
            )
            row = cursor.fetchone()
            return _required_returning_row(cursor, row)

        return _run_repository_write(self.conn, commit, _upsert_agent_eval_result)

    def list_agent_eval_results(self, *, eval_case_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM pulse_agent_eval_results
            WHERE eval_case_id = %s
            ORDER BY created_at_ms ASC, eval_result_id ASC
            """,
            (eval_case_id,),
        ).fetchall()
        return [_row(row) for row in rows]
