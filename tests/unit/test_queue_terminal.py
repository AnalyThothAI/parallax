from __future__ import annotations

import copy
from typing import Any

from gmgn_twitter_intel.app.runtime.queue_terminal import (
    inspect_terminal_events,
    resolve_terminal_event,
    terminalize_source_row,
)


def test_terminalize_source_row_is_idempotent_when_payload_hash_is_missing_or_empty() -> None:
    conn = _FakeTerminalConnection()
    first = terminalize_source_row(
        conn,
        worker_name="resolution_refresh",
        source_table="token_discovery_dirty_lookup_keys",
        target_key="okx_dex_search:bonk",
        source_row={
            "provider": "okx_dex_search",
            "lookup_key": "bonk",
            "payload_hash": None,
            "attempt_count": 4,
        },
        final_status="dead",
        final_reason="retry_budget_exhausted",
        now_ms=1_700_000_000_000,
    )
    second = terminalize_source_row(
        conn,
        worker_name="resolution_refresh",
        source_table="token_discovery_dirty_lookup_keys",
        target_key="okx_dex_search:bonk",
        source_row={
            "provider": "okx_dex_search",
            "lookup_key": "bonk",
            "payload_hash": "",
            "attempt_count": 4,
        },
        final_status="dead",
        final_reason="retry_budget_exhausted",
        now_ms=1_700_000_000_500,
    )

    assert second["terminal_id"] == first["terminal_id"]
    assert len(conn.rows) == 1
    assert conn.rows[0]["payload_hash"] == ""
    assert conn.rows[0]["source_row_json"]["payload_hash"] == ""
    assert conn.rows[0]["source_row_hash"].startswith("sha256:")


def test_terminalize_source_row_reopens_resolved_snapshot_on_new_terminal_attempt() -> None:
    conn = _FakeTerminalConnection()
    first = terminalize_source_row(
        conn,
        worker_name="resolution_refresh",
        source_table="token_discovery_dirty_lookup_keys",
        target_key="okx_dex_search:symbol:BONK",
        source_row={
            "provider": "okx_dex_search",
            "lookup_key": "symbol:BONK",
            "payload_hash": "hash-bonk",
            "attempt_count": 3,
        },
        final_status="error",
        final_reason="provider_error_retry_budget_exhausted",
        now_ms=1_700_000_000_000,
    )
    conn.rows[0].update(
        {
            "operator_action": "retry",
            "operator_reason": "operator retry",
            "operator_action_at_ms": 1_700_000_010_000,
        }
    )

    second = terminalize_source_row(
        conn,
        worker_name="resolution_refresh",
        source_table="token_discovery_dirty_lookup_keys",
        target_key="okx_dex_search:symbol:BONK",
        source_row={
            "provider": "okx_dex_search",
            "lookup_key": "symbol:BONK",
            "payload_hash": "hash-bonk",
            "attempt_count": 3,
        },
        final_status="error",
        final_reason="provider_error_retry_budget_exhausted",
        now_ms=1_700_000_020_000,
    )

    assert second["terminal_id"] != first["terminal_id"]
    assert len(conn.rows) == 2
    assert conn.rows[0]["operator_action"] == "retry"
    assert conn.rows[0]["operator_reason"] == "operator retry"
    assert conn.rows[1]["operator_action"] is None
    assert conn.rows[1]["operator_reason"] is None
    assert conn.rows[1]["operator_action_at_ms"] is None
    assert conn.rows[1]["attempt_count"] == 3
    assert conn.rows[1]["terminal_generation"] == 2
    assert conn.rows[1]["terminalized_at_ms"] == 1_700_000_020_000


def test_inspect_terminal_events_filters_unresolved_terminal_rows() -> None:
    conn = _FakeTerminalConnection()
    conn.rows = [
        _terminal_row("terminal-1", worker_name="resolution_refresh", source_table="lookup", target_key="a"),
        _terminal_row(
            "terminal-2",
            worker_name="resolution_refresh",
            source_table="other",
            target_key="b",
            operator_action="archive",
        ),
        _terminal_row("terminal-3", worker_name="pulse", source_table="lookup", target_key="c"),
    ]

    payload = inspect_terminal_events(
        conn,
        worker_name="resolution_refresh",
        source_table="lookup",
        status="terminal",
        limit=10,
    )

    assert payload["status"] == "terminal"
    assert payload["count"] == 1
    assert [row["terminal_id"] for row in payload["items"]] == ["terminal-1"]


def test_inspect_terminal_events_excludes_quarantine_from_unresolved_terminal_rows() -> None:
    conn = _FakeTerminalConnection()
    conn.rows = [
        _terminal_row(
            "terminal-1",
            worker_name="resolution_refresh",
            source_table="lookup",
            target_key="a",
            operator_action="quarantine",
        )
    ]

    unresolved = inspect_terminal_events(
        conn,
        worker_name="resolution_refresh",
        source_table="lookup",
        status="terminal",
        limit=10,
    )
    active = inspect_terminal_events(
        conn,
        worker_name="resolution_refresh",
        source_table="lookup",
        status="active",
        limit=10,
    )

    assert unresolved["count"] == 0
    assert active["count"] == 1
    assert active["items"][0]["operator_action"] == "quarantine"


