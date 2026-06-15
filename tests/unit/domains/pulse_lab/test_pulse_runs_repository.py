from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from parallax.domains.pulse_lab.repositories.pulse_runs_repository import PulseRunsRepository

NOW_MS = 1_779_000_000_000
_ROWCOUNT_MISSING = object()
_NO_EXISTING_RUN = object()


class PulseRunReturningCursor:
    def __init__(self, rows: list[dict[str, Any]], *, rowcount: object = _ROWCOUNT_MISSING) -> None:
        self._rows = rows
        if rowcount is not _ROWCOUNT_MISSING:
            self.rowcount = rowcount

    def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None


class PulseRunReturningConnection:
    def __init__(
        self,
        rows: list[dict[str, Any]],
        *,
        rowcount: object = _ROWCOUNT_MISSING,
        existing_run: dict[str, Any] | object = _ROWCOUNT_MISSING,
    ) -> None:
        self.rows = rows
        self.rowcount = rowcount
        self.existing_run = _existing_run() if existing_run is _ROWCOUNT_MISSING else existing_run
        self.sql: list[str] = []

    def execute(self, sql: str, params: Any = None) -> PulseRunReturningCursor:
        del params
        self.sql.append(sql)
        if "SELECT started_at_ms, usage_json, trace_metadata_json FROM pulse_agent_runs" in sql:
            rows = [] if self.existing_run is _NO_EXISTING_RUN else [self.existing_run]
            return PulseRunReturningCursor(rows)
        if "RETURNING *" in sql:
            return PulseRunReturningCursor(self.rows, rowcount=self.rowcount)
        raise AssertionError(f"unexpected SQL: {sql}")


def _existing_run() -> dict[str, Any]:
    return {"started_at_ms": NOW_MS - 100, "usage_json": {}, "trace_metadata_json": {}}


def _run_row() -> dict[str, Any]:
    return {
        "run_id": "run-1",
        "job_id": "job-1",
        "candidate_id": "candidate-1",
        "status": "running",
        "outcome": "running",
    }


def _step_row() -> dict[str, Any]:
    return {
        "step_id": "step-1",
        "run_id": "run-1",
        "stage": "pulse_decision",
        "attempt_index": 0,
    }


def _run_insert_agent_run(repo: PulseRunsRepository) -> dict[str, Any]:
    return repo.insert_agent_run(
        run_id="run-1",
        job_id="job-1",
        candidate_id="candidate-1",
        provider="test",
        model="model",
        workflow_name="workflow",
        agent_name="agent",
        artifact_version_hash="sha256:artifact",
        prompt_version="prompt-v1",
        schema_version="schema-v1",
        runtime_version="runtime-v1",
        runtime_hash="sha256:runtime",
        input_hash="sha256:input",
        outcome="running",
        commit=False,
    )


def _run_finish_agent_run(repo: PulseRunsRepository) -> dict[str, Any] | None:
    return repo.finish_agent_run(
        "run-1",
        "done",
        response_json={"status": "done"},
        outcome="completed",
        commit=False,
    )


def _run_insert_agent_run_step(repo: PulseRunsRepository) -> dict[str, Any]:
    return repo.insert_agent_run_step(
        step_id="step-1",
        run_id="run-1",
        stage="pulse_decision",
        route="meme",
        attempt_index=0,
        provider="test",
        model="model",
        prompt_version="prompt-v1",
        schema_version="schema-v1",
        input_json={},
        prompt_text="prompt",
        response_json={},
        commit=False,
    )


@pytest.mark.parametrize(
    ("operation", "invoke", "rows"),
    [
        pytest.param("insert_agent_run", _run_insert_agent_run, [_run_row()], id="run"),
        pytest.param("finish_agent_run", _run_finish_agent_run, [_run_row()], id="finish"),
        pytest.param("insert_agent_run_step", _run_insert_agent_run_step, [_step_row()], id="step"),
    ],
)
def test_pulse_run_returning_writes_require_cursor_rowcount(
    operation: str,
    invoke: Callable[[PulseRunsRepository], dict[str, Any] | None],
    rows: list[dict[str, Any]],
) -> None:
    del operation
    conn = PulseRunReturningConnection(rows=rows)

    with pytest.raises(TypeError, match="pulse_runs_repository_rowcount_required"):
        invoke(PulseRunsRepository(conn))


@pytest.mark.parametrize(
    ("operation", "invoke", "rows"),
    [
        pytest.param("insert_agent_run", _run_insert_agent_run, [_run_row()], id="run"),
        pytest.param("finish_agent_run", _run_finish_agent_run, [_run_row()], id="finish"),
        pytest.param("insert_agent_run_step", _run_insert_agent_run_step, [_step_row()], id="step"),
    ],
)
@pytest.mark.parametrize(
    ("rowcount", "expected_rows", "expected_error"),
    [
        pytest.param(True, [_run_row()], "invalid", id="bool-true"),
        pytest.param(False, [], "invalid", id="bool-false"),
        pytest.param("1", [_run_row()], "invalid", id="numeric-string"),
        pytest.param(-1, [], "invalid", id="negative"),
        pytest.param(2, [_run_row()], "invalid", id="multi-row"),
        pytest.param(0, [_run_row()], "invalid", id="zero-with-row"),
        pytest.param(1, [], "invalid", id="one-without-row"),
    ],
)
def test_pulse_run_returning_writes_reject_invalid_or_mismatched_rowcount(
    operation: str,
    invoke: Callable[[PulseRunsRepository], dict[str, Any] | None],
    rows: list[dict[str, Any]],
    rowcount: object,
    expected_rows: list[dict[str, Any]],
    expected_error: str,
) -> None:
    del operation, rows
    conn = PulseRunReturningConnection(rows=expected_rows, rowcount=rowcount)

    with pytest.raises(TypeError, match=f"pulse_runs_repository_rowcount_{expected_error}"):
        invoke(PulseRunsRepository(conn))


def test_pulse_run_returning_writes_accept_valid_single_rowcount() -> None:
    run_conn = PulseRunReturningConnection(rows=[_run_row()], rowcount=1)
    finish_conn = PulseRunReturningConnection(rows=[_run_row()], rowcount=1)
    step_conn = PulseRunReturningConnection(rows=[_step_row()], rowcount=1)

    assert _run_insert_agent_run(PulseRunsRepository(run_conn))["run_id"] == "run-1"
    assert _run_finish_agent_run(PulseRunsRepository(finish_conn))["run_id"] == "run-1"
    assert _run_insert_agent_run_step(PulseRunsRepository(step_conn))["step_id"] == "step-1"


def test_finish_agent_run_no_existing_run_returns_none_without_update_rowcount() -> None:
    conn = PulseRunReturningConnection(rows=[], existing_run=_NO_EXISTING_RUN)

    assert _run_finish_agent_run(PulseRunsRepository(conn)) is None
    assert len(conn.sql) == 1
