from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from parallax.domains.pulse_lab.repositories.pulse_candidates_repository import PulseCandidatesRepository

NOW_MS = 1_779_000_000_000
_ROWCOUNT_MISSING = object()


class PulseCandidateReturningCursor:
    def __init__(self, rows: list[dict[str, Any]], *, rowcount: object = _ROWCOUNT_MISSING) -> None:
        self._rows = rows
        if rowcount is not _ROWCOUNT_MISSING:
            self.rowcount = rowcount

    def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None


class PulseCandidateReturningConnection:
    def __init__(self, rows: list[dict[str, Any]], *, rowcount: object = _ROWCOUNT_MISSING) -> None:
        self.rows = rows
        self.rowcount = rowcount
        self.sql: list[str] = []

    def execute(self, sql: str, params: Any = None) -> PulseCandidateReturningCursor:
        del params
        self.sql.append(sql)
        if "SELECT *" in sql:
            raise AssertionError("pulse_candidates_repository must not restore write success with fallback SELECT")
        return PulseCandidateReturningCursor(self.rows, rowcount=self.rowcount)


def _run_upsert_candidate(repo: PulseCandidatesRepository) -> dict[str, Any] | None:
    return repo.upsert_candidate(
        candidate_id="candidate-1",
        candidate_type="token_target",
        subject_key="asset:sol",
        target_type="asset",
        target_id="asset:sol",
        symbol="SOL",
        window="1h",
        scope="global",
        pulse_status="token_watch",
        verdict="token_watch",
        social_phase="ignition",
        candidate_score=82.0,
        score_band="watch",
        trigger_signature="trigger",
        timeline_signature="timeline",
        factor_snapshot_json={"composite": {"rank_score": 82}},
        gate_json={"pulse_status": "token_watch"},
        decision_route="meme",
        decision_recommendation="watchlist",
        decision_confidence=0.82,
        decision_stage_count=1,
        decision_json={"recommendation": "watchlist"},
        pulse_version="pulse-v1",
        gate_version="gate-v1",
        prompt_version="prompt-v1",
        schema_version="schema-v1",
        commit=False,
    )


def _run_hide_public_candidate(repo: PulseCandidatesRepository) -> dict[str, Any] | None:
    return repo.hide_public_candidate_for_low_information(
        candidate_id="candidate-1",
        candidate_score=12.0,
        trigger_signature="trigger",
        factor_snapshot_json={"composite": {"rank_score": 12}},
        gate_json={"pulse_status": "blocked_low_information"},
        commit=False,
    )


def _candidate_row() -> dict[str, Any]:
    return {
        "candidate_id": "candidate-1",
        "candidate_type": "token_target",
        "target_type": "asset",
        "target_id": "asset:sol",
        "window": "1h",
        "scope": "global",
    }


@pytest.mark.parametrize(
    ("operation", "invoke"),
    [
        pytest.param("upsert_candidate", _run_upsert_candidate, id="upsert"),
        pytest.param("hide_public_candidate_for_low_information", _run_hide_public_candidate, id="hide"),
    ],
)
def test_pulse_candidate_returning_writes_require_cursor_rowcount(
    operation: str,
    invoke: Callable[[PulseCandidatesRepository], dict[str, Any] | None],
) -> None:
    del operation
    conn = PulseCandidateReturningConnection(rows=[_candidate_row()])

    with pytest.raises(TypeError, match="pulse_candidates_repository_rowcount_required"):
        invoke(PulseCandidatesRepository(conn))


@pytest.mark.parametrize(
    ("operation", "invoke"),
    [
        pytest.param("upsert_candidate", _run_upsert_candidate, id="upsert"),
        pytest.param("hide_public_candidate_for_low_information", _run_hide_public_candidate, id="hide"),
    ],
)
@pytest.mark.parametrize(
    ("rowcount", "rows", "expected_error"),
    [
        pytest.param(True, [_candidate_row()], "invalid", id="bool-true"),
        pytest.param(False, [], "invalid", id="bool-false"),
        pytest.param("1", [_candidate_row()], "invalid", id="numeric-string"),
        pytest.param(-1, [], "invalid", id="negative"),
        pytest.param(2, [_candidate_row()], "invalid", id="multi-row"),
        pytest.param(0, [_candidate_row()], "invalid", id="zero-with-row"),
        pytest.param(1, [], "invalid", id="one-without-row"),
    ],
)
def test_pulse_candidate_returning_writes_reject_invalid_or_mismatched_rowcount(
    operation: str,
    invoke: Callable[[PulseCandidatesRepository], dict[str, Any] | None],
    rowcount: object,
    rows: list[dict[str, Any]],
    expected_error: str,
) -> None:
    del operation
    conn = PulseCandidateReturningConnection(rows=rows, rowcount=rowcount)

    with pytest.raises(TypeError, match=f"pulse_candidates_repository_rowcount_{expected_error}"):
        invoke(PulseCandidatesRepository(conn))


@pytest.mark.parametrize(
    ("operation", "invoke"),
    [
        pytest.param("upsert_candidate", _run_upsert_candidate, id="upsert"),
        pytest.param("hide_public_candidate_for_low_information", _run_hide_public_candidate, id="hide"),
    ],
)
def test_pulse_candidate_returning_writes_accept_valid_single_rowcount(
    operation: str,
    invoke: Callable[[PulseCandidatesRepository], dict[str, Any] | None],
) -> None:
    del operation
    conn = PulseCandidateReturningConnection(rows=[_candidate_row()], rowcount=1)
    row = invoke(PulseCandidatesRepository(conn))

    assert row is not None
    assert row["candidate_id"] == "candidate-1"


@pytest.mark.parametrize(
    ("operation", "invoke"),
    [
        pytest.param("upsert_candidate", _run_upsert_candidate, id="upsert"),
        pytest.param("hide_public_candidate_for_low_information", _run_hide_public_candidate, id="hide"),
    ],
)
def test_pulse_candidate_returning_writes_accept_zero_rowcount_without_fallback_select(
    operation: str,
    invoke: Callable[[PulseCandidatesRepository], dict[str, Any] | None],
) -> None:
    del operation
    conn = PulseCandidateReturningConnection(rows=[], rowcount=0)

    assert invoke(PulseCandidatesRepository(conn)) is None
    assert len(conn.sql) == 1
