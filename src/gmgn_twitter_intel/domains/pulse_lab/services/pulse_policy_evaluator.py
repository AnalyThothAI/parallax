from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from gmgn_twitter_intel.domains.pulse_lab.interfaces import PULSE_VERSION
from gmgn_twitter_intel.domains.token_intel._constants import TOKEN_RADAR_PROJECTION_VERSION

DEFAULT_CURRENT_POLICY_WINDOWS = ("5m", "1h", "4h", "24h")
DEFAULT_CURRENT_POLICY_SCOPES = ("all", "matched")
PROPOSED_PRIMARY_WINDOWS = ("1h", "4h")
PROPOSED_PRIMARY_SCOPES = ("all",)
EVALUATED_WINDOWS = ("5m", "1h", "4h", "24h")
EVALUATED_SCOPES = ("all", "matched", "watched")
FAILURE_OUTCOMES = {
    "invalid_schema",
    "invalid_unknown_evidence_ref",
    "invalid_unsupported_claim",
    "timeout",
    "provider_rate_limited",
    "provider_unavailable",
    "unexpected_exception",
    "backpressure_released",
}
BACKPRESSURE_JOB_STATUSES = {"pending", "running", "dead"}


def fetch_radar_rows(conn: Any, *, now_ms: int, lookback_hours: int) -> list[dict[str, Any]]:
    since_ms = _since_ms(now_ms=now_ms, lookback_hours=lookback_hours)
    results: list[dict[str, Any]] = []
    for window in EVALUATED_WINDOWS:
        for scope in EVALUATED_SCOPES:
            latest = conn.execute(
                """
                SELECT computed_at_ms
                FROM token_radar_rows
                WHERE computed_at_ms >= %s
                  AND computed_at_ms <= %s
                  AND projection_version = %s
                  AND "window" = %s
                  AND scope = %s
                ORDER BY computed_at_ms DESC
                LIMIT 1
                """,
                (since_ms, int(now_ms), TOKEN_RADAR_PROJECTION_VERSION, window, scope),
            ).fetchone()
            if not latest:
                continue
            computed_at_ms = int(dict(latest).get("computed_at_ms") or 0)
            rows = conn.execute(
                """
                SELECT
                  "window",
                  scope,
                  row_id,
                  COALESCE(target_type || ':' || target_id, intent_id, event_id, row_id) AS subject_key,
                  decision,
                  rank,
                  computed_at_ms,
                  source_max_received_at_ms,
                  factor_snapshot_json,
                  source_event_ids_json
                FROM token_radar_rows
                WHERE projection_version = %s
                  AND "window" = %s
                  AND scope = %s
                  AND computed_at_ms = %s
                ORDER BY rank ASC
                """,
                (TOKEN_RADAR_PROJECTION_VERSION, window, scope, computed_at_ms),
            ).fetchall()
            results.extend(dict(row) for row in rows)
    return results


def fetch_candidate_rows(conn: Any, *, now_ms: int, lookback_hours: int) -> list[dict[str, Any]]:
    since_ms = _since_ms(now_ms=now_ms, lookback_hours=lookback_hours)
    rows = conn.execute(
        """
        SELECT
          "window",
          scope,
          candidate_id,
          subject_key,
          target_type,
          target_id,
          symbol,
          pulse_status,
          verdict,
          social_phase,
          candidate_score,
          score_band,
          display_status,
          evidence_status,
          decision_status,
          decision_route,
          decision_recommendation,
          decision_confidence,
          evidence_packet_hash,
          factor_snapshot_json,
          updated_at_ms
        FROM pulse_candidates
        WHERE updated_at_ms >= %s
          AND updated_at_ms <= %s
          AND pulse_version = %s
          AND "window" = ANY(%s)
          AND scope = ANY(%s)
        """,
        (since_ms, int(now_ms), PULSE_VERSION, list(EVALUATED_WINDOWS), list(EVALUATED_SCOPES)),
    ).fetchall()
    return [dict(row) for row in rows]


