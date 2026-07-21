from __future__ import annotations

from typing import Any

import pytest

from parallax.domains.pulse_lab.repositories.pulse_playbooks_repository import PulsePlaybooksRepository

NOW_MS = 1_779_000_000_000
_ROWCOUNT_MISSING = object()


class PulsePlaybookReturningCursor:
    def __init__(self, rows: list[dict[str, Any]], *, rowcount: object = _ROWCOUNT_MISSING) -> None:
        self._rows = rows
        if rowcount is not _ROWCOUNT_MISSING:
            self.rowcount = rowcount

    def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None


class PulsePlaybookReturningConnection:
    def __init__(self, rows: list[dict[str, Any]], *, rowcount: object = _ROWCOUNT_MISSING) -> None:
        self.rows = rows
        self.rowcount = rowcount
        self.sql: list[str] = []

    def execute(self, sql: str, params: Any = None) -> PulsePlaybookReturningCursor:
        del params
        self.sql.append(sql)
        if "SELECT *" in sql:
            raise AssertionError("pulse_playbooks_repository must not restore write success with fallback SELECT")
        return PulsePlaybookReturningCursor(self.rows, rowcount=self.rowcount)


def _run_upsert_playbook_snapshot(repo: PulsePlaybooksRepository) -> dict[str, Any] | None:
    return repo.upsert_playbook_snapshot(
        playbook_id="playbook-1",
        candidate_id="candidate-1",
        horizon="1h",
        decision_time_ms=NOW_MS,
        playbook_status="active",
        side="long",
        setup={"reason": "setup"},
        confirmation={"signal": "confirm"},
        invalidation={"signal": "invalidate"},
        risk={"max_loss": 0.1},
        playbook_version="playbook-v1",
        commit=False,
    )


def _playbook_snapshot_row() -> dict[str, Any]:
    return {
        "playbook_id": "playbook-1",
        "candidate_id": "candidate-1",
        "horizon": "1h",
        "playbook_status": "active",
        "side": "long",
        "playbook_version": "playbook-v1",
    }


def test_pulse_playbook_returning_writes_require_cursor_rowcount() -> None:
    conn = PulsePlaybookReturningConnection(rows=[_playbook_snapshot_row()])

    with pytest.raises(TypeError, match="pulse_playbooks_repository_rowcount_required"):
        _run_upsert_playbook_snapshot(PulsePlaybooksRepository(conn))


@pytest.mark.parametrize(
    ("rowcount", "rows", "expected_error"),
    [
        pytest.param(True, [_playbook_snapshot_row()], "invalid", id="bool-true"),
        pytest.param(False, [], "invalid", id="bool-false"),
        pytest.param("1", [_playbook_snapshot_row()], "invalid", id="numeric-string"),
        pytest.param(-1, [], "invalid", id="negative"),
        pytest.param(2, [_playbook_snapshot_row()], "invalid", id="multi-row"),
        pytest.param(0, [_playbook_snapshot_row()], "invalid", id="zero-with-row"),
        pytest.param(1, [], "invalid", id="one-without-row"),
    ],
)
def test_pulse_playbook_snapshot_returning_writes_reject_invalid_or_mismatched_rowcount(
    rowcount: object,
    rows: list[dict[str, Any]],
    expected_error: str,
) -> None:
    conn = PulsePlaybookReturningConnection(rows=rows, rowcount=rowcount)

    with pytest.raises(TypeError, match=f"pulse_playbooks_repository_rowcount_{expected_error}"):
        _run_upsert_playbook_snapshot(PulsePlaybooksRepository(conn))


def test_pulse_playbook_returning_writes_accept_valid_single_rowcount() -> None:
    snapshot_conn = PulsePlaybookReturningConnection(rows=[_playbook_snapshot_row()], rowcount=1)

    snapshot = _run_upsert_playbook_snapshot(PulsePlaybooksRepository(snapshot_conn))

    assert snapshot is not None
    assert snapshot["playbook_id"] == "playbook-1"


def test_pulse_playbook_snapshot_noop_accepts_zero_rowcount_without_fallback_select() -> None:
    conn = PulsePlaybookReturningConnection(rows=[], rowcount=0)

    assert _run_upsert_playbook_snapshot(PulsePlaybooksRepository(conn)) is None
    assert len(conn.sql) == 1
