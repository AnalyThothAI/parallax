from __future__ import annotations

from typing import Any

import pytest

from parallax.domains.pulse_lab.repositories import pulse_read_repository as module
from parallax.domains.pulse_lab.repositories.pulse_read_repository import PulseReadRepository


def test_pulse_read_repository_list_candidates_requires_explicit_limit_without_default() -> None:
    try:
        PulseReadRepository(object()).list_candidates(window="1h", scope="matched")
    except TypeError as exc:
        assert "limit" in str(exc)
    else:  # pragma: no cover - RED guard expectation
        raise AssertionError("Pulse list candidates must require an explicit public read limit")


def test_pulse_read_repository_treats_blank_q_as_no_search_filter() -> None:
    conn = CapturingPulseReadConnection()
    repository = PulseReadRepository(conn)

    repository.list_candidates(window="1h", scope="matched", q="   ", limit=10)
    repository.pulse_summary(window="1h", scope="matched", q="\t")

    sql = "\n".join(query for query, _params in conn.executions)
    params = [param for _query, query_params in conn.executions for param in query_params]

    assert "ILIKE" not in sql
    assert "%%" not in params


def test_pulse_read_repository_strips_q_before_ilike_filter() -> None:
    conn = CapturingPulseReadConnection()

    PulseReadRepository(conn).list_candidates(window="1h", scope="matched", q="  PEPE  ", limit=10)

    query, params = conn.executions[0]
    assert "ILIKE" in query
    assert params[2:5] == ("%PEPE%", "%PEPE%", "%PEPE%")


def test_signal_pulse_notification_candidates_use_single_keyset_window_query() -> None:
    conn = CapturingPulseReadConnection()

    rows = PulseReadRepository(conn).list_signal_pulse_notification_candidates(
        window="1h",
        scopes=("all", "matched"),
        statuses=("token_watch", "trade_candidate"),
        per_scope_status_limit=25,
    )

    assert rows == []
    assert len(conn.executions) == 1
    query, params = conn.executions[0]
    assert "input_scopes AS" in query
    assert "input_statuses AS" in query
    assert "unnest(%s::text[]) WITH ORDINALITY" in query
    assert "unnest(%s::text[], %s::text[])" in query
    assert "ROW_NUMBER() OVER" in query
    assert "PARTITION BY input_scopes.scope, input_statuses.public_status" in query
    assert "candidate.evidence_packet_hash IS NOT NULL" in query
    assert "candidate.display_status = input_statuses.display_status" in query
    assert params == (
        ["all", "matched"],
        ["token_watch", "trade_candidate"],
        ["display_token_watch", "display_trade_candidate"],
        "1h",
        25,
    )


def test_signal_pulse_notification_candidates_allow_zero_limit_without_sql() -> None:
    conn = CapturingPulseReadConnection()

    rows = PulseReadRepository(conn).list_signal_pulse_notification_candidates(
        window="1h",
        scopes=("all",),
        statuses=("token_watch",),
        per_scope_status_limit=0,
    )

    assert rows == []
    assert conn.executions == []


@pytest.mark.parametrize("per_scope_status_limit", [-1, True, "25"])
def test_signal_pulse_notification_candidates_reject_malformed_limit_before_sql(
    per_scope_status_limit: object,
) -> None:
    conn = CapturingPulseReadConnection()

    with pytest.raises(ValueError, match="pulse_notification_candidate_limit_required"):
        PulseReadRepository(conn).list_signal_pulse_notification_candidates(
            window="1h",
            scopes=("all",),
            statuses=("token_watch",),
            per_scope_status_limit=per_scope_status_limit,  # type: ignore[arg-type]
        )

    assert conn.executions == []


def test_pulse_read_repository_freshness_health_requires_explicit_since_hours_without_default() -> None:
    try:
        PulseReadRepository(object()).freshness_health(window="1h", scope="matched", now_ms=10_000)
    except TypeError as exc:
        assert "since_hours" in str(exc)
    else:  # pragma: no cover - RED guard expectation
        raise AssertionError("Pulse freshness health must require an explicit since_hours window")


@pytest.mark.parametrize("since_hours", [0, -1, True, "4"])
def test_pulse_read_repository_freshness_health_rejects_malformed_since_hours(since_hours: object) -> None:
    with pytest.raises(ValueError, match="pulse_freshness_since_hours_required"):
        PulseReadRepository(object()).freshness_health(
            window="1h",
            scope="matched",
            now_ms=10_000,
            since_hours=since_hours,  # type: ignore[arg-type]
        )


