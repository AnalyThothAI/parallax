from __future__ import annotations

from typing import Any

import pytest

from parallax.domains.pulse_lab.queries.pulse_agent_cost_report import (
    build_signal_pulse_agent_cost_report,
    summarize_signal_pulse_agent_cost_rows,
)

NOW_MS = 1_800_000


def test_summarize_signal_pulse_agent_cost_rows_counts_cost_leak_signals() -> None:
    run_rows = [
        _run_row(
            "run-public",
            display_status="display_token_watch",
            outcome="completed",
            evidence_packet_hash="hash-public",
        ),
        _run_row(
            "run-hidden",
            display_status="hidden_invalid_output",
            outcome="invalid_schema",
            evidence_packet_hash="hash-hidden",
        ),
        _run_row(
            "run-backpressure-1",
            display_status="hidden_insufficient_evidence",
            outcome="backpressure_circuit_open",
        ),
        _run_row(
            "run-backpressure-2",
            display_status="hidden_insufficient_evidence",
            outcome="provider_circuit_open",
        ),
        _run_row(
            "run-duplicate-a",
            display_status="hidden_abstain",
            status="done",
            outcome="completed",
            input_hash="same-input",
            runtime_hash="same-runtime",
            evidence_packet_hash="same-evidence",
        ),
        _run_row(
            "run-duplicate-b",
            display_status="hidden_abstain",
            status="done",
            outcome="completed",
            input_hash="same-input",
            runtime_hash="same-runtime",
            evidence_packet_hash="same-evidence",
        ),
    ]
    step_rows = [
        _step_row(
            "run-public",
            "pulse_decision",
            model="deepseek-v4-flash",
            usage_json={"input_tokens": 100, "output_tokens": 100},
        ),
        _step_row(
            "run-hidden",
            "pulse_decision",
            model="deepseek-v4-flash",
            usage_json={"input_tokens": 300, "output_tokens": 500},
        ),
    ]

    report = summarize_signal_pulse_agent_cost_rows(
        run_rows,
        step_rows,
        now_ms=NOW_MS,
        lookback_hours=24,
        dry_run_policy={"skip_decision_stage_display_status_prefixes": ["hidden_"]},
    )

    assert report["decision_stage"]["total_tokens"] == 1_000
    assert report["hidden_invalid_output"]["total_tokens"] == 800
    assert report["public_display"]["display_token_watch"] == 1
    assert report["backpressure"]["circuit_open_runs"] == 2
    assert report["duplicate_fingerprints"] == {
        "duplicate_success_fingerprint_groups": 1,
        "extra_success_runs_same_fingerprint": 1,
    }
    assert report["predicted_savings"] == {
        "decision_stage_tokens_before": 1_000,
        "decision_stage_tokens_after": 200,
        "decision_stage_token_reduction_ratio": 0.8,
    }


def test_build_signal_pulse_agent_cost_report_uses_read_only_selects() -> None:
    conn = FakeConn(
        run_rows=[_run_row("run-public", display_status="display_trade_candidate")],
        step_rows=[
            _step_row(
                "run-public",
                "pulse_decision",
                model="deepseek-v4-flash",
                usage_json={"total_tokens": 42},
            )
        ],
    )

    report = build_signal_pulse_agent_cost_report(conn, now_ms=NOW_MS, lookback_hours=4, dry_run_policy={})

    assert report["window"]["lookback_hours"] == 4
    assert report["window"]["since_ms"] == NOW_MS - (4 * 60 * 60 * 1000)
    assert report["decision_stage"]["total_tokens"] == 42
    assert report["public_candidate_delta"]["display_trade_candidate"] == 1
    assert conn.executed_sql
    assert all(sql.strip().split(maxsplit=1)[0].upper() in {"SELECT", "WITH"} for sql in conn.executed_sql)
    assert any("FROM pulse_agent_runs" in sql for sql in conn.executed_sql)
    assert any("FROM pulse_agent_run_steps" in sql for sql in conn.executed_sql)


def test_build_signal_pulse_agent_cost_report_rejects_malformed_lookback_before_sql() -> None:
    conn = FakeConn(run_rows=[], step_rows=[])

    with pytest.raises(ValueError, match="pulse_agent_cost_report_lookback_hours_required"):
        build_signal_pulse_agent_cost_report(conn, now_ms=NOW_MS, lookback_hours=0, dry_run_policy={})

    assert conn.executed_sql == []


class FakeCursor:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self._rows)


class FakeConn:
    def __init__(self, *, run_rows: list[dict[str, Any]], step_rows: list[dict[str, Any]]) -> None:
        self._rows = {
            "pulse_agent_runs": run_rows,
            "pulse_agent_run_steps": step_rows,
            "pulse_agent_jobs": [],
            "pulse_agent_eval_cases": [],
            "pulse_agent_eval_results": [],
        }
        self.executed_sql: list[str] = []

    def execute(self, sql: str, params: tuple[object, ...]) -> FakeCursor:
        self.executed_sql.append(sql)
        assert params
        assert sql.strip().split(maxsplit=1)[0].upper() in {"SELECT", "WITH"}
        for table, rows in self._rows.items():
            if table in sql:
                return FakeCursor(rows)
        raise AssertionError(f"unexpected SQL: {sql}")


def _run_row(
    run_id: str,
    *,
    display_status: str,
    status: str = "done",
    outcome: str = "completed",
    candidate_id: str = "candidate-1",
    input_hash: str | None = None,
    runtime_hash: str | None = None,
    evidence_packet_hash: str | None = None,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "job_id": f"job-{run_id}",
        "candidate_id": candidate_id,
        "provider": "litellm",
        "model": "deepseek-v4-flash",
        "status": status,
        "outcome": outcome,
        "display_status": display_status,
        "input_hash": input_hash or f"input-{run_id}",
        "runtime_hash": runtime_hash or f"runtime-{run_id}",
        "evidence_packet_hash": evidence_packet_hash,
        "usage_json": {},
        "started_at_ms": NOW_MS - 1_000,
        "finished_at_ms": NOW_MS,
    }


def _step_row(
    run_id: str,
    stage: str,
    *,
    model: str,
    usage_json: dict[str, Any],
    status: str = "ok",
) -> dict[str, Any]:
    return {
        "step_id": f"step-{run_id}-{stage}",
        "run_id": run_id,
        "stage": stage,
        "route": "cex",
        "provider": "litellm",
        "model": model,
        "status": status,
        "usage_json": usage_json,
        "started_at_ms": NOW_MS - 1_000,
        "finished_at_ms": NOW_MS,
    }
