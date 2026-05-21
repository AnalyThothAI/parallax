from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEEPSEEK_MODEL_MARKERS = ("deepseek",)
PUBLIC_DISPLAY_STATUSES = ("display_trade_candidate", "display_token_watch")
DEFAULT_DRY_RUN_POLICY = {"skip_deepseek_display_status_prefixes": ("hidden_",)}


def build_signal_pulse_agent_cost_report(
    conn: Any,
    *,
    now_ms: int,
    lookback_hours: int,
    dry_run_policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    since_ms = _since_ms(now_ms=now_ms, lookback_hours=lookback_hours)
    run_rows = _fetch_run_rows(conn, since_ms=since_ms, now_ms=now_ms)
    step_rows = _fetch_step_rows(conn, since_ms=since_ms, now_ms=now_ms)
    job_rows = _fetch_optional_rows(conn, _JOBS_SQL, (since_ms, int(now_ms)))
    eval_case_rows = _fetch_optional_rows(conn, _EVAL_CASES_SQL, (since_ms, int(now_ms)))
    eval_result_rows = _fetch_optional_rows(conn, _EVAL_RESULTS_SQL, (since_ms, int(now_ms)))
    report = summarize_signal_pulse_agent_cost_rows(
        run_rows,
        step_rows,
        now_ms=now_ms,
        lookback_hours=lookback_hours,
        dry_run_policy=dry_run_policy,
    )
    report["jobs"] = {"total": len(job_rows), "status_counts": _counter_dict(_count_values(job_rows, "status"))}
    report["eval"] = {
        "cases": len(eval_case_rows),
        "results": len(eval_result_rows),
        "result_status_counts": _counter_dict(_count_values(eval_result_rows, "status")),
    }
    return report


def summarize_signal_pulse_agent_cost_rows(
    run_rows: list[Mapping[str, Any]],
    step_rows: list[Mapping[str, Any]],
    *,
    now_ms: int,
    lookback_hours: int,
    dry_run_policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    since_ms = _since_ms(now_ms=now_ms, lookback_hours=lookback_hours)
    runs_by_id = {str(row.get("run_id") or ""): row for row in run_rows}
    steps_with_runs = [dict(step, _run=runs_by_id.get(str(step.get("run_id") or ""), {})) for step in step_rows]
    deepseek_steps = [step for step in steps_with_runs if _is_deepseek_model(step.get("model"))]
    deepseek_tokens_before = sum(_usage_tokens(step.get("usage_json")) for step in deepseek_steps)
    hidden_invalid_tokens = sum(
        _usage_tokens(step.get("usage_json"))
        for step in deepseek_steps
        if _display_status(step) == "hidden_invalid_output"
    )
    public_display = Counter(
        status for row in run_rows if (status := str(row.get("display_status") or "")) in PUBLIC_DISPLAY_STATUSES
    )
    runs = {
        "total": len(run_rows),
        "backpressure_circuit_open": sum(1 for row in run_rows if _is_circuit_open_run(row)),
        "hidden_invalid_output": sum(
            1 for row in run_rows if str(row.get("display_status") or "") == "hidden_invalid_output"
        ),
    }
    after_tokens = sum(
        _usage_tokens(step.get("usage_json"))
        for step in deepseek_steps
        if not _dry_run_skips_deepseek(step, dry_run_policy=dry_run_policy)
    )
    steps_by_stage_model_status = _steps_by_stage_model_status(step_rows)
    tokens_by_display_status = _tokens_by_display_status(steps_with_runs)
    public_candidate_delta = {
        "display_trade_candidate": int(public_display.get("display_trade_candidate", 0)),
        "display_token_watch": int(public_display.get("display_token_watch", 0)),
    }
    return {
        "window": {"lookback_hours": int(lookback_hours), "since_ms": since_ms, "now_ms": int(now_ms)},
        "runs": runs,
        "deepseek": {
            "steps": len(deepseek_steps),
            "total_tokens": deepseek_tokens_before,
            "stage_counts": _counter_dict(_count_values(deepseek_steps, "stage")),
        },
        "hidden_invalid_output": {"runs": runs["hidden_invalid_output"], "total_tokens": hidden_invalid_tokens},
        "public_display": public_candidate_delta.copy(),
        "backpressure": {"circuit_open_runs": runs["backpressure_circuit_open"]},
        "steps_by_stage_model_status": steps_by_stage_model_status,
        "tokens_by_display_status": tokens_by_display_status,
        "duplicate_fingerprints": _duplicate_fingerprints(run_rows),
        "public_candidate_delta": public_candidate_delta,
        "predicted_savings": {
            "deepseek_tokens_before": deepseek_tokens_before,
            "deepseek_tokens_after": after_tokens,
            "deepseek_token_reduction_ratio": _ratio(deepseek_tokens_before - after_tokens, deepseek_tokens_before),
        },
    }


def render_signal_pulse_agent_cost_report(
    report: Mapping[str, Any],
    *,
    generated_date: str,
    config_context: Mapping[str, Any],
    dry_run: bool,
) -> str:
    window = _mapping(report.get("window"))
    runs = _mapping(report.get("runs"))
    deepseek = _mapping(report.get("deepseek"))
    predicted = _mapping(report.get("predicted_savings"))
    duplicates = _mapping(report.get("duplicate_fingerprints"))
    public_delta = _mapping(report.get("public_candidate_delta"))
    lines = [
        "# Signal Pulse Agent Cost Guard Read-only Report",
        "",
        f"- generated_date: {generated_date}",
        f"- lookback_hours: {_int(window.get('lookback_hours'))}",
        f"- dry_run: {_bool_text(dry_run)}",
        f"- since_ms: {_int(window.get('since_ms'))}",
        f"- now_ms: {_int(window.get('now_ms'))}",
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
        "## Summary",
        "",
        f"- runs_total: {_int(runs.get('total'))}",
        f"- backpressure_circuit_open_runs: {_int(runs.get('backpressure_circuit_open'))}",
        f"- hidden_invalid_output_runs: {_int(runs.get('hidden_invalid_output'))}",
        f"- deepseek_total_tokens: {_int(deepseek.get('total_tokens'))}",
        f"- hidden_invalid_output_tokens: {_int(_mapping(report.get('hidden_invalid_output')).get('total_tokens'))}",
        f"- predicted_deepseek_tokens_after: {_int(predicted.get('deepseek_tokens_after'))}",
        f"- predicted_deepseek_reduction_ratio: {float(predicted.get('deepseek_token_reduction_ratio') or 0.0):.4f}",
        f"- duplicate_success_fingerprint_groups: {_int(duplicates.get('duplicate_success_fingerprint_groups'))}",
        f"- extra_success_runs_same_fingerprint: {_int(duplicates.get('extra_success_runs_same_fingerprint'))}",
        f"- display_trade_candidate: {_int(public_delta.get('display_trade_candidate'))}",
        f"- display_token_watch: {_int(public_delta.get('display_token_watch'))}",
        "",
        "## Steps By Stage Model Status",
        "",
    ]
    lines.extend(
        _table_lines(report.get("steps_by_stage_model_status"), ("stage", "model", "status", "steps", "tokens"))
    )
    lines.extend(["", "## Tokens By Display Status", ""])
    lines.extend(_table_lines(report.get("tokens_by_display_status"), ("display_status", "steps", "tokens")))
    return "\n".join(lines).rstrip("\n")


def write_signal_pulse_agent_cost_report(
    report: Mapping[str, Any],
    *,
    output_dir: Path,
    generated_date: str,
    config_context: Mapping[str, Any],
    dry_run: bool,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"signal-pulse-agent-cost-guard-{generated_date}.md"
    path.write_text(
        render_signal_pulse_agent_cost_report(
            report,
            generated_date=generated_date,
            config_context=config_context,
            dry_run=dry_run,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _fetch_run_rows(conn: Any, *, since_ms: int, now_ms: int) -> list[dict[str, Any]]:
    rows = conn.execute(_RUNS_SQL, (since_ms, int(now_ms))).fetchall()
    return [dict(row) for row in rows]


def _fetch_step_rows(conn: Any, *, since_ms: int, now_ms: int) -> list[dict[str, Any]]:
    rows = conn.execute(_STEPS_SQL, (since_ms, int(now_ms))).fetchall()
    return [dict(row) for row in rows]


def _fetch_optional_rows(conn: Any, sql: str, params: tuple[int, int]) -> list[dict[str, Any]]:
    try:
        rows = conn.execute(sql, params).fetchall()
    except Exception as exc:
        if _missing_optional_relation(exc):
            return []
        raise
    return [dict(row) for row in rows]


def _steps_by_stage_model_status(step_rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for step in step_rows:
        key = (
            str(step.get("stage") or "unknown"),
            str(step.get("model") or "unknown"),
            str(step.get("status") or "unknown"),
        )
        bucket = grouped.setdefault(key, {"stage": key[0], "model": key[1], "status": key[2], "steps": 0, "tokens": 0})
        bucket["steps"] += 1
        bucket["tokens"] += _usage_tokens(step.get("usage_json"))
    return sorted(grouped.values(), key=lambda row: (row["stage"], row["model"], row["status"]))


def _tokens_by_display_status(steps: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for step in steps:
        status = _display_status(step)
        bucket = grouped.setdefault(status, {"display_status": status, "steps": 0, "tokens": 0})
        bucket["steps"] += 1
        bucket["tokens"] += _usage_tokens(step.get("usage_json"))
    return sorted(grouped.values(), key=lambda row: row["display_status"])


def _duplicate_fingerprints(run_rows: list[Mapping[str, Any]]) -> dict[str, int]:
    groups: defaultdict[tuple[str, str, str, str], int] = defaultdict(int)
    for row in run_rows:
        if not _is_success_run(row):
            continue
        fingerprint = (
            str(row.get("candidate_id") or ""),
            str(row.get("input_hash") or ""),
            str(row.get("runtime_hash") or ""),
            str(row.get("evidence_packet_hash") or ""),
        )
        if all(fingerprint):
            groups[fingerprint] += 1
    duplicate_sizes = [size for size in groups.values() if size > 1]
    return {
        "duplicate_success_fingerprint_groups": len(duplicate_sizes),
        "extra_success_runs_same_fingerprint": sum(size - 1 for size in duplicate_sizes),
    }


def _dry_run_skips_deepseek(step: Mapping[str, Any], *, dry_run_policy: Mapping[str, Any] | None) -> bool:
    policy = dict(DEFAULT_DRY_RUN_POLICY if dry_run_policy is None else dry_run_policy)
    statuses = set(str(value) for value in policy.get("skip_deepseek_display_statuses") or ())
    prefixes = tuple(str(value) for value in policy.get("skip_deepseek_display_status_prefixes") or ())
    display_status = _display_status(step)
    return display_status in statuses or any(display_status.startswith(prefix) for prefix in prefixes)


def _display_status(step: Mapping[str, Any]) -> str:
    run = _mapping(step.get("_run"))
    return str(run.get("display_status") or "unknown")


def _usage_tokens(value: Any) -> int:
    usage = _mapping(_decode_json(value))
    explicit = _int(usage.get("total_tokens"))
    if explicit:
        return explicit
    return sum(
        _int(usage.get(key))
        for key in ("input_tokens", "output_tokens", "cached_input_tokens", "reasoning_tokens")
    )


def _is_deepseek_model(value: Any) -> bool:
    model = str(value or "").lower()
    return any(marker in model for marker in DEEPSEEK_MODEL_MARKERS)


def _is_circuit_open_run(row: Mapping[str, Any]) -> bool:
    outcome = str(row.get("outcome") or "").lower()
    error = str(row.get("error") or "").lower()
    return outcome in {"backpressure_circuit_open", "provider_circuit_open"} or "circuit_open" in error


def _is_success_run(row: Mapping[str, Any]) -> bool:
    status = str(row.get("status") or "").lower()
    outcome = str(row.get("outcome") or "").lower()
    return status in {"done", "ok", "succeeded", "completed"} and outcome == "completed"


def _count_values(rows: list[Mapping[str, Any]], key: str) -> Counter[str]:
    return Counter(str(row.get(key) or "unknown") for row in rows)


def _counter_dict(counter: Counter[str]) -> dict[str, int]:
    return {key: int(counter[key]) for key in sorted(counter)}


def _table_lines(value: Any, columns: tuple[str, ...]) -> list[str]:
    rows = value if isinstance(value, list) else []
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join("---" for _ in columns) + " |"]
    for row in rows:
        payload = _mapping(row)
        lines.append("| " + " | ".join(str(payload.get(column, "")) for column in columns) + " |")
    if not rows:
        lines.append("| " + " | ".join("0" if column in {"steps", "tokens"} else "none" for column in columns) + " |")
    return lines


def _mapping(value: Any) -> dict[str, Any]:
    decoded = _decode_json(value)
    return dict(decoded) if isinstance(decoded, Mapping) else {}


def _decode_json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _missing_optional_relation(exc: Exception) -> bool:
    text = str(exc).lower()
    return "does not exist" in text and any(
        relation in text for relation in ("pulse_agent_jobs", "pulse_agent_eval_cases", "pulse_agent_eval_results")
    )


def _safe_path(value: Any) -> str:
    return "unknown" if value is None else str(value)


def _bool_text(value: Any) -> str:
    return "true" if bool(value) else "false"


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(float(numerator) / float(denominator), 4)


def _since_ms(*, now_ms: int, lookback_hours: int) -> int:
    return int(now_ms) - max(1, int(lookback_hours)) * 60 * 60 * 1000


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def report_generated_date(now: datetime | None = None) -> str:
    return (now or datetime.now(tz=UTC)).date().isoformat()


_RUNS_SQL = """
SELECT
  run.run_id,
  run.job_id,
  run.candidate_id,
  run.provider,
  run.model,
  run.status,
  run.outcome,
  run.decision_route,
  run.decision_stage_count,
  run.evidence_status,
  run.display_status,
  run.input_hash,
  run.runtime_hash,
  run.evidence_packet_hash,
  run.usage_json,
  run.error,
  run.started_at_ms,
  run.finished_at_ms
FROM pulse_agent_runs AS run
WHERE run.started_at_ms >= %s
  AND run.started_at_ms <= %s
ORDER BY run.started_at_ms ASC, run.run_id ASC
"""

_STEPS_SQL = """
SELECT
  step.step_id,
  step.run_id,
  step.stage,
  step.route,
  step.attempt_index,
  step.provider,
  step.model,
  step.status,
  step.usage_json,
  step.latency_ms,
  step.error,
  step.started_at_ms,
  step.finished_at_ms
FROM pulse_agent_run_steps AS step
WHERE step.started_at_ms >= %s
  AND step.started_at_ms <= %s
ORDER BY step.started_at_ms ASC, step.run_id ASC, step.stage ASC, step.attempt_index ASC
"""

_JOBS_SQL = """
SELECT job_id, candidate_id, status, attempt_count, max_attempts, last_error, created_at_ms, updated_at_ms
FROM pulse_agent_jobs
WHERE updated_at_ms >= %s
  AND updated_at_ms <= %s
ORDER BY updated_at_ms ASC, job_id ASC
"""

_EVAL_CASES_SQL = """
SELECT eval_case_id, source_run_id, runtime_hash, eval_type, route, recommendation, status, created_at_ms
FROM pulse_agent_eval_cases
WHERE created_at_ms >= %s
  AND created_at_ms <= %s
ORDER BY created_at_ms ASC, eval_case_id ASC
"""

_EVAL_RESULTS_SQL = """
SELECT eval_result_id, eval_case_id, runtime_hash, status, created_at_ms
FROM pulse_agent_eval_results
WHERE created_at_ms >= %s
  AND created_at_ms <= %s
ORDER BY created_at_ms ASC, eval_result_id ASC
"""

__all__ = [
    "build_signal_pulse_agent_cost_report",
    "render_signal_pulse_agent_cost_report",
    "report_generated_date",
    "summarize_signal_pulse_agent_cost_rows",
    "write_signal_pulse_agent_cost_report",
]
