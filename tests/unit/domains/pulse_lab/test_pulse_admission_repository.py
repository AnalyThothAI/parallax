from __future__ import annotations

from typing import Any

import pytest

from parallax.domains.pulse_lab.repositories.pulse_admission_repository import PulseAdmissionRepository

NOW_MS = 1_779_000_000_000
_ROWCOUNT_MISSING = object()


class MissingTransactionConnection:
    def __init__(self) -> None:
        self.sql: list[str] = []
        self.commits = 0

    def execute(self, sql: str, params: Any = None) -> object:
        self.sql.append(sql)
        raise AssertionError("claim_pulse_admission must require transaction before SQL")

    def commit(self) -> None:
        self.commits += 1
        raise AssertionError("claim_pulse_admission must not manually commit without transaction")


class NonCallableTransactionConnection(MissingTransactionConnection):
    transaction = None


class PulseAdmissionReturningCursor:
    def __init__(self, rows: list[dict[str, Any]], *, rowcount: object = _ROWCOUNT_MISSING) -> None:
        self._rows = rows
        if rowcount is not _ROWCOUNT_MISSING:
            self.rowcount = rowcount

    def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None


class PulseAdmissionReturningConnection:
    def __init__(self, rows: list[dict[str, Any]], *, rowcount: object = _ROWCOUNT_MISSING) -> None:
        self.rows = rows
        self.rowcount = rowcount
        self.sql: list[str] = []

    def execute(self, sql: str, params: Any = None) -> PulseAdmissionReturningCursor:
        del params
        self.sql.append(sql)
        return PulseAdmissionReturningCursor(self.rows, rowcount=self.rowcount)


def _run_claim_edge_budget(repo: PulseAdmissionRepository) -> bool:
    return repo.claim_edge_budget(
        candidate_id="candidate-1",
        hour_bucket_ms=NOW_MS,
        now_ms=NOW_MS,
        commit=False,
    )


def _run_record_edge_observation(repo: PulseAdmissionRepository) -> dict[str, Any]:
    return repo.record_edge_observation(
        candidate_id="candidate-1",
        current_state_json={"score_band": "trade_candidate"},
        edge_signature="edge",
        observed_at_ms=NOW_MS,
        commit=False,
    )


def _run_mark_edge_job_enqueued(repo: PulseAdmissionRepository) -> dict[str, Any]:
    return repo.mark_edge_job_enqueued(
        candidate_id="candidate-1",
        processed_state_json={"score_band": "trade_candidate"},
        edge_events_json=["rank_score_changed"],
        job_id="job-1",
        processed_at_ms=NOW_MS,
        commit=False,
    )


def _run_mark_edge_budget_rejected(repo: PulseAdmissionRepository) -> dict[str, Any] | None:
    return repo.mark_edge_budget_rejected(
        candidate_id="candidate-1",
        edge_events_json=["rank_score_changed"],
        rejected_at_ms=NOW_MS,
        commit=False,
    )


def _run_mark_edge_run_finished(repo: PulseAdmissionRepository) -> dict[str, Any] | None:
    return repo.mark_edge_run_finished(
        candidate_id="candidate-1",
        agent_run_id="run-1",
        processed_state_json={"score_band": "trade_candidate"},
        edge_events_json=["rank_score_changed"],
        finished_at_ms=NOW_MS,
        commit=False,
    )


@pytest.mark.parametrize(
    "connection_type",
    [
        pytest.param(MissingTransactionConnection, id="missing-transaction"),
        pytest.param(NonCallableTransactionConnection, id="non-callable-transaction"),
    ],
)
def test_claim_pulse_admission_requires_connection_transaction_before_edge_or_budget_sql(
    connection_type: type[MissingTransactionConnection],
) -> None:
    connection = connection_type()
    repo = PulseAdmissionRepository(connection)

    with pytest.raises(RuntimeError, match="pulse_repository_transaction_required"):
        repo.claim_pulse_admission(
            candidate_id="candidate-1",
            target_type="Asset",
            target_id="asset-1",
            hour_bucket_ms=NOW_MS,
            now_ms=NOW_MS,
            target_limit=1,
            candidate_limit=1,
            edge_state={"score_band": "trade_candidate", "rank_score": 80},
            edge_events=("rank_score_changed",),
        )

    assert connection.sql == []
    assert connection.commits == 0