def test_resolve_terminal_event_retry_marks_action_before_transition_and_uses_snapshot() -> None:
    conn = _FakeTerminalConnection()
    conn.rows = [
        _terminal_row(
            "terminal-1",
            worker_name="resolution_refresh",
            source_table="token_discovery_dirty_lookup_keys",
            target_key="okx_dex_search:bonk",
            source_row_json={"provider": "okx_dex_search", "lookup_key": "bonk", "payload_hash": ""},
        )
    ]
    calls: list[dict[str, Any]] = []

    def retry_transition(event: dict[str, Any], *, now_ms: int, reason: str) -> dict[str, Any]:
        calls.append({"event": event, "now_ms": now_ms, "reason": reason})
        assert conn.rows[0]["operator_action"] == "retry"
        return {"requeued": 1}

    payload = resolve_terminal_event(
        conn,
        terminal_id="terminal-1",
        action="retry",
        reason="operator checked source row",
        now_ms=1_700_000_100_000,
        retry_transitions={
            ("resolution_refresh", "token_discovery_dirty_lookup_keys"): retry_transition,
        },
    )

    assert payload["operator_action"] == "retry"
    assert payload["transition"] == {"requeued": 1}
    assert calls == [
        {
            "event": {
                **conn.rows[0],
                "operator_action": "retry",
                "operator_reason": "operator checked source row",
                "operator_action_at_ms": 1_700_000_100_000,
            },
            "now_ms": 1_700_000_100_000,
            "reason": "operator checked source row",
        }
    ]
    assert conn.commits == 1


def test_resolve_terminal_event_retry_rolls_back_operator_action_when_transition_fails() -> None:
    conn = _FakeTerminalConnection()
    conn.rows = [
        _terminal_row(
            "terminal-1",
            worker_name="resolution_refresh",
            source_table="token_discovery_dirty_lookup_keys",
            target_key="okx_dex_search:bonk",
            source_row_json={"provider": "okx_dex_search", "lookup_key": "bonk", "payload_hash": ""},
        )
    ]

    def retry_transition(_event: dict[str, Any], *, now_ms: int, reason: str) -> dict[str, Any]:
        raise ValueError("discovery_lookup_retry_not_requeued")

    try:
        resolve_terminal_event(
            conn,
            terminal_id="terminal-1",
            action="retry",
            reason="operator checked source row",
            now_ms=1_700_000_100_000,
            retry_transitions={
                ("resolution_refresh", "token_discovery_dirty_lookup_keys"): retry_transition,
            },
        )
    except ValueError as exc:
        assert str(exc) == "discovery_lookup_retry_not_requeued"
    else:
        raise AssertionError("expected retry transition failure")

    assert conn.rows[0]["operator_action"] is None
    assert conn.rows[0]["operator_reason"] is None
    assert conn.commits == 0
    assert conn.rollbacks == 1


def test_resolve_terminal_event_archive_does_not_call_retry_transition() -> None:
    conn = _FakeTerminalConnection()
    conn.rows = [_terminal_row("terminal-1", worker_name="pulse", source_table="pulse_agent_jobs", target_key="job-1")]

    payload = resolve_terminal_event(
        conn,
        terminal_id="terminal-1",
        action="archive",
        reason="obsolete terminal row",
        now_ms=1_700_000_100_000,
        retry_transitions={
            ("pulse", "pulse_agent_jobs"): lambda *_args, **_kwargs: {"requeued": 1},
        },
    )

    assert payload["operator_action"] == "archive"
    assert "transition" not in payload
    assert conn.rows[0]["operator_reason"] == "obsolete terminal row"


def _terminal_row(
    terminal_id: str,
    *,
    worker_name: str,
    source_table: str,
    target_key: str,
    source_row_json: dict[str, Any] | None = None,
    operator_action: str | None = None,
) -> dict[str, Any]:
    return {
        "terminal_id": terminal_id,
        "worker_name": worker_name,
        "source_table": source_table,
        "target_key": target_key,
        "source_row_json": source_row_json or {"target_key": target_key},
        "source_row_hash": f"sha256:{terminal_id}",
        "final_status": "dead",
        "final_reason": "retry_budget_exhausted",
        "attempt_count": 4,
        "payload_hash": "",
        "first_seen_at_ms": None,
        "last_attempted_at_ms": None,
        "terminalized_at_ms": 1_700_000_000_000,
        "terminal_generation": 1,
        "operator_action": operator_action,
        "operator_reason": "done" if operator_action else None,
        "operator_action_at_ms": 1_700_000_000_001 if operator_action else None,
    }


