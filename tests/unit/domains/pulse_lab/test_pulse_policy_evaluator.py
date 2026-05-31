from __future__ import annotations

import pytest

from parallax.domains.pulse_lab.queries.pulse_policy_evaluator import (
    build_pulse_policy_evaluation,
    fetch_radar_rows,
    render_pulse_policy_evaluation_report,
    summarize_candidate_policy_rows,
    summarize_job_policy_rows,
    summarize_pulse_run_rows,
    summarize_radar_policy_rows,
)


def test_summarize_radar_policy_rows_compares_current_and_proposed_author_quality() -> None:
    rows = [
        _radar_row("5m", "all", authors=1, top_share=1.0, watched_mentions=0, computed_at_ms=100),
        _radar_row("5m", "all", authors=2, top_share=0.5, watched_mentions=1, computed_at_ms=100),
        _radar_row("5m", "all", authors=3, top_share=0.4, watched_mentions=0, computed_at_ms=100),
        _radar_row("1h", "all", authors=3, top_share=0.34, watched_mentions=1, computed_at_ms=200),
        _radar_row("1h", "all", authors=1, top_share=0.9, watched_mentions=0, computed_at_ms=200),
        _radar_row("4h", "all", authors=4, top_share=0.25, watched_mentions=0, computed_at_ms=300),
        _radar_row("4h", "matched", authors=2, top_share=0.5, watched_mentions=2, computed_at_ms=400),
        _radar_row("24h", "matched", authors=5, top_share=0.2, watched_mentions=3, computed_at_ms=500),
    ]

    summary = summarize_radar_policy_rows(rows)

    assert summary["sample_kind"] == "latest_snapshot"
    assert summary["computed_at_ms"] == {"min": 100, "max": 500, "latest": 500}
    current = summary["by_window_scope"]["5m/all"]
    assert current["total_rows"] == 3
    assert current["source_quality"]["single_author_ratio"] == pytest.approx(1 / 3)
    assert current["source_quality"]["author_count_buckets"]["ge2"] == 2
    assert current["source_quality"]["author_count_buckets"]["ge3"] == 1
    assert current["source_quality"]["watched_confirmation_count"] == 1
    assert current["source_quality"]["top_author_share_buckets"] == {
        "lt_50": 1,
        "50_65": 1,
        "65_80": 0,
        "ge_80": 1,
        "unknown": 0,
    }

    proposed_1h = summary["by_window_scope"]["1h/all"]
    assert proposed_1h["source_quality"]["single_author_ratio"] == pytest.approx(0.5)
    assert proposed_1h["source_quality"]["author_count_buckets"]["ge3"] == 1
    assert proposed_1h["source_quality"]["watched_confirmation_count"] == 1

    proposed = summary["policy_comparison"]["proposed_primary"]
    assert proposed["total_rows"] == 3
    assert proposed["source_quality"]["author_count_buckets"]["ge3"] == 2
    assert proposed["source_quality"]["watched_confirmation_count"] == 1
    assert proposed["scope_quality"]["matched_only_count"] == 0
    assert proposed["scope_quality"]["watched_only_count"] == 1

    all_rows = summary["overall"]
    assert all_rows["scope_quality"]["matched_only_count"] == 2
    assert all_rows["scope_quality"]["watched_only_count"] == 2

    current_policy = summary["policy_comparison"]["current"]
    assert current_policy["total_rows"] == len(rows)
    assert current_policy["source_quality"]["author_count_buckets"]["ge3"] == 4