def fetch_run_rows(conn: Any, *, now_ms: int, lookback_hours: int) -> list[dict[str, Any]]:
    since_ms = _since_ms(now_ms=now_ms, lookback_hours=lookback_hours)
    rows = conn.execute(
        """
        SELECT
          job."window",
          job.scope,
          run.run_id,
          run.candidate_id,
          run.status,
          run.outcome,
          run.decision_route,
          run.decision_stage_count,
          run.evidence_status,
          run.display_status,
          run.evidence_packet_hash,
          run.latency_ms,
          run.started_at_ms,
          run.finished_at_ms,
          job.status AS job_status,
          job.attempt_count,
          job.max_attempts,
          job.next_run_at_ms
        FROM pulse_agent_runs AS run
        JOIN pulse_agent_jobs AS job ON job.job_id = run.job_id
        WHERE run.started_at_ms >= %s
          AND run.started_at_ms <= %s
          AND job."window" = ANY(%s)
          AND job.scope = ANY(%s)
        """,
        (since_ms, int(now_ms), list(EVALUATED_WINDOWS), list(EVALUATED_SCOPES)),
    ).fetchall()
    return [dict(row) for row in rows]


def fetch_job_rows(conn: Any, *, now_ms: int, lookback_hours: int) -> list[dict[str, Any]]:
    since_ms = _since_ms(now_ms=now_ms, lookback_hours=lookback_hours)
    rows = conn.execute(
        """
        SELECT
          job."window",
          job.scope,
          job.job_id,
          job.candidate_id,
          job.candidate_type,
          job.subject_key,
          job.status,
          job.attempt_count,
          job.max_attempts,
          job.next_run_at_ms,
          job.last_error,
          job.created_at_ms,
          job.updated_at_ms,
          latest.run_id AS latest_run_id,
          latest.status AS latest_run_status,
          latest.outcome AS latest_run_outcome,
          latest.finished_at_ms AS latest_run_finished_at_ms
        FROM pulse_agent_jobs AS job
        LEFT JOIN LATERAL (
          SELECT run.run_id, run.status, run.outcome, run.finished_at_ms
          FROM pulse_agent_runs AS run
          WHERE run.job_id = job.job_id
          ORDER BY run.started_at_ms DESC, run.run_id DESC
          LIMIT 1
        ) AS latest ON true
        WHERE job.updated_at_ms >= %s
          AND job.updated_at_ms <= %s
          AND job."window" = ANY(%s)
          AND job.scope = ANY(%s)
        """,
        (since_ms, int(now_ms), list(EVALUATED_WINDOWS), list(EVALUATED_SCOPES)),
    ).fetchall()
    return [dict(row) for row in rows]


