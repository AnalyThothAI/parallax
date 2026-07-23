from __future__ import annotations

from collections.abc import Mapping
from datetime import date, timedelta
from typing import Any

from psycopg.types.json import Jsonb

from parallax.domains.macro_intel.services.daily_macro_judgment import (
    DailyMacroJudgment,
    DailyMacroOutcome,
    MacroEvidencePack,
    ReviewerResult,
)
from parallax.domains.macro_intel.services.macro_concept_manifest import (
    MACRO_EVIDENCE_CONCEPTS,
)


class DailyMacroJudgmentRepository:
    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def material_observations_for_evidence(
        self,
        *,
        session_date: date,
        lookback_days: int,
        limit_per_series: int,
    ) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            WITH requested AS (
              SELECT unnest(%s::text[]) AS concept_key
            )
            SELECT selected.*
            FROM requested
            CROSS JOIN LATERAL (
              SELECT observations.*
              FROM macro_observations AS observations
              WHERE observations.concept_key = requested.concept_key
                AND (
                  (
                    observations.concept_key LIKE 'event:%%'
                    AND observations.observed_at BETWEEN %s AND %s
                  )
                  OR (
                    observations.concept_key NOT LIKE 'event:%%'
                    AND observations.observed_at BETWEEN %s AND %s
                  )
                )
              ORDER BY
                observations.observed_at DESC,
                observations.source_priority ASC,
                observations.source_name ASC,
                observations.series_key ASC
              LIMIT %s
            ) AS selected
            ORDER BY selected.concept_key ASC, selected.observed_at DESC,
                     selected.source_priority ASC, selected.source_name ASC, selected.series_key ASC
            """,
            (
                list(MACRO_EVIDENCE_CONCEPTS),
                session_date - timedelta(days=30),
                session_date + timedelta(days=366),
                session_date - timedelta(days=int(lookback_days)),
                session_date,
                int(limit_per_series),
            ),
        ).fetchall()
        return [dict(row) for row in rows]

    def eligible_news_text_rows(
        self,
        *,
        market_cutoff_ms: int,
        sealed_at_ms: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT
              items.news_item_id,
              items.source_id,
              sources.source_name,
              sources.trust_tier,
              sources.source_quality_status,
              items.published_at_ms,
              items.fetched_at_ms,
              items.title,
              items.summary,
              items.body_text,
              items.canonical_url,
              items.content_hash
            FROM news_items AS items
            JOIN news_sources AS sources ON sources.source_id = items.source_id
            WHERE items.lifecycle_status = 'processed'
              AND sources.trust_tier IN ('official', 'high')
              AND sources.source_quality_status IN ('healthy', 'degraded')
              AND items.published_at_ms <= %s
              AND items.fetched_at_ms <= %s
            ORDER BY items.published_at_ms DESC, items.source_id ASC, items.news_item_id ASC
            LIMIT %s
            """,
            (int(market_cutoff_ms), int(sealed_at_ms), int(limit)),
        ).fetchall()
        return [dict(row) for row in rows]

    def publication_exists(self, session_date: date) -> bool:
        row = self.conn.execute(
            "SELECT 1 AS present FROM macro_judgment_publications WHERE session_date = %s",
            (session_date,),
        ).fetchone()
        return row is not None

    def latest_job_session(self) -> date | None:
        row = self.conn.execute(
            "SELECT session_date FROM macro_judgment_jobs ORDER BY session_date DESC LIMIT 1"
        ).fetchone()
        return row["session_date"] if row is not None else None

    def insert_job(
        self,
        *,
        evidence_pack: MacroEvidencePack,
        compiler_version: str,
        max_attempts: int,
        due_at_ms: int,
        now_ms: int,
    ) -> bool:
        row = self.conn.execute(
            """
            INSERT INTO macro_judgment_jobs(
              session_date,
              market_cutoff_ms,
              status,
              evidence_pack_json,
              evidence_pack_hash,
              compiler_version,
              selection_policy_version,
              sealed_at_ms,
              max_attempts,
              due_at_ms,
              created_at_ms,
              updated_at_ms
            )
            VALUES (%s, %s, 'pending', %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(session_date) DO NOTHING
            RETURNING session_date
            """,
            (
                evidence_pack.session_date,
                evidence_pack.market_cutoff_ms,
                Jsonb(evidence_pack.model_dump(mode="json")),
                evidence_pack.pack_hash,
                str(compiler_version),
                evidence_pack.selection_policy_version,
                evidence_pack.sealed_at_ms,
                int(max_attempts),
                int(due_at_ms),
                int(now_ms),
                int(now_ms),
            ),
        ).fetchone()
        return row is not None

    def claim_due_job(
        self,
        *,
        lease_owner: str,
        lease_ms: int,
        now_ms: int,
    ) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            WITH candidate AS (
              SELECT session_date
              FROM macro_judgment_jobs
              WHERE (
                  status IN ('pending', 'retryable')
                  OR (status = 'running' AND leased_until_ms <= %s)
                )
                AND due_at_ms <= %s
                AND attempt_count < max_attempts
              ORDER BY session_date ASC
              FOR UPDATE SKIP LOCKED
              LIMIT 1
            )
            UPDATE macro_judgment_jobs AS jobs
            SET status = 'running',
                attempt_count = jobs.attempt_count + 1,
                leased_until_ms = %s,
                lease_owner = %s,
                last_error = NULL,
                updated_at_ms = %s
            FROM candidate
            WHERE jobs.session_date = candidate.session_date
            RETURNING jobs.*
            """,
            (int(now_ms), int(now_ms), int(now_ms) + int(lease_ms), str(lease_owner), int(now_ms)),
        ).fetchone()
        return dict(row) if row is not None else None

    def mark_job_error(
        self,
        *,
        session_date: date,
        lease_owner: str,
        error: str,
        retry_ms: int,
        now_ms: int,
    ) -> str:
        row = self.conn.execute(
            """
            UPDATE macro_judgment_jobs
            SET status = CASE WHEN attempt_count >= max_attempts THEN 'failed' ELSE 'retryable' END,
                due_at_ms = CASE
                  WHEN attempt_count >= max_attempts THEN due_at_ms
                  ELSE %s
                END,
                leased_until_ms = NULL,
                lease_owner = NULL,
                last_error = %s,
                updated_at_ms = %s
            WHERE session_date = %s
              AND status = 'running'
              AND lease_owner = %s
            RETURNING status
            """,
            (
                int(now_ms) + int(retry_ms),
                _safe_error(error),
                int(now_ms),
                session_date,
                str(lease_owner),
            ),
        ).fetchone()
        if row is None:
            raise RuntimeError("macro_judgment_job_error_owner_mismatch")
        return str(row["status"])

    def mark_job_blocked(
        self,
        *,
        session_date: date,
        lease_owner: str,
        error: str,
        reviewer_disposition: str | None,
        now_ms: int,
    ) -> None:
        row = self.conn.execute(
            """
            UPDATE macro_judgment_jobs
            SET status = 'blocked',
                leased_until_ms = NULL,
                lease_owner = NULL,
                reviewer_disposition = %s,
                last_error = %s,
                updated_at_ms = %s
            WHERE session_date = %s
              AND status = 'running'
              AND lease_owner = %s
            RETURNING session_date
            """,
            (
                reviewer_disposition,
                _safe_error(error),
                int(now_ms),
                session_date,
                str(lease_owner),
            ),
        ).fetchone()
        if row is None:
            raise RuntimeError("macro_judgment_job_block_owner_mismatch")

    def publish(
        self,
        *,
        session_date: date,
        lease_owner: str,
        judgment: DailyMacroJudgment,
        memo_text: str,
        evidence_pack_hash: str,
        review: ReviewerResult,
        agent_audit: Mapping[str, Any],
        model_name: str,
        prompt_version: str,
        schema_version: str,
        workflow_version: str,
        renderer_version: str,
        now_ms: int,
    ) -> bool:
        inserted = self.conn.execute(
            """
            INSERT INTO macro_judgment_publications(
              session_date,
              market_cutoff_ms,
              evidence_pack_hash,
              judgment_json,
              memo_text,
              review_json,
              agent_audit_json,
              model_name,
              prompt_version,
              schema_version,
              workflow_version,
              renderer_version,
              published_at_ms
            )
            SELECT
              jobs.session_date,
              jobs.market_cutoff_ms,
              %s,
              %s,
              %s,
              %s,
              %s,
              %s,
              %s,
              %s,
              %s,
              %s,
              %s
            FROM macro_judgment_jobs AS jobs
            WHERE jobs.session_date = %s
              AND jobs.status = 'running'
              AND jobs.lease_owner = %s
              AND jobs.evidence_pack_hash = %s
            ON CONFLICT(session_date) DO NOTHING
            RETURNING session_date
            """,
            (
                str(evidence_pack_hash),
                Jsonb(judgment.model_dump(mode="json")),
                str(memo_text),
                Jsonb(review.model_dump(mode="json")),
                Jsonb(dict(agent_audit)),
                str(model_name),
                str(prompt_version),
                str(schema_version),
                str(workflow_version),
                str(renderer_version),
                int(now_ms),
                session_date,
                str(lease_owner),
                str(evidence_pack_hash),
            ),
        ).fetchone()
        if inserted is None:
            return False
        completed = self.conn.execute(
            """
            UPDATE macro_judgment_jobs
            SET status = 'published',
                leased_until_ms = NULL,
                lease_owner = NULL,
                reviewer_disposition = 'pass',
                last_error = NULL,
                updated_at_ms = %s
            WHERE session_date = %s
              AND status = 'running'
            RETURNING session_date
            """,
            (int(now_ms), session_date),
        ).fetchone()
        if completed is None:
            raise RuntimeError("macro_judgment_publication_completion_failed")
        return True

    def publication_record(self, session_date: date) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT
              publications.*,
              jobs.evidence_pack_json,
              jobs.compiler_version,
              jobs.selection_policy_version,
              jobs.sealed_at_ms
            FROM macro_judgment_publications AS publications
            JOIN macro_judgment_jobs AS jobs USING (session_date)
            WHERE publications.session_date = %s
            """,
            (session_date,),
        ).fetchone()
        return dict(row) if row is not None else None

    def latest_publication_record(self) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT
              publications.*,
              jobs.evidence_pack_json,
              jobs.compiler_version,
              jobs.selection_policy_version,
              jobs.sealed_at_ms
            FROM macro_judgment_publications AS publications
            JOIN macro_judgment_jobs AS jobs USING (session_date)
            ORDER BY publications.session_date DESC
            LIMIT 1
            """
        ).fetchone()
        return dict(row) if row is not None else None

    def job_record(self, session_date: date) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM macro_judgment_jobs WHERE session_date = %s",
            (session_date,),
        ).fetchone()
        return dict(row) if row is not None else None

    def outcomes_for_session(self, session_date: date) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT
              session_date,
              horizon_sessions,
              target_session_date,
              start_close,
              target_close,
              realized_return_pct,
              source_evidence_refs_json AS source_evidence_refs,
              computed_at_ms
            FROM macro_judgment_outcomes
            WHERE session_date = %s
            ORDER BY horizon_sessions ASC
            """,
            (session_date,),
        ).fetchall()
        return [dict(row) for row in rows]

    def publications_missing_outcomes(self, *, limit: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT publications.session_date, publications.market_cutoff_ms
            FROM macro_judgment_publications AS publications
            WHERE EXISTS (
              SELECT 1
              FROM (VALUES (5), (20)) AS horizons(horizon_sessions)
              WHERE NOT EXISTS (
                SELECT 1
                FROM macro_judgment_outcomes AS outcomes
                WHERE outcomes.session_date = publications.session_date
                  AND outcomes.horizon_sessions = horizons.horizon_sessions
              )
            )
            ORDER BY publications.session_date ASC
            LIMIT %s
            """,
            (int(limit),),
        ).fetchall()
        return [dict(row) for row in rows]

    def spy_close(self, session_date: date) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT
              observation_id,
              observed_at,
              value_numeric,
              source_name,
              series_key,
              fact_payload_hash
            FROM macro_observations
            WHERE concept_key = 'asset:spy'
              AND observed_at = %s
              AND value_numeric IS NOT NULL
              AND value_numeric > 0
            ORDER BY source_priority ASC, source_name ASC, series_key ASC
            LIMIT 1
            """,
            (session_date,),
        ).fetchone()
        return dict(row) if row is not None else None

    def insert_outcome(self, outcome: DailyMacroOutcome) -> bool:
        row = self.conn.execute(
            """
            INSERT INTO macro_judgment_outcomes(
              session_date,
              horizon_sessions,
              target_session_date,
              start_close,
              target_close,
              realized_return_pct,
              source_evidence_refs_json,
              computed_at_ms
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT(session_date, horizon_sessions) DO NOTHING
            RETURNING session_date
            """,
            (
                outcome.session_date,
                outcome.horizon_sessions,
                outcome.target_session_date,
                outcome.start_close,
                outcome.target_close,
                outcome.realized_return_pct,
                Jsonb(list(outcome.source_evidence_refs)),
                outcome.computed_at_ms,
            ),
        ).fetchone()
        return row is not None


def _safe_error(value: object) -> str:
    return str(value or "macro_judgment_unknown_error").replace("\n", " ")[:1_000]


__all__ = ["DailyMacroJudgmentRepository"]
