from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from parallax.domains.pulse_lab.repositories.pulse_agent_eval_repository import PulseAgentEvalRepository

_ROWCOUNT_MISSING = object()


class PulseAgentEvalReturningCursor:
    def __init__(self, rows: list[dict[str, Any]], *, rowcount: object = _ROWCOUNT_MISSING) -> None:
        self._rows = rows
        if rowcount is not _ROWCOUNT_MISSING:
            self.rowcount = rowcount

    def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None


class PulseAgentEvalReturningConnection:
    def __init__(self, rows: list[dict[str, Any]], *, rowcount: object = _ROWCOUNT_MISSING) -> None:
        self.rows = rows
        self.rowcount = rowcount
        self.sql: list[str] = []

    def execute(self, sql: str, params: Any = None) -> PulseAgentEvalReturningCursor:
        del params
        self.sql.append(sql)
        if "RETURNING *" in sql:
            return PulseAgentEvalReturningCursor(self.rows, rowcount=self.rowcount)
        raise AssertionError(f"unexpected SQL: {sql}")


def _runtime_row() -> dict[str, Any]:
    return {"runtime_hash": "sha256:runtime", "runtime_version": "runtime-v1"}


def _eval_case_row() -> dict[str, Any]:
    return {"eval_case_id": "case-1", "source_run_id": "run-1", "eval_type": "deterministic"}


def _eval_result_row() -> dict[str, Any]:
    return {"eval_result_id": "result-1", "eval_case_id": "case-1", "status": "pass"}


def _run_upsert_agent_runtime_version(repo: PulseAgentEvalRepository) -> dict[str, Any]:
    return repo.upsert_agent_runtime_version(
        runtime_version="runtime-v1",
        runtime_hash="sha256:runtime",
        strategy="default",
        provider="test",
        model="model",
        prompt_version="prompt-v1",
        schema_version="schema-v1",
        manifest_json={},
        commit=False,
    )


def _run_insert_agent_eval_case(repo: PulseAgentEvalRepository) -> dict[str, Any]:
    return repo.insert_agent_eval_case(
        eval_case_id="case-1",
        source_run_id="run-1",
        runtime_hash="sha256:runtime",
        eval_type="deterministic",
        route="meme",
        recommendation="trade_candidate",
        input_json={},
        expected_json={},
        rubric_json={},
        commit=False,
    )


def _run_upsert_agent_eval_result(repo: PulseAgentEvalRepository) -> dict[str, Any]:
    return repo.upsert_agent_eval_result(
        eval_result_id="result-1",
        eval_case_id="case-1",
        runtime_hash="sha256:runtime",
        status="pass",
        score=1.0,
        grader_version="grader-v1",
        details_json={},
        commit=False,
    )


@pytest.mark.parametrize(
    ("operation", "invoke", "rows"),
    [
        pytest.param("upsert_agent_runtime_version", _run_upsert_agent_runtime_version, [_runtime_row()], id="runtime"),
        pytest.param("insert_agent_eval_case", _run_insert_agent_eval_case, [_eval_case_row()], id="case"),
        pytest.param("upsert_agent_eval_result", _run_upsert_agent_eval_result, [_eval_result_row()], id="result"),
    ],
)
def test_pulse_agent_eval_returning_writes_require_cursor_rowcount(
    operation: str,
    invoke: Callable[[PulseAgentEvalRepository], dict[str, Any]],
    rows: list[dict[str, Any]],
) -> None:
    del operation
    conn = PulseAgentEvalReturningConnection(rows=rows)

    with pytest.raises(TypeError, match="pulse_agent_eval_repository_rowcount_required"):
        invoke(PulseAgentEvalRepository(conn))


@pytest.mark.parametrize(
    ("operation", "invoke"),
    [
        pytest.param("upsert_agent_runtime_version", _run_upsert_agent_runtime_version, id="runtime"),
        pytest.param("insert_agent_eval_case", _run_insert_agent_eval_case, id="case"),
        pytest.param("upsert_agent_eval_result", _run_upsert_agent_eval_result, id="result"),
    ],
)
@pytest.mark.parametrize(
    ("rowcount", "rows", "expected_error"),
    [
        pytest.param(True, [_runtime_row()], "invalid", id="bool-true"),
        pytest.param(False, [], "invalid", id="bool-false"),
        pytest.param("1", [_runtime_row()], "invalid", id="numeric-string"),
        pytest.param(-1, [], "invalid", id="negative"),
        pytest.param(0, [], "invalid", id="zero-without-row"),
        pytest.param(0, [_runtime_row()], "invalid", id="zero-with-row"),
        pytest.param(1, [], "invalid", id="one-without-row"),
        pytest.param(2, [_runtime_row()], "invalid", id="multi-row"),
    ],
)
def test_pulse_agent_eval_returning_writes_reject_invalid_or_mismatched_rowcount(
    operation: str,
    invoke: Callable[[PulseAgentEvalRepository], dict[str, Any]],
    rowcount: object,
    rows: list[dict[str, Any]],
    expected_error: str,
) -> None:
    del operation
    conn = PulseAgentEvalReturningConnection(rows=rows, rowcount=rowcount)

    with pytest.raises(TypeError, match=f"pulse_agent_eval_repository_rowcount_{expected_error}"):
        invoke(PulseAgentEvalRepository(conn))


def test_pulse_agent_eval_returning_writes_accept_valid_single_rowcount() -> None:
    runtime_conn = PulseAgentEvalReturningConnection(rows=[_runtime_row()], rowcount=1)
    case_conn = PulseAgentEvalReturningConnection(rows=[_eval_case_row()], rowcount=1)
    result_conn = PulseAgentEvalReturningConnection(rows=[_eval_result_row()], rowcount=1)

    assert _run_upsert_agent_runtime_version(PulseAgentEvalRepository(runtime_conn))["runtime_hash"] == "sha256:runtime"
    assert _run_insert_agent_eval_case(PulseAgentEvalRepository(case_conn))["eval_case_id"] == "case-1"
    assert _run_upsert_agent_eval_result(PulseAgentEvalRepository(result_conn))["eval_result_id"] == "result-1"
