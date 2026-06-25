from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from parallax.domains.pulse_lab.queries.pulse_freshness_health_queries import (
    fetch_pulse_health_candidates,
    fetch_pulse_health_clocks,
    fetch_pulse_health_jobs,
    fetch_pulse_health_runs,
)
from parallax.domains.pulse_lab.repositories._pulse_repository_shared import (
    _decode_cursor,
    _encode_cursor,
    _normalize_subject,
    _optional_row,
    _row,
)
from parallax.domains.pulse_lab.types.pulse_freshness_health import (
    classify_pulse_freshness_health,
    pulse_freshness_since_hours,
    pulse_freshness_since_ms,
)

PUBLIC_DISPLAY_STATUS_SQL = "('display_trade_candidate', 'display_token_watch', 'display_risk_rejected_high_info')"
PUBLIC_DISPLAY_STATUS_BY_PUBLIC_STATUS = {
    "trade_candidate": "display_trade_candidate",
    "token_watch": "display_token_watch",
    "risk_rejected_high_info": "display_risk_rejected_high_info",
}


class PulseReadRepository:
    def __init__(self, conn: Any):
        self.conn = conn

    def list_candidates(
        self,
        window: str,
        scope: str,
        limit: int,
        status: str | None = None,
        cursor: str | None = None,
        q: str | None = None,
        handle: str | None = None,
        displayable_only: bool = False,
        hidden_only: bool = False,
    ) -> dict[str, Any]:
        bounded_limit = max(0, min(int(limit), 200))
        clauses = ['candidate."window" = %s', "candidate.scope = %s"]
        params: list[Any] = [window, scope]
        if status:
            public_display_status = PUBLIC_DISPLAY_STATUS_BY_PUBLIC_STATUS.get(status)
            if public_display_status is None:
                raise ValueError(f"invalid public Signal Pulse status: {status}")
            clauses.append("candidate.display_status = %s")
            params.append(public_display_status)
        if displayable_only:
            clauses.append(f"candidate.display_status IN {PUBLIC_DISPLAY_STATUS_SQL}")
            clauses.append("candidate.evidence_packet_hash IS NOT NULL")
        if hidden_only:
            clauses.append("left(candidate.display_status, 7) = 'hidden_'")
        if handle:
            handle_clause, handle_params = _candidate_handle_filter_clause("candidate", handle)
            if handle_clause:
                clauses.append(handle_clause)
                params.extend(handle_params)
        normalized_q = _normalize_public_search_q(q)
        if normalized_q:
            pattern = f"%{normalized_q}%"
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

    def list_signal_pulse_notification_candidates(
        self,
        *,
        window: str,
        scopes: Sequence[str],
        statuses: Sequence[str],
        per_scope_status_limit: int,
    ) -> list[dict[str, Any]]:
        normalized_scopes = _ordered_non_empty(scopes)
        normalized_statuses = _ordered_non_empty(statuses)
        bounded_limit = _required_nonnegative_int(
            per_scope_status_limit,
            "pulse_notification_candidate_limit_required",
        )
        if not normalized_scopes or not normalized_statuses or bounded_limit == 0:
            return []
        display_statuses = [_public_display_status(status) for status in normalized_statuses]
        rows = self.conn.execute(
            f"""
            WITH input_scopes AS (
              SELECT scope, ordinality AS scope_ordinal
              FROM unnest(%s::text[]) WITH ORDINALITY AS input(scope, ordinality)
            ),
            input_statuses AS (
              SELECT public_status, display_status, ordinality AS status_ordinal
              FROM unnest(%s::text[], %s::text[])
                WITH ORDINALITY AS input(public_status, display_status, ordinality)
            ),
            candidate_rows AS (
              SELECT
                candidate.*,
                input_scopes.scope_ordinal,
                input_statuses.status_ordinal,
                ROW_NUMBER() OVER (
                  PARTITION BY input_scopes.scope, input_statuses.public_status
                  ORDER BY candidate.updated_at_ms DESC, candidate.candidate_id DESC
                ) AS bucket_rank
              FROM input_scopes
              JOIN input_statuses ON true
              JOIN pulse_candidates AS candidate
                ON candidate."window" = %s
               AND candidate.scope = input_scopes.scope
               AND candidate.pulse_status = input_statuses.public_status
               AND candidate.display_status = input_statuses.display_status
              WHERE input_statuses.display_status IN {PUBLIC_DISPLAY_STATUS_SQL}
                AND candidate.evidence_packet_hash IS NOT NULL
            )
            SELECT *
            FROM candidate_rows
            WHERE bucket_rank <= %s
            ORDER BY scope_ordinal ASC, status_ordinal ASC, bucket_rank ASC
            """,
            (
                normalized_scopes,
                normalized_statuses,
                display_statuses,
                window,
                bounded_limit,
            ),
        ).fetchall()
        return [_row(row) for row in rows]

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
        normalized_q = _normalize_public_search_q(q)
        if normalized_q:
            pattern = f"%{normalized_q}%"
            clauses.append(
                "(candidate.symbol ILIKE %s OR candidate.subject_key ILIKE %s OR candidate.target_id ILIKE %s)"
            )
            params.extend([pattern, pattern, pattern])
        candidate_row = self.conn.execute(
            f"""
            SELECT
              COUNT(*) AS candidate_count,
              COUNT(*) FILTER (WHERE display_status = 'display_trade_candidate') AS trade_candidate_count,
              COUNT(*) FILTER (WHERE display_status = 'display_token_watch') AS token_watch_count,
              COUNT(*) FILTER (
                WHERE display_status = 'display_risk_rejected_high_info'
              ) AS risk_rejected_high_info_count,
              COUNT(*) FILTER (
                WHERE display_status IN {PUBLIC_DISPLAY_STATUS_SQL} AND decision_route = 'cex'
              ) AS decision_route_cex_count,
              COUNT(*) FILTER (
                WHERE display_status IN {PUBLIC_DISPLAY_STATUS_SQL} AND decision_route = 'meme'
              ) AS decision_route_meme_count,
              COUNT(*) FILTER (
                WHERE display_status IN {PUBLIC_DISPLAY_STATUS_SQL} AND decision_route = 'research_only'
              ) AS decision_route_research_only_count,
              COUNT(*) FILTER (
                WHERE display_status IN {PUBLIC_DISPLAY_STATUS_SQL}
                  AND decision_recommendation = 'high_conviction'
              ) AS decision_high_conviction_count,
              COUNT(*) FILTER (
                WHERE display_status IN {PUBLIC_DISPLAY_STATUS_SQL}
                  AND decision_recommendation = 'trade_candidate'
              ) AS decision_trade_candidate_count,
              COUNT(*) FILTER (
                WHERE display_status IN {PUBLIC_DISPLAY_STATUS_SQL}
                  AND decision_recommendation = 'watchlist'
              ) AS decision_watchlist_count,
              COUNT(*) FILTER (
                WHERE display_status IN {PUBLIC_DISPLAY_STATUS_SQL}
                  AND decision_recommendation = 'ignore'
              ) AS decision_ignore_count,
              COUNT(*) FILTER (
                WHERE display_status IN {PUBLIC_DISPLAY_STATUS_SQL}
                  AND decision_recommendation = 'abstain'
              ) AS decision_abstain_count,
              COUNT(*) FILTER (
                WHERE pulse_status = 'blocked_low_information'
                   OR verdict = 'blocked_low_information'
                   OR gate_reasons_json @> '["low_information"]'::jsonb
              ) AS blocked_low_information_count,
              COUNT(*) FILTER (WHERE display_status IN {PUBLIC_DISPLAY_STATUS_SQL}) AS displayable_count,
              COUNT(*) FILTER (WHERE left(display_status, 7) = 'hidden_') AS hidden_candidate_count,
              COUNT(*) FILTER (
                WHERE display_status IN {PUBLIC_DISPLAY_STATUS_SQL}
                  AND evidence_packet_hash IS NOT NULL
                  AND evidence_status IN ('complete', 'partial')
              ) AS market_fresh_count
            FROM pulse_candidates
            AS candidate
            WHERE {" AND ".join(clauses)}
            """,
            tuple(params),
        ).fetchone()
        abstain_rows = self.conn.execute(
            f"""
            SELECT
              COALESCE(NULLIF(decision_abstain_reason, ''), 'unspecified') AS reason,
              COUNT(*) AS count
            FROM pulse_candidates
            AS candidate
            WHERE {" AND ".join(clauses)}
              AND display_status IN {PUBLIC_DISPLAY_STATUS_SQL}
              AND decision_recommendation = 'abstain'
            GROUP BY reason
            ORDER BY count DESC, reason ASC
            """,
            tuple(params),
        ).fetchall()
        job_clauses = ['job."window" = %s', "job.scope = %s", "job.status = 'dead'"]
        job_params: list[Any] = [window, scope]
        if handle:
            normalized_handle = _normalize_subject(handle)
            candidate_handle_clause, candidate_handle_params = _candidate_handle_filter_clause("candidate", handle)
            if normalized_handle and candidate_handle_clause:
                job_clauses.append(f"(lower(job.subject_key) = %s OR {candidate_handle_clause})")
                job_params.extend([normalized_handle, *candidate_handle_params])
        if normalized_q:
            pattern = f"%{normalized_q}%"
            job_clauses.append("(candidate.symbol ILIKE %s OR job.subject_key ILIKE %s OR job.target_id ILIKE %s)")
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
            "risk_rejected_high_info": int(row.get("risk_rejected_high_info_count") or 0),
        }
        decision_route_counts = {
            "cex": int(row.get("decision_route_cex_count") or 0),
            "meme": int(row.get("decision_route_meme_count") or 0),
            "research_only": int(row.get("decision_route_research_only_count") or 0),
        }
        decision_recommendation_counts = {
            "high_conviction": int(row.get("decision_high_conviction_count") or 0),
            "trade_candidate": int(row.get("decision_trade_candidate_count") or 0),
            "watchlist": int(row.get("decision_watchlist_count") or 0),
            "ignore": int(row.get("decision_ignore_count") or 0),
            "abstain": int(row.get("decision_abstain_count") or 0),
        }
        decision_abstain_reason_counts = {
            str(abstain_row["reason"]): int(abstain_row["count"]) for abstain_row in abstain_rows
        }
        displayable_count = int(row.get("displayable_count") or 0)
        market_fresh_count = int(row.get("market_fresh_count") or 0)
        return {
            "window": window,
            "scope": scope,
            "summary": summary,
            "decision_route_counts": decision_route_counts,
            "decision_recommendation_counts": decision_recommendation_counts,
            "decision_abstain_reason_counts": decision_abstain_reason_counts,
            "decision_error_count": 0,
            "candidate_count": int(row.get("candidate_count") or 0),
            "public_candidate_count": displayable_count,
            "displayable_count": displayable_count,
            "hidden_candidate_count": int(row.get("hidden_candidate_count") or 0),
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
                WHERE display_status IN (
                  'display_trade_candidate',
                  'display_token_watch',
                  'display_risk_rejected_high_info'
                )
                AND evidence_packet_hash IS NOT NULL
              ) AS displayable_count,
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
            "displayable_count": int(candidate_row["displayable_count"] if candidate_row else 0),
            "blocked_low_information_count": int(
                candidate_row["blocked_low_information_count"] if candidate_row else 0
            ),
            "dead_job_count": int(job_counts.get("dead", 0)),
            "job_counts": job_counts,
        }

    def freshness_health(self, *, window: str, scope: str, now_ms: int, since_hours: int) -> dict[str, Any]:
        since_hour_count = pulse_freshness_since_hours(since_hours)
        since_ms = pulse_freshness_since_ms(now_ms=now_ms, since_hours=since_hours)
        clocks = fetch_pulse_health_clocks(self.conn, window=window, scope=scope)
        jobs = fetch_pulse_health_jobs(self.conn, window=window, scope=scope, now_ms=now_ms, since_ms=since_ms)
        runs = fetch_pulse_health_runs(self.conn, window=window, scope=scope, since_ms=since_ms)
        candidates = fetch_pulse_health_candidates(self.conn, window=window, scope=scope, since_ms=since_ms)
        status, reasons = classify_pulse_freshness_health(
            clocks=clocks,
            jobs=jobs,
            runs=runs,
            now_ms=now_ms,
        )
        return {
            "window": window,
            "scope": scope,
            "since_hours": since_hour_count,
            "publish_status": status,
            "reasons": reasons,
            **clocks,
            **jobs,
            **runs,
            **candidates,
        }


def _candidate_handle_filter_clause(candidate_alias: str, handle: str | None) -> tuple[str, list[Any]]:
    normalized = _normalize_subject(handle)
    if not normalized:
        return "", []
    return (
        f"""
        lower({candidate_alias}.subject_key) = %s
        """,
        [normalized],
    )


def _normalize_public_search_q(q: str | None) -> str:
    if q is None:
        return ""
    return str(q).strip()


def _required_nonnegative_int(value: Any, error_code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(error_code)
    return int(value)


def _ordered_non_empty(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(str(value).strip() for value in values if str(value or "").strip()))


def _public_display_status(status: str) -> str:
    public_display_status = PUBLIC_DISPLAY_STATUS_BY_PUBLIC_STATUS.get(status)
    if public_display_status is None:
        raise ValueError(f"invalid public Signal Pulse status: {status}")
    return public_display_status