def test_summarize_candidate_and_run_rows_include_display_statuses_outcomes_and_backpressure() -> None:
    candidate_rows = [
        _candidate_row("1h", "all", "display_trade_candidate", evidence_status="complete"),
        _candidate_row("1h", "all", "hidden_hold_publish", evidence_status="partial"),
        _candidate_row("4h", "all", "hidden_insufficient_evidence", evidence_status="insufficient"),
        _candidate_row("5m", "all", "display_token_watch", evidence_status="complete"),
    ]
    run_rows = [
        _run_row("1h", "all", outcome="completed", status="completed", job_status="done"),
        _run_row("1h", "all", outcome="invalid_unknown_evidence_ref", status="failed", job_status="failed"),
        _run_row("4h", "all", outcome="provider_rate_limited", status="failed", job_status="pending"),
        _run_row("4h", "all", outcome="backpressure_circuit_open", status="skipped", job_status="done"),
        _run_row("5m", "all", outcome="completed", status="completed", job_status="running"),
    ]

    candidates = summarize_candidate_policy_rows(candidate_rows)
    runs = summarize_pulse_run_rows(run_rows)

    candidate_1h = candidates["by_window_scope"]["1h/all"]
    assert candidate_1h["display_status_counts"] == {
        "display_trade_candidate": 1,
        "hidden_hold_publish": 1,
    }
    assert candidate_1h["evidence_status_counts"] == {"complete": 1, "partial": 1}

    run_1h = runs["by_window_scope"]["1h/all"]
    assert run_1h["outcome_counts"] == {"completed": 1, "invalid_unknown_evidence_ref": 1}
    assert run_1h["failure_count"] == 1
    assert run_1h["invalid_ref_count"] == 1
    assert run_1h["backpressure_count"] == 0

    proposed_runs = runs["policy_comparison"]["proposed_primary"]
    assert proposed_runs["outcome_counts"]["provider_rate_limited"] == 1
    assert proposed_runs["outcome_counts"]["backpressure_circuit_open"] == 1
    assert proposed_runs["backpressure_count"] == 2
    assert proposed_runs["backpressure_rate"] == pytest.approx(0.5)


def test_summarize_job_rows_includes_no_run_pending_dead_and_backpressure_statuses() -> None:
    rows = [
        _job_row("1h", "all", status="pending", has_run=False, next_run_at_ms=900),
        _job_row("1h", "all", status="dead", has_run=False, next_run_at_ms=800),
        _job_row("4h", "all", status="running", has_run=True, next_run_at_ms=700),
        _job_row("5m", "matched", status="done", has_run=True, next_run_at_ms=600),
    ]

    summary = summarize_job_policy_rows(rows, now_ms=1_000)

    one_hour = summary["by_window_scope"]["1h/all"]
    assert one_hour["job_status_counts"] == {"dead": 1, "pending": 1}
    assert one_hour["no_run_count"] == 2
    assert one_hour["backpressure_count"] == 2
    assert one_hour["due_pending_count"] == 1

    proposed = summary["policy_comparison"]["proposed_primary"]
    assert proposed["total_rows"] == 3
    assert proposed["no_run_count"] == 2
    assert proposed["backpressure_count"] == 3


def test_build_pulse_policy_evaluation_uses_only_read_queries_and_returns_sections() -> None:
    conn = FakeConn(
        radar_rows=[_radar_row("1h", "all", authors=3, top_share=0.3, watched_mentions=1)],
        candidate_rows=[_candidate_row("1h", "all", "display_trade_candidate")],
        run_rows=[_run_row("1h", "all", outcome="completed", status="completed", job_status="done")],
        job_rows=[_job_row("1h", "all", status="pending", has_run=False, next_run_at_ms=1_699_999_999_000)],
        publication_state_rows=[
            {
                "window": "1h",
                "scope": "all",
                "current_published_at_ms": 1_700_000_000_000,
                "current_generation_id": "gen-ready",
                "latest_attempt_status": "ready",
            }
        ],
    )

    evaluation = build_pulse_policy_evaluation(conn, now_ms=1_700_000_000_000, lookback_hours=24)

    assert set(evaluation) == {"radar", "candidates", "runs", "jobs"}
    assert evaluation["radar"]["by_window_scope"]["1h/all"]["total_rows"] == 1
    assert evaluation["candidates"]["by_window_scope"]["1h/all"]["total_rows"] == 1
    assert evaluation["runs"]["by_window_scope"]["1h/all"]["total_rows"] == 1
    assert evaluation["jobs"]["by_window_scope"]["1h/all"]["no_run_count"] == 1
    assert any("FROM pulse_agent_jobs" in sql for sql in conn.executed_sql)
    assert conn.executed_sql
    assert all(_is_read_only_select(sql) for sql in conn.executed_sql)