@pytest.mark.parametrize(
    ("operation", "invoke"),
    [
        pytest.param("claim_edge_budget", _run_claim_edge_budget, id="claim-edge-budget"),
        pytest.param("record_edge_observation", _run_record_edge_observation, id="record-edge-observation"),
        pytest.param("mark_edge_job_enqueued", _run_mark_edge_job_enqueued, id="mark-edge-job-enqueued"),
        pytest.param("mark_edge_budget_rejected", _run_mark_edge_budget_rejected, id="mark-edge-budget-rejected"),
        pytest.param("mark_edge_run_finished", _run_mark_edge_run_finished, id="mark-edge-run-finished"),
    ],
)
def test_pulse_admission_returning_writes_require_cursor_rowcount(
    operation: str,
    invoke: Any,
) -> None:
    del operation
    conn = PulseAdmissionReturningConnection(rows=[{"candidate_id": "candidate-1", "enqueue_count": 1}])

    with pytest.raises(TypeError, match="pulse_admission_repository_rowcount_required"):
        invoke(PulseAdmissionRepository(conn))


@pytest.mark.parametrize(
    ("rowcount", "rows", "expected_error"),
    [
        pytest.param(True, [{"candidate_id": "candidate-1", "enqueue_count": 1}], "invalid", id="bool-true"),
        pytest.param(False, [], "invalid", id="bool-false"),
        pytest.param("1", [{"candidate_id": "candidate-1", "enqueue_count": 1}], "invalid", id="numeric-string"),
        pytest.param(-1, [], "invalid", id="negative"),
        pytest.param(2, [{"candidate_id": "candidate-1", "enqueue_count": 1}], "invalid", id="multi-row"),
        pytest.param(0, [{"candidate_id": "candidate-1", "enqueue_count": 1}], "invalid", id="zero-with-row"),
        pytest.param(1, [], "invalid", id="one-without-row"),
    ],
)
def test_claim_edge_budget_returning_rowcount_must_match_returned_row(
    rowcount: object,
    rows: list[dict[str, Any]],
    expected_error: str,
) -> None:
    conn = PulseAdmissionReturningConnection(rows=rows, rowcount=rowcount)

    with pytest.raises(TypeError, match=f"pulse_admission_repository_rowcount_{expected_error}"):
        _run_claim_edge_budget(PulseAdmissionRepository(conn))


def test_claim_edge_budget_uses_returning_rowcount_for_boolean_result() -> None:
    accepted = PulseAdmissionRepository(
        PulseAdmissionReturningConnection(rows=[{"candidate_id": "candidate-1", "enqueue_count": 1}], rowcount=1)
    )
    exhausted = PulseAdmissionRepository(PulseAdmissionReturningConnection(rows=[], rowcount=0))

    assert _run_claim_edge_budget(accepted) is True
    assert _run_claim_edge_budget(exhausted) is False


@pytest.mark.parametrize("max_enqueues", [0, -1, True, "3"])
def test_claim_edge_budget_rejects_malformed_max_enqueues_before_sql(max_enqueues: object) -> None:
    conn = MissingTransactionConnection()

    with pytest.raises(ValueError, match="pulse_edge_budget_max_enqueues_required"):
        PulseAdmissionRepository(conn).claim_edge_budget(
            candidate_id="candidate-1",
            hour_bucket_ms=NOW_MS,
            now_ms=NOW_MS,
            max_enqueues=max_enqueues,  # type: ignore[arg-type]
            commit=False,
        )

    assert conn.sql == []
