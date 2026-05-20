from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.domains.pulse_lab.repositories._pulse_repository_shared import (
    _decode_cursor,
    _encode_cursor,
    _normalize_subject,
    _optional_row,
    _row,
)

PUBLIC_DISPLAY_STATUS_SQL = "('display_trade_candidate', 'display_token_watch', 'display_risk_rejected_high_info')"
PUBLIC_DISPLAY_STATUS_BY_PUBLIC_STATUS = {
    "trade_candidate": "display_trade_candidate",
    "token_watch": "display_token_watch",
    "risk_rejected_high_info": "display_risk_rejected_high_info",
}


class PulseReadRepository:
    def __init__(self, conn: Any, *, running_timeout_ms: int = 300_000):
        self.conn = conn
        self.running_timeout_ms = int(running_timeout_ms)

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
        if q:
            pattern = f"%{q.strip()}%"
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