def test_fetch_radar_rows_uses_publication_state_for_ready_current_generation() -> None:
    conn = FakeConn(
        radar_rows=[
            _radar_row(
                "1h",
                "all",
                authors=3,
                top_share=0.3,
                watched_mentions=1,
                computed_at_ms=100,
                generation_id="gen-ready",
            )
        ],
        candidate_rows=[],
        run_rows=[],
        publication_state_rows=[
            {
                "window": "1h",
                "scope": "all",
                "current_published_at_ms": 1_700_000_000_000,
                "current_generation_id": "gen-ready",
                "latest_attempt_status": "ready",
            }
        ],
    )

    rows = fetch_radar_rows(conn, now_ms=1_700_000_060_000, lookback_hours=24)

    assert len(rows) == 1
    assert rows[0]["computed_at_ms"] == 100
    assert all("token_radar_projection_coverage" not in sql for sql in conn.executed_sql)
    row_sql = next(sql for sql in conn.executed_sql if "FROM token_radar_current_rows" in sql)
    assert "JOIN token_radar_publication_state" in row_sql
    assert "state.current_generation_id = token_radar_current_rows.generation_id" in row_sql
    assert "state.latest_attempt_status = 'ready'" in row_sql


def test_fetch_radar_rows_ignores_non_ready_publication_state() -> None:
    conn = FakeConn(
        radar_rows=[_radar_row("1h", "all", authors=3, top_share=0.3, watched_mentions=1, computed_at_ms=100)],
        candidate_rows=[],
        run_rows=[],
        publication_state_rows=[
            {
                "window": "1h",
                "scope": "all",
                "current_published_at_ms": 1_700_000_000_000,
                "current_generation_id": "gen-ready",
                "latest_attempt_status": "failed",
            }
        ],
    )

    rows = fetch_radar_rows(conn, now_ms=1_700_000_060_000, lookback_hours=24)

    assert rows == []


def test_build_pulse_policy_evaluation_uses_configured_current_policy_selection() -> None:
    conn = FakeConn(
        radar_rows=[
            _radar_row("1h", "matched", authors=3, top_share=0.3, watched_mentions=1),
            _radar_row("1h", "all", authors=1, top_share=0.9, watched_mentions=0),
            _radar_row("4h", "matched", authors=4, top_share=0.2, watched_mentions=2),
        ],
        candidate_rows=[
            _candidate_row("1h", "matched", "display_trade_candidate"),
            _candidate_row("1h", "all", "hidden_hold_publish"),
        ],
        run_rows=[
            _run_row("1h", "matched", outcome="completed", status="completed", job_status="done"),
            _run_row("1h", "all", outcome="completed", status="completed", job_status="done"),
        ],
        job_rows=[
            _job_row("1h", "matched", status="done", has_run=True, next_run_at_ms=900),
            _job_row("4h", "matched", status="done", has_run=True, next_run_at_ms=900),
        ],
        publication_state_rows=[
            {
                "window": "1h",
                "scope": "matched",
                "current_published_at_ms": 1_700_000_000_000,
                "current_generation_id": "gen-ready",
                "latest_attempt_status": "ready",
            },
            {
                "window": "1h",
                "scope": "all",
                "current_published_at_ms": 1_700_000_000_000,
                "current_generation_id": "gen-ready",
                "latest_attempt_status": "ready",
            },
            {
                "window": "4h",
                "scope": "matched",
                "current_published_at_ms": 1_700_000_000_000,
                "current_generation_id": "gen-ready",
                "latest_attempt_status": "ready",
            },
        ],
    )

    evaluation = build_pulse_policy_evaluation(
        conn,
        now_ms=1_700_000_000_000,
        lookback_hours=24,
        current_windows=("1h",),
        current_scopes=("matched",),
    )

    assert evaluation["radar"]["policy_comparison"]["current"]["total_rows"] == 1
    assert evaluation["radar"]["policy_comparison"]["current"]["source_quality"]["author_count_buckets"]["ge3"] == 1
    assert evaluation["candidates"]["policy_comparison"]["current"]["display_status_counts"] == {
        "display_trade_candidate": 1
    }
    assert evaluation["runs"]["policy_comparison"]["current"]["outcome_counts"] == {"completed": 1}
    assert evaluation["jobs"]["policy_comparison"]["current"]["total_rows"] == 1