def test_pulse_read_repository_freshness_health_owns_public_health_contract(monkeypatch) -> None:
    conn = object()
    calls: dict[str, dict[str, Any]] = {}

    def fetch_clocks(fake_conn: object, *, window: str, scope: str) -> dict[str, int | None]:
        calls["clocks"] = {"conn": fake_conn, "window": window, "scope": scope}
        return {
            "latest_packet_created_at_ms": 9_000,
            "latest_agent_run_finished_at_ms": 8_000,
            "latest_public_candidate_updated_at_ms": 7_500,
        }

    def fetch_jobs(
        fake_conn: object,
        *,
        window: str,
        scope: str,
        now_ms: int,
        since_ms: int,
    ) -> dict[str, int]:
        calls["jobs"] = {
            "conn": fake_conn,
            "window": window,
            "scope": scope,
            "now_ms": now_ms,
            "since_ms": since_ms,
        }
        return {"due_jobs": 1, "claimed_jobs": 0, "failed_jobs_4h": 0, "dead_jobs": 1}

    def fetch_runs(fake_conn: object, *, window: str, scope: str, since_ms: int) -> dict[str, int | float]:
        calls["runs"] = {"conn": fake_conn, "window": window, "scope": scope, "since_ms": since_ms}
        return {
            "agent_runs_4h": 10,
            "agent_failed_4h": 1,
            "agent_failure_rate_4h": 0.1,
            "unknown_ref_failures_4h": 0,
            "unknown_ref_failure_rate_4h": 0.0,
            "unsupported_claim_failures_4h": 0,
            "unsupported_claim_failure_rate_4h": 0.0,
        }

    def fetch_candidates(fake_conn: object, *, window: str, scope: str, since_ms: int) -> dict[str, int | None]:
        calls["candidates"] = {"conn": fake_conn, "window": window, "scope": scope, "since_ms": since_ms}
        return {
            "hidden_abstain_4h": 0,
            "hidden_hold_publish_4h": 0,
            "latest_hidden_hold_candidate_updated_at_ms": None,
            "hidden_insufficient_evidence_4h": 0,
            "public_candidates_4h": 3,
        }

    monkeypatch.setattr(module, "fetch_pulse_health_clocks", fetch_clocks)
    monkeypatch.setattr(module, "fetch_pulse_health_jobs", fetch_jobs)
    monkeypatch.setattr(module, "fetch_pulse_health_runs", fetch_runs)
    monkeypatch.setattr(module, "fetch_pulse_health_candidates", fetch_candidates)

    health = PulseReadRepository(conn).freshness_health(
        window="1h",
        scope="matched",
        now_ms=10_000,
        since_hours=4,
    )

    assert calls == {
        "clocks": {"conn": conn, "window": "1h", "scope": "matched"},
        "jobs": {"conn": conn, "window": "1h", "scope": "matched", "now_ms": 10_000, "since_ms": 0},
        "runs": {"conn": conn, "window": "1h", "scope": "matched", "since_ms": 0},
        "candidates": {"conn": conn, "window": "1h", "scope": "matched", "since_ms": 0},
    }
    assert health["publish_status"] == "degraded"
    assert health["reasons"] == ["dead_jobs_present"]
    assert health["public_candidates_4h"] == 3
    assert health["dead_jobs"] == 1


class CapturingPulseReadCursor:
    def __init__(self, *, rows: list[dict[str, Any]] | None = None, row: dict[str, Any] | None = None) -> None:
        self._rows = rows or []
        self._row = row

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self._rows)

    def fetchone(self) -> dict[str, Any] | None:
        return self._row


class CapturingPulseReadConnection:
    def __init__(self) -> None:
        self.executions: list[tuple[str, tuple[Any, ...]]] = []

    def execute(self, query: str, params: tuple[Any, ...] = ()) -> CapturingPulseReadCursor:
        self.executions.append((query, tuple(params)))
        if "dead_job_count" in query:
            return CapturingPulseReadCursor(row={"dead_job_count": 0})
        if "candidate_count" in query:
            return CapturingPulseReadCursor(
                row={
                    "candidate_count": 0,
                    "trade_candidate_count": 0,
                    "token_watch_count": 0,
                    "risk_rejected_high_info_count": 0,
                    "decision_route_cex_count": 0,
                    "decision_route_meme_count": 0,
                    "decision_route_research_only_count": 0,
                    "decision_high_conviction_count": 0,
                    "decision_trade_candidate_count": 0,
                    "decision_watchlist_count": 0,
                    "decision_ignore_count": 0,
                    "decision_abstain_count": 0,
                    "blocked_low_information_count": 0,
                    "displayable_count": 0,
                    "hidden_candidate_count": 0,
                    "market_fresh_count": 0,
                }
            )
        return CapturingPulseReadCursor(rows=[])