def summarize_radar_policy_rows(
    rows: list[dict[str, Any]],
    *,
    current_windows: tuple[str, ...] | None = None,
    current_scopes: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    summary = summarize_by_window_scope(rows, current_windows=current_windows, current_scopes=current_scopes)
    summary["sample_kind"] = "latest_snapshot"
    summary["computed_at_ms"] = _computed_at_bounds(rows)
    return summary


def summarize_candidate_policy_rows(
    rows: list[dict[str, Any]],
    *,
    current_windows: tuple[str, ...] | None = None,
    current_scopes: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    return _summarize_candidates_by_window_scope(
        rows, current_windows=current_windows, current_scopes=current_scopes
    )


def summarize_pulse_run_rows(
    rows: list[dict[str, Any]],
    *,
    current_windows: tuple[str, ...] | None = None,
    current_scopes: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    return summarize_by_window_scope_and_outcome(
        rows, current_windows=current_windows, current_scopes=current_scopes
    )


def summarize_job_policy_rows(
    rows: list[dict[str, Any]],
    *,
    now_ms: int,
    current_windows: tuple[str, ...] | None = None,
    current_scopes: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    return _policy_summary(
        rows,
        summarizer=lambda group_rows: _summarize_job_rows(group_rows, now_ms=now_ms),
        current_windows=current_windows,
        current_scopes=current_scopes,
    )


def summarize_by_window_scope(
    rows: list[dict[str, Any]],
    *,
    current_windows: tuple[str, ...] | None = None,
    current_scopes: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    return _policy_summary(
        rows,
        summarizer=_summarize_source_quality_rows,
        current_windows=current_windows,
        current_scopes=current_scopes,
    )


def summarize_by_window_scope_and_outcome(
    rows: list[dict[str, Any]],
    *,
    current_windows: tuple[str, ...] | None = None,
    current_scopes: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    return _policy_summary(
        rows,
        summarizer=_summarize_run_rows,
        current_windows=current_windows,
        current_scopes=current_scopes,
    )


def build_pulse_policy_evaluation(
    conn: Any,
    *,
    now_ms: int,
    lookback_hours: int = 24,
    current_windows: tuple[str, ...] | None = None,
    current_scopes: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    radar_rows = fetch_radar_rows(conn, now_ms=now_ms, lookback_hours=lookback_hours)
    candidate_rows = fetch_candidate_rows(conn, now_ms=now_ms, lookback_hours=lookback_hours)
    run_rows = fetch_run_rows(conn, now_ms=now_ms, lookback_hours=lookback_hours)
    job_rows = fetch_job_rows(conn, now_ms=now_ms, lookback_hours=lookback_hours)
    return {
        "radar": summarize_radar_policy_rows(
            radar_rows, current_windows=current_windows, current_scopes=current_scopes
        ),
        "candidates": summarize_candidate_policy_rows(
            candidate_rows, current_windows=current_windows, current_scopes=current_scopes
        ),
        "runs": summarize_pulse_run_rows(run_rows, current_windows=current_windows, current_scopes=current_scopes),
        "jobs": summarize_job_policy_rows(
            job_rows, now_ms=now_ms, current_windows=current_windows, current_scopes=current_scopes
        ),
    }


def render_pulse_policy_evaluation_report(
    evaluation: dict[str, Any],
    *,
    generated_date: str,
    lookback_hours: int,
    config_context: dict[str, Any],
) -> str:
    recommendation = _recommendation(evaluation)
    lines = [
        "# Pulse 1h/4h Research Committee Evaluation",
        "",
        f"- generated_date: {generated_date}",
        f"- lookback_hours: {int(lookback_hours)}",
        f"- Recommendation: {recommendation}",
        "",
        "## Runtime Config Confirmation",
        "",
        f"- config_path: {_safe_path(config_context.get('config_path'))}",
        f"- workers_config_path: {_safe_path(config_context.get('workers_config_path'))}",
        f"- config_path_under_operator_home: {_bool_text(config_context.get('config_path_under_operator_home'))}",
        (
            "- workers_config_path_under_operator_home: "
            f"{_bool_text(config_context.get('workers_config_path_under_operator_home'))}"
        ),
        "",
        "## Policy Comparison",
        "",
    ]
    lines.extend(_section_lines("Radar", evaluation.get("radar", {})))
    lines.extend(_section_lines("Candidates", evaluation.get("candidates", {})))
    lines.extend(_section_lines("Runs", evaluation.get("runs", {})))
    lines.extend(_section_lines("Jobs", evaluation.get("jobs", {})))
    lines.extend(
        [
            "## Recommendation Rationale",
            "",
            _recommendation_rationale(evaluation, recommendation),
        ]
    )
    return "\n".join(lines).rstrip("\n")


def write_pulse_policy_evaluation_report(
    evaluation: dict[str, Any],
    *,
    output_dir: Path,
    generated_date: str,
    lookback_hours: int,
    config_context: dict[str, Any],
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"pulse-1h-4h-research-committee-evaluation-{generated_date}.md"
    path.write_text(
        render_pulse_policy_evaluation_report(
            evaluation,
            generated_date=generated_date,
            lookback_hours=lookback_hours,
            config_context=config_context,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _policy_summary(
    rows: list[dict[str, Any]],
    *,
    summarizer: Any,
    current_windows: tuple[str, ...] | None = None,
    current_scopes: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    resolved_current_windows = _policy_tuple(current_windows, fallback=DEFAULT_CURRENT_POLICY_WINDOWS)
    resolved_current_scopes = _policy_tuple(current_scopes, fallback=DEFAULT_CURRENT_POLICY_SCOPES)
    by_key = {
        key: summarizer(group_rows)
        for key, group_rows in sorted(_group_by_window_scope(rows).items(), key=lambda item: item[0])
    }
    return {
        "overall": summarizer(rows),
        "by_window_scope": by_key,
        "policy_comparison": {
            "current": summarizer(
                _select_policy_rows(
                    rows,
                    windows=resolved_current_windows,
                    scopes=resolved_current_scopes,
                )
            ),
            "proposed_primary": summarizer(
                _select_policy_rows(rows, windows=PROPOSED_PRIMARY_WINDOWS, scopes=PROPOSED_PRIMARY_SCOPES)
            ),
        },
    }


def _summarize_candidates_by_window_scope(
    rows: list[dict[str, Any]],
    *,
    current_windows: tuple[str, ...] | None = None,
    current_scopes: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    return _policy_summary(
        rows,
        summarizer=_summarize_candidate_rows,
        current_windows=current_windows,
        current_scopes=current_scopes,
    )


def _summarize_source_quality_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    source_quality = _source_quality(rows)
    return {
        "total_rows": len(rows),
        "unique_subjects": len(
            {str(row.get("subject_key") or row.get("candidate_id") or row.get("row_id")) for row in rows}
        ),
        "source_quality": source_quality,
        "scope_quality": _scope_quality(rows),
        "decision_counts": _count_values(rows, "decision"),
    }


def _summarize_candidate_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total_rows": len(rows),
        "unique_subjects": len({str(row.get("subject_key") or row.get("candidate_id")) for row in rows}),
        "source_quality": _source_quality(rows),
        "scope_quality": _scope_quality(rows),
        "display_status_counts": _count_values(rows, "display_status"),
        "evidence_status_counts": _count_values(rows, "evidence_status"),
        "decision_status_counts": _count_values(rows, "decision_status"),
        "pulse_status_counts": _count_values(rows, "pulse_status"),
        "public_display_count": sum(1 for row in rows if str(row.get("display_status") or "").startswith("display_")),
        "hidden_display_count": sum(1 for row in rows if str(row.get("display_status") or "").startswith("hidden_")),
    }


def _summarize_run_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    failure_count = sum(1 for row in rows if _is_failed_run(row))
    invalid_ref_count = sum(1 for row in rows if row.get("outcome") == "invalid_unknown_evidence_ref")
    backpressure_count = sum(1 for row in rows if _is_backpressure(row))
    return {
        "total_rows": total,
        "outcome_counts": _count_values(rows, "outcome"),
        "status_counts": _count_values(rows, "status"),
        "job_status_counts": _count_values(rows, "job_status"),
        "display_status_counts": _count_values(rows, "display_status"),
        "evidence_status_counts": _count_values(rows, "evidence_status"),
        "failure_count": failure_count,
        "failure_rate": _ratio(failure_count, total),
        "invalid_ref_count": invalid_ref_count,
        "invalid_ref_rate": _ratio(invalid_ref_count, total),
        "backpressure_count": backpressure_count,
        "backpressure_rate": _ratio(backpressure_count, total),
    }


def _summarize_job_rows(rows: list[dict[str, Any]], *, now_ms: int) -> dict[str, Any]:
    total = len(rows)
    no_run_count = sum(1 for row in rows if not row.get("latest_run_id"))
    backpressure_count = sum(1 for row in rows if _is_backpressure_job(row))
    due_pending_count = sum(
        1
        for row in rows
        if str(row.get("status") or "") in {"pending", "failed"} and _int(row.get("next_run_at_ms")) <= int(now_ms)
    )
    return {
        "total_rows": total,
        "job_status_counts": _count_values(rows, "status"),
        "latest_run_outcome_counts": _count_values(rows, "latest_run_outcome"),
        "no_run_count": no_run_count,
        "no_run_rate": _ratio(no_run_count, total),
        "backpressure_count": backpressure_count,
        "backpressure_rate": _ratio(backpressure_count, total),
        "due_pending_count": due_pending_count,
        "due_pending_rate": _ratio(due_pending_count, total),
    }


def _source_quality(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    author_counts = [_independent_author_count(row) for row in rows]
    single_author = sum(1 for value in author_counts if value == 1)
    ge2 = sum(1 for value in author_counts if value >= 2)
    ge3 = sum(1 for value in author_counts if value >= 3)
    unknown = sum(1 for value in author_counts if value <= 0)
    watched = sum(1 for row in rows if _watched_confirmation(row))
    return {
        "author_count_buckets": {
            "single": single_author,
            "ge2": ge2,
            "ge3": ge3,
            "unknown": unknown,
        },
        "single_author_ratio": _ratio(single_author, total),
        "ge2_author_ratio": _ratio(ge2, total),
        "ge3_author_ratio": _ratio(ge3, total),
        "watched_confirmation_count": watched,
        "watched_confirmation_ratio": _ratio(watched, total),
        "top_author_share_buckets": _top_author_share_buckets(rows),
    }


def _scope_quality(rows: list[dict[str, Any]]) -> dict[str, Any]:
    matched = sum(1 for row in rows if str(row.get("scope") or "") in {"matched", "watched"})
    watched_only = sum(1 for row in rows if str(row.get("scope") or "") == "all" and _watched_confirmation(row))
    return {
        "all_scope_count": sum(1 for row in rows if str(row.get("scope") or "") == "all"),
        "matched_only_count": matched,
        "watched_only_count": watched_only,
        "watched_to_matched_ratio": _ratio(watched_only, matched),
    }


def _top_author_share_buckets(rows: list[dict[str, Any]]) -> dict[str, int]:
    buckets = {"lt_50": 0, "50_65": 0, "65_80": 0, "ge_80": 0, "unknown": 0}
    for row in rows:
        value = _top_author_share(row)
        if value is None:
            buckets["unknown"] += 1
        elif value < 0.5:
            buckets["lt_50"] += 1
        elif value < 0.65:
            buckets["50_65"] += 1
        elif value < 0.8:
            buckets["65_80"] += 1
        else:
            buckets["ge_80"] += 1
    return buckets


def _group_by_window_scope(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = f"{row.get('window') or 'unknown'}/{row.get('scope') or 'unknown'}"
        groups.setdefault(key, []).append(row)
    return groups


def _computed_at_bounds(rows: list[dict[str, Any]]) -> dict[str, int | None]:
    values = [_int_or_none(row.get("computed_at_ms")) for row in rows]
    present = [value for value in values if value is not None]
    if not present:
        return {"min": None, "max": None, "latest": None}
    latest = max(present)
    return {"min": min(present), "max": latest, "latest": latest}


def _select_policy_rows(
    rows: list[dict[str, Any]], *, windows: tuple[str, ...], scopes: tuple[str, ...]
) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if str(row.get("window") or "") in set(windows) and str(row.get("scope") or "") in set(scopes)
    ]


def _policy_tuple(value: tuple[str, ...] | None, *, fallback: tuple[str, ...]) -> tuple[str, ...]:
    normalized = tuple(str(item).strip() for item in (value or ()) if str(item).strip())
    return normalized or fallback


def _independent_author_count(row: dict[str, Any]) -> int:
    snapshot = _snapshot(row)
    social_heat = _family_facts(snapshot, "social_heat")
    propagation = _family_facts(snapshot, "social_propagation")
    return max(_int(social_heat.get("unique_authors")), _int(propagation.get("independent_authors")))


def _top_author_share(row: dict[str, Any]) -> float | None:
    propagation = _family_facts(_snapshot(row), "social_propagation")
    value = propagation.get("top_author_share")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _watched_confirmation(row: dict[str, Any]) -> bool:
    snapshot = _snapshot(row)
    social_heat = _family_facts(snapshot, "social_heat")
    propagation = _family_facts(snapshot, "social_propagation")
    return _int(social_heat.get("watched_mentions")) > 0 or _int(propagation.get("watched_author_count")) > 0


def _snapshot(row: dict[str, Any]) -> dict[str, Any]:
    value = row.get("factor_snapshot_json")
    return value if isinstance(value, dict) else {}


def _family_facts(snapshot: dict[str, Any], family: str) -> dict[str, Any]:
    families = snapshot.get("families") if isinstance(snapshot.get("families"), dict) else {}
    block = families.get(family) if isinstance(families.get(family), dict) else {}
    facts = block.get("facts") if isinstance(block.get("facts"), dict) else {}
    return facts


def _count_values(rows: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts = Counter(str(row.get(field) or "unknown") for row in rows)
    return dict(sorted(counts.items()))


def _is_failed_run(row: dict[str, Any]) -> bool:
    return str(row.get("status") or "") == "failed" or str(row.get("outcome") or "") in FAILURE_OUTCOMES


def _is_backpressure(row: dict[str, Any]) -> bool:
    outcome = str(row.get("outcome") or "")
    status = str(row.get("job_status") or "")
    return "backpressure" in outcome or status in BACKPRESSURE_JOB_STATUSES - {"done"}


def _is_backpressure_job(row: dict[str, Any]) -> bool:
    status = str(row.get("status") or "")
    return status in BACKPRESSURE_JOB_STATUSES


def _recommendation(evaluation: dict[str, Any]) -> str:
    radar = evaluation.get("radar", {}).get("policy_comparison", {}).get("proposed_primary", {})
    runs = evaluation.get("runs", {}).get("policy_comparison", {}).get("proposed_primary", {})
    jobs = evaluation.get("jobs", {}).get("policy_comparison", {}).get("proposed_primary", {})
    total = int(radar.get("total_rows") or 0)
    source_quality = radar.get("source_quality") if isinstance(radar.get("source_quality"), dict) else {}
    if (
        total <= 0
        or float(runs.get("failure_rate") or 0.0) >= 0.5
        or float(runs.get("invalid_ref_rate") or 0.0) >= 0.2
        or float(jobs.get("backpressure_rate") or 0.0) >= 0.5
    ):
        return "stop"
    if float(source_quality.get("single_author_ratio") or 0.0) > 0.5 or float(
        source_quality.get("ge3_author_ratio") or 0.0
    ) < 0.3:
        return "revise thresholds"
    return "ship"


def _recommendation_rationale(evaluation: dict[str, Any], recommendation: str) -> str:
    proposed_radar = evaluation.get("radar", {}).get("policy_comparison", {}).get("proposed_primary", {})
    proposed_runs = evaluation.get("runs", {}).get("policy_comparison", {}).get("proposed_primary", {})
    proposed_jobs = evaluation.get("jobs", {}).get("policy_comparison", {}).get("proposed_primary", {})
    quality = proposed_radar.get("source_quality") if isinstance(proposed_radar.get("source_quality"), dict) else {}
    return (
        f"{recommendation} based on proposed 1h/all and 4h/all radar latest-snapshot sample size "
        f"{proposed_radar.get('total_rows', 0)}, ge3 author ratio {float(quality.get('ge3_author_ratio') or 0.0):.2f}, "
        f"single-author ratio {float(quality.get('single_author_ratio') or 0.0):.2f}, "
        f"run failure rate {float(proposed_runs.get('failure_rate') or 0.0):.2f}, and "
        f"invalid-ref rate {float(proposed_runs.get('invalid_ref_rate') or 0.0):.2f}, "
        f"job backpressure rate {float(proposed_jobs.get('backpressure_rate') or 0.0):.2f}."
    )


def _section_lines(title: str, summary: dict[str, Any]) -> list[str]:
    comparison = summary.get("policy_comparison") if isinstance(summary.get("policy_comparison"), dict) else {}
    overall = summary.get("overall") if isinstance(summary.get("overall"), dict) else {}
    current = comparison.get("current") if isinstance(comparison.get("current"), dict) else {}
    proposed = comparison.get("proposed_primary") if isinstance(comparison.get("proposed_primary"), dict) else {}
    lines = [f"### {title}", ""]
    if summary.get("sample_kind"):
        lines.append(
            f"- sample_kind={summary.get('sample_kind')}, "
            f"computed_at_ms={_format_counts(summary.get('computed_at_ms'))}"
        )
    lines.extend(_compact_metric_lines("overall", overall))
    lines.extend(_compact_metric_lines("current_policy", current))
    lines.extend(_compact_metric_lines("proposed_primary", proposed))
    lines.append("")
    return lines


def _compact_metric_lines(label: str, payload: dict[str, Any]) -> list[str]:
    quality = payload.get("source_quality") if isinstance(payload.get("source_quality"), dict) else {}
    scope = payload.get("scope_quality") if isinstance(payload.get("scope_quality"), dict) else {}
    return [
        (
            f"- {label}: total={int(payload.get('total_rows') or 0)}, "
            f"single_author_ratio={float(quality.get('single_author_ratio') or 0.0):.2f}, "
            f"ge3_author_ratio={float(quality.get('ge3_author_ratio') or 0.0):.2f}, "
            f"top_author_share_buckets={_format_counts(quality.get('top_author_share_buckets'))}, "
            f"watched_to_matched_ratio={float(scope.get('watched_to_matched_ratio') or 0.0):.2f}, "
            f"watched_only={int(scope.get('watched_only_count') or 0)}, "
            f"matched_only={int(scope.get('matched_only_count') or 0)}, "
            f"failures={int(payload.get('failure_count') or 0)}, "
            f"failure_rate={float(payload.get('failure_rate') or 0.0):.2f}, "
            f"invalid_refs={int(payload.get('invalid_ref_count') or 0)}, "
            f"invalid_ref_rate={float(payload.get('invalid_ref_rate') or 0.0):.2f}, "
            f"backpressure={int(payload.get('backpressure_count') or 0)}, "
            f"backpressure_rate={float(payload.get('backpressure_rate') or 0.0):.2f}, "
            f"display_status_counts={_format_counts(payload.get('display_status_counts'))}, "
            f"outcome_counts={_format_counts(payload.get('outcome_counts'))}, "
            f"status_counts={_format_counts(payload.get('status_counts') or payload.get('job_status_counts'))}, "
            f"no_run_count={int(payload.get('no_run_count') or 0)}, "
            f"due_pending_count={int(payload.get('due_pending_count') or 0)}"
        )
    ]


def _format_counts(value: Any) -> str:
    if not isinstance(value, dict) or not value:
        return "{}"
    return "{" + ", ".join(f"{key}:{value[key]}" for key in sorted(value)) + "}"


def _safe_path(value: Any) -> str:
    if value is None:
        return "unknown"
    return str(value)


def _bool_text(value: Any) -> str:
    return "true" if bool(value) else "false"


def _since_ms(*, now_ms: int, lookback_hours: int) -> int:
    return int(now_ms) - max(1, int(lookback_hours)) * 60 * 60 * 1000


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return float(numerator) / float(denominator)


def today_utc_date() -> str:
    return datetime.now(UTC).date().isoformat()


__all__ = [
    "build_pulse_policy_evaluation",
    "fetch_candidate_rows",
    "fetch_job_rows",
    "fetch_radar_rows",
    "fetch_run_rows",
    "render_pulse_policy_evaluation_report",
    "summarize_by_window_scope",
    "summarize_by_window_scope_and_outcome",
    "summarize_candidate_policy_rows",
    "summarize_job_policy_rows",
    "summarize_pulse_run_rows",
    "summarize_radar_policy_rows",
    "today_utc_date",
    "write_pulse_policy_evaluation_report",
]
