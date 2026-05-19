from __future__ import annotations

from typing import Any

PUBLIC_DISPLAY_STATUSES = (
    "display_trade_candidate",
    "display_token_watch",
    "display_risk_rejected_high_info",
)


def fetch_pulse_health_clocks(conn: Any, *, window: str, scope: str) -> dict[str, int | None]:
    row = conn.execute(
        """
        SELECT
          (SELECT MAX(created_at_ms)
             FROM pulse_evidence_packets
            WHERE "window" = %s AND scope = %s) AS latest_packet_created_at_ms,
          (SELECT MAX(run.finished_at_ms)
             FROM pulse_agent_runs AS run
             JOIN pulse_agent_jobs AS job ON job.job_id = run.job_id
            WHERE job."window" = %s AND job.scope = %s) AS latest_agent_run_finished_at_ms,
          (SELECT MAX(updated_at_ms)
             FROM pulse_candidates
            WHERE "window" = %s
              AND scope = %s
              AND display_status = ANY(%s)
              AND evidence_packet_hash IS NOT NULL) AS latest_public_candidate_updated_at_ms
        """,
        (window, scope, window, scope, window, scope, list(PUBLIC_DISPLAY_STATUSES)),
    ).fetchone()
    payload = dict(row) if row else {}
    return {
        "latest_packet_created_at_ms": _optional_int(payload.get("latest_packet_created_at_ms")),
        "latest_agent_run_finished_at_ms": _optional_int(payload.get("latest_agent_run_finished_at_ms")),
        "latest_public_candidate_updated_at_ms": _optional_int(payload.get("latest_public_candidate_updated_at_ms")),
    }


def fetch_pulse_health_jobs(conn: Any, *, window: str, scope: str, now_ms: int, since_ms: int) -> dict[str, int]:
    row = conn.execute(
        """
        SELECT
          COUNT(*) FILTER (WHERE status = 'pending' AND next_run_at_ms <= %s) AS due_jobs,
          COUNT(*) FILTER (WHERE status = 'running') AS claimed_jobs,
          COUNT(*) FILTER (WHERE status = 'failed' AND updated_at_ms >= %s) AS failed_jobs_4h,
          COUNT(*) FILTER (WHERE status = 'dead') AS dead_jobs
        FROM pulse_agent_jobs
        WHERE "window" = %s AND scope = %s
        """,
        (int(now_ms), int(since_ms), window, scope),
    ).fetchone()
    payload = dict(row) if row else {}
    return {
        "due_jobs": _int(payload.get("due_jobs")),
        "claimed_jobs": _int(payload.get("claimed_jobs")),
        "failed_jobs_4h": _int(payload.get("failed_jobs_4h")),
        "dead_jobs": _int(payload.get("dead_jobs")),
    }


def fetch_pulse_health_runs(conn: Any, *, window: str, scope: str, since_ms: int) -> dict[str, int | float]:
    row = conn.execute(
        """
        SELECT
          COUNT(*) AS agent_runs_4h,
          COUNT(*) FILTER (WHERE run.status = 'failed' OR run.outcome IN (
            'invalid_schema',
            'invalid_unknown_evidence_ref',
            'invalid_unsupported_claim',
            'timeout',
            'provider_rate_limited',
            'provider_unavailable',
            'unexpected_exception'
          )) AS agent_failed_4h,
          COUNT(*) FILTER (WHERE run.outcome = 'invalid_unknown_evidence_ref') AS unknown_ref_failures_4h,
          COUNT(*) FILTER (WHERE run.outcome = 'invalid_unsupported_claim') AS unsupported_claim_failures_4h
        FROM pulse_agent_runs AS run
        JOIN pulse_agent_jobs AS job ON job.job_id = run.job_id
        WHERE job."window" = %s
          AND job.scope = %s
          AND run.finished_at_ms >= %s
        """,
        (window, scope, int(since_ms)),
    ).fetchone()
    payload = dict(row) if row else {}
    total = _int(payload.get("agent_runs_4h"))
    failed = _int(payload.get("agent_failed_4h"))
    unknown = _int(payload.get("unknown_ref_failures_4h"))
    unsupported = _int(payload.get("unsupported_claim_failures_4h"))
    return {
        "agent_runs_4h": total,
        "agent_failed_4h": failed,
        "agent_failure_rate_4h": _rate(failed, total),
        "unknown_ref_failures_4h": unknown,
        "unknown_ref_failure_rate_4h": _rate(unknown, total),
        "unsupported_claim_failures_4h": unsupported,
        "unsupported_claim_failure_rate_4h": _rate(unsupported, total),
    }


def fetch_pulse_health_candidates(conn: Any, *, window: str, scope: str, since_ms: int) -> dict[str, int]:
    row = conn.execute(
        """
        SELECT
          COUNT(*) FILTER (WHERE display_status = 'hidden_abstain') AS hidden_abstain_4h,
          COUNT(*) FILTER (WHERE display_status = 'hidden_hold_publish') AS hidden_hold_publish_4h,
          MAX(updated_at_ms) FILTER (
            WHERE display_status = 'hidden_hold_publish'
          ) AS latest_hidden_hold_candidate_updated_at_ms,
          COUNT(*) FILTER (
            WHERE display_status = 'hidden_insufficient_evidence'
          ) AS hidden_insufficient_evidence_4h,
          COUNT(*) FILTER (WHERE display_status = ANY(%s)) AS public_candidates_4h
        FROM pulse_candidates
        WHERE "window" = %s
          AND scope = %s
          AND updated_at_ms >= %s
        """,
        (list(PUBLIC_DISPLAY_STATUSES), window, scope, int(since_ms)),
    ).fetchone()
    payload = dict(row) if row else {}
    return {
        "hidden_abstain_4h": _int(payload.get("hidden_abstain_4h")),
        "hidden_hold_publish_4h": _int(payload.get("hidden_hold_publish_4h")),
        "latest_hidden_hold_candidate_updated_at_ms": _optional_int(
            payload.get("latest_hidden_hold_candidate_updated_at_ms")
        ),
        "hidden_insufficient_evidence_4h": _int(payload.get("hidden_insufficient_evidence_4h")),
        "public_candidates_4h": _int(payload.get("public_candidates_4h")),
    }


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _int(value: Any) -> int:
    return int(value or 0)


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return float(numerator) / float(denominator)


__all__ = [
    "PUBLIC_DISPLAY_STATUSES",
    "fetch_pulse_health_candidates",
    "fetch_pulse_health_clocks",
    "fetch_pulse_health_jobs",
    "fetch_pulse_health_runs",
]