def test_report_rendering_redacts_secrets_and_includes_recommendation() -> None:
    evaluation = {
        "radar": summarize_radar_policy_rows(
            [
                _radar_row("1h", "all", authors=3, top_share=0.3, watched_mentions=1),
                _radar_row("4h", "all", authors=4, top_share=0.25, watched_mentions=0),
            ]
        ),
        "candidates": summarize_candidate_policy_rows(
            [_candidate_row("1h", "all", "display_trade_candidate", evidence_status="complete")]
        ),
        "runs": summarize_pulse_run_rows(
            [
                _run_row("1h", "all", outcome="completed", status="completed", job_status="done"),
                _run_row("4h", "all", outcome="provider_rate_limited", status="failed", job_status="pending"),
            ]
        ),
        "jobs": summarize_job_policy_rows(
            [_job_row("4h", "all", status="pending", has_run=False, next_run_at_ms=1_000)],
            now_ms=2_000,
        ),
    }

    report = render_pulse_policy_evaluation_report(
        evaluation,
        generated_date="2026-05-20",
        lookback_hours=24,
        config_context={
            "config_path": "/Users/qinghuan/.parallax/config.yaml",
            "workers_config_path": "/Users/qinghuan/.parallax/workers.yaml",
            "config_path_under_operator_home": True,
            "workers_config_path_under_operator_home": True,
            "postgres_dsn": "postgresql://parallax_app:super-secret-password@localhost/db",
        },
    )

    assert "super-secret-password" not in report
    assert "postgresql://" not in report
    assert any(
        f"Recommendation: {recommendation}" in report for recommendation in ("ship", "revise thresholds", "stop")
    )
    assert "/Users/qinghuan/.parallax/config.yaml" in report
    assert "config_path_under_operator_home: true" in report
    assert "top_author_share_buckets=" in report
    assert "watched_to_matched_ratio=" in report
    assert "display_status_counts=" in report
    assert "outcome_counts=" in report
    assert "status_counts=" in report
    assert "failure_rate=" in report
    assert "backpressure_rate=" in report
    assert "sample_kind=latest_snapshot" in report
    assert "radar latest-snapshot sample size" in report
    assert not report.endswith("\n")


class FakeCursor:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    def fetchall(self) -> list[dict]:
        return self._rows

    def fetchone(self) -> dict | None:
        return self._rows[0] if self._rows else None