class _FakeCursor:
    def __init__(self, rows: list[dict[str, Any]], rowcount: int = 0) -> None:
        self._rows = rows
        self.rowcount = rowcount

    def fetchall(self) -> list[dict[str, Any]]:
        return self._rows

    def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None


class _FakeTerminalConnection:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self.commits = 0
        self.rollbacks = 0

    def transaction(self) -> _FakeTransaction:
        return _FakeTransaction(self)

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> _FakeCursor:
        params = dict(params or {})
        normalized = " ".join(sql.split()).lower()
        if "select terminal_generation" in normalized:
            rows = [
                row
                for row in self.rows
                if row["worker_name"] == params["worker_name"]
                and row["source_table"] == params["source_table"]
                and row["target_key"] == params["target_key"]
                and row["operator_action"] is None
            ]
            return _FakeCursor(rows[:1])
        if "select coalesce(max(terminal_generation)" in normalized:
            generations = [
                int(row["terminal_generation"])
                for row in self.rows
                if row["worker_name"] == params["worker_name"]
                and row["source_table"] == params["source_table"]
                and row["target_key"] == params["target_key"]
                and row["source_row_hash"] == params["source_row_hash"]
            ]
            return _FakeCursor([{"terminal_generation": (max(generations) if generations else 0) + 1}])
        if "insert into worker_queue_terminal_events" in normalized:
            existing = next(
                (
                    row
                    for row in self.rows
                    if row["worker_name"] == params["worker_name"]
                    and row["source_table"] == params["source_table"]
                    and row["target_key"] == params["target_key"]
                    and row["operator_action"] is None
                ),
                None,
            )
            if existing is None:
                existing = {
                    "terminal_id": params["terminal_id"],
                    "worker_name": params["worker_name"],
                    "source_table": params["source_table"],
                    "target_key": params["target_key"],
                    "source_row_json": _json_obj(params["source_row_json"]),
                    "source_row_hash": params["source_row_hash"],
                    "final_status": params["final_status"],
                    "final_reason": params["final_reason"],
                    "attempt_count": params["attempt_count"],
                    "payload_hash": params["payload_hash"],
                    "first_seen_at_ms": params["first_seen_at_ms"],
                    "last_attempted_at_ms": params["last_attempted_at_ms"],
                    "terminalized_at_ms": params["terminalized_at_ms"],
                    "terminal_generation": params["terminal_generation"],
                    "operator_action": None,
                    "operator_reason": None,
                    "operator_action_at_ms": None,
                }
                self.rows.append(existing)
            else:
                existing.update(
                    {
                        "terminal_id": params["terminal_id"],
                        "source_row_json": _json_obj(params["source_row_json"]),
                        "source_row_hash": params["source_row_hash"],
                        "final_status": params["final_status"],
                        "final_reason": params["final_reason"],
                        "attempt_count": max(existing["attempt_count"], params["attempt_count"]),
                        "payload_hash": params["payload_hash"],
                        "last_attempted_at_ms": params["last_attempted_at_ms"]
                        or existing["last_attempted_at_ms"],
                        "terminalized_at_ms": params["terminalized_at_ms"],
                    }
                )
            return _FakeCursor([existing], rowcount=1)
        if "select" in normalized and "from worker_queue_terminal_events" in normalized:
            rows = list(self.rows)
            if "terminal_id = %(terminal_id)s" in normalized:
                rows = [row for row in rows if row["terminal_id"] == params["terminal_id"]]
            if params.get("worker_name"):
                rows = [row for row in rows if row["worker_name"] == params["worker_name"]]
            if params.get("source_table"):
                rows = [row for row in rows if row["source_table"] == params["source_table"]]
            if "operator_action is null" in normalized:
                rows = [row for row in rows if row["operator_action"] is None]
            rows.sort(key=lambda row: (-int(row["terminalized_at_ms"]), row["terminal_id"]))
            return _FakeCursor(rows[: int(params.get("limit") or len(rows))])
        if "update worker_queue_terminal_events" in normalized:
            row = next((item for item in self.rows if item["terminal_id"] == params["terminal_id"]), None)
            if row is None:
                return _FakeCursor([], rowcount=0)
            row.update(
                {
                    "operator_action": params["operator_action"],
                    "operator_reason": params["operator_reason"],
                    "operator_action_at_ms": params["operator_action_at_ms"],
                }
            )
            return _FakeCursor([row], rowcount=1)
        raise AssertionError(f"unexpected SQL: {sql}")

    def commit(self) -> None:
        self.commits += 1


class _FakeTransaction:
    def __init__(self, conn: _FakeTerminalConnection) -> None:
        self.conn = conn
        self._rows: list[dict[str, Any]] = []

    def __enter__(self) -> _FakeTransaction:
        self._rows = copy.deepcopy(self.conn.rows)
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        if exc_type is not None:
            self.conn.rows = self._rows
            self.conn.rollbacks += 1
            return False
        self.conn.commits += 1
        return False


def _json_obj(value: Any) -> Any:
    return getattr(value, "obj", value)