class FakeConn:
    def __init__(
        self,
        *,
        radar_rows: list[dict],
        candidate_rows: list[dict],
        run_rows: list[dict],
        job_rows: list[dict] | None = None,
        publication_state_rows: list[dict] | None = None,
    ) -> None:
        self._rows = {
            "token_radar_current_rows": radar_rows,
            "token_radar_publication_state": publication_state_rows or [],
            "pulse_candidates": candidate_rows,
            "pulse_agent_runs": run_rows,
            "pulse_agent_jobs": job_rows or [],
        }
        self.executed_sql: list[str] = []

    def execute(self, sql: str, params: tuple[object, ...]) -> FakeCursor:
        self.executed_sql.append(sql)
        verb = sql.strip().split(maxsplit=1)[0].upper()
        assert verb in {"SELECT", "WITH"}
        if "FROM pulse_agent_runs" in sql:
            return FakeCursor(self._rows["pulse_agent_runs"])
        if "FROM pulse_agent_jobs" in sql:
            return FakeCursor(self._rows["pulse_agent_jobs"])
        if "FROM token_radar_current_rows" in sql and '"window" = %s' in sql and "scope = %s" in sql:
            window, scope = str(params[1]), str(params[2])
            state_rows = [
                row
                for row in self._rows["token_radar_publication_state"]
                if row.get("window") == window
                and row.get("scope") == scope
                and row.get("latest_attempt_status") == "ready"
            ]
            if not state_rows:
                return FakeCursor([])
            generation_id = state_rows[0].get("current_generation_id")
            rows = [
                row
                for row in self._rows["token_radar_current_rows"]
                if row.get("window") == window
                and row.get("scope") == scope
                and row.get("generation_id", "gen-ready") == generation_id
            ]
            return FakeCursor(rows)
        for table, rows in self._rows.items():
            if table in sql:
                return FakeCursor(rows)
        raise AssertionError(f"unexpected SQL: {sql}")


def _is_read_only_select(sql: str) -> bool:
    verb = sql.strip().split(maxsplit=1)[0].upper()
    return verb in {"SELECT", "WITH"}


def _radar_row(
    window: str,
    scope: str,
    *,
    authors: int,
    top_share: float,
    watched_mentions: int,
    computed_at_ms: int = 1_000,
    generation_id: str = "gen-ready",
) -> dict:
    return {
        "window": window,
        "scope": scope,
        "generation_id": generation_id,
        "subject_key": f"{window}:{scope}:{authors}:{top_share}:{watched_mentions}",
        "computed_at_ms": computed_at_ms,
        "factor_snapshot_json": _factor_snapshot(
            authors=authors,
            top_share=top_share,
            watched_mentions=watched_mentions,
        ),
        "decision": "watch",
    }


def _candidate_row(
    window: str,
    scope: str,
    display_status: str,
    *,
    evidence_status: str = "complete",
) -> dict:
    return {
        "window": window,
        "scope": scope,
        "candidate_id": f"{window}:{scope}:{display_status}",
        "display_status": display_status,
        "pulse_status": "admitted",
        "decision_status": "trade_candidate" if display_status.startswith("display_") else "invalid",
        "evidence_status": evidence_status,
        "factor_snapshot_json": _factor_snapshot(authors=2, top_share=0.5, watched_mentions=1),
    }


def _run_row(window: str, scope: str, *, outcome: str, status: str, job_status: str) -> dict:
    return {
        "window": window,
        "scope": scope,
        "run_id": f"{window}:{scope}:{outcome}",
        "outcome": outcome,
        "status": status,
        "job_status": job_status,
        "display_status": "display_trade_candidate" if outcome == "completed" else "hidden_invalid_output",
        "evidence_status": "complete",
    }


def _job_row(
    window: str,
    scope: str,
    *,
    status: str,
    has_run: bool,
    next_run_at_ms: int,
) -> dict:
    return {
        "window": window,
        "scope": scope,
        "job_id": f"{window}:{scope}:{status}:{has_run}",
        "candidate_id": f"candidate:{window}:{scope}:{status}",
        "status": status,
        "attempt_count": 1,
        "max_attempts": 3,
        "next_run_at_ms": next_run_at_ms,
        "latest_run_id": f"run:{window}:{scope}:{status}" if has_run else None,
        "latest_run_outcome": "completed" if has_run else None,
        "updated_at_ms": next_run_at_ms,
    }


def _factor_snapshot(*, authors: int, top_share: float, watched_mentions: int) -> dict:
    return {
        "families": {
            "social_heat": {
                "facts": {
                    "unique_authors": authors,
                    "watched_mentions": watched_mentions,
                }
            },
            "social_propagation": {
                "facts": {
                    "independent_authors": authors,
                    "top_author_share": top_share,
                    "watched_author_count": 1 if watched_mentions else 0,
                }
            },
        },
    }
