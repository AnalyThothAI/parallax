from __future__ import annotations

import copy
from typing import Any

import pytest

from parallax.platform.db.queue_terminal import (
    inspect_terminal_events,
    list_terminal_event_ids,
    resolve_terminal_event,
    terminal_reason_bucket,
    terminalize_source_row,
)


def test_terminal_reason_bucket_normalizes_operator_triage_reasons() -> None:
    assert terminal_reason_bucket("deepseek provider 522 gateway") == "llm_provider_522"
    assert terminal_reason_bucket("stale_running_timeout") == "stale_window_ttl"
    assert terminal_reason_bucket("provider_error_retry_budget_exhausted") == "retry_budget_exhausted"
    assert terminal_reason_bucket("provider_unavailable: transport failed") == "provider_unavailable"
    assert terminal_reason_bucket("provider_no_quote:empty") == "provider_no_quote"
    assert terminal_reason_bucket("semantic parse unavailable") == "semantic_unavailable"
    assert terminal_reason_bucket("unexpected") == "other"


def test_terminalize_source_row_stores_final_reason_bucket() -> None:
    conn = _FakeTerminalConnection()

    row = terminalize_source_row(
        conn,
        worker_name="resolution_refresh",
        source_table="token_discovery_dirty_lookup_keys",
        target_key="okx_dex_search:bonk",
        source_row={
            "provider": "okx_dex_search",
            "lookup_key": "bonk",
            "attempt_count": 4,
        },
        final_status="dead",
        final_reason="provider_error_retry_budget_exhausted",
        now_ms=1_700_000_000_000,
    )

    assert row["final_reason_bucket"] == "retry_budget_exhausted"
    assert conn.rows[0]["final_reason_bucket"] == "retry_budget_exhausted"


def test_terminalize_source_row_requires_connection_transaction_when_committing() -> None:
    conn = _ConnectionWithoutTransaction()

    try:
        terminalize_source_row(
            conn,
            worker_name="resolution_refresh",
            source_table="token_discovery_dirty_lookup_keys",
            target_key="okx_dex_search:bonk",
            source_row={
                "provider": "okx_dex_search",
                "lookup_key": "bonk",
                "attempt_count": 4,
            },
            final_status="dead",
            final_reason="provider_error_retry_budget_exhausted",
            now_ms=1_700_000_000_000,
            commit=True,
        )
    except RuntimeError as exc:
        assert str(exc) == "queue_terminal_transaction_required"
    else:
        raise AssertionError("expected missing transaction contract failure")

    assert conn.sql == []
    assert conn.rows == []
    assert conn.commits == 0


def test_terminalize_source_row_requires_attempt_contract_before_sql() -> None:
    conn = _ConnectionWithoutTransaction()

    try:
        terminalize_source_row(
            conn,
            worker_name="resolution_refresh",
            source_table="token_discovery_dirty_lookup_keys",
            target_key="okx_dex_search:bonk",
            source_row={
                "provider": "okx_dex_search",
                "lookup_key": "bonk",
            },
            final_status="dead",
            final_reason="provider_error_retry_budget_exhausted",
            now_ms=1_700_000_000_000,
        )
    except RuntimeError as exc:
        assert str(exc) == "queue_terminal_attempt_contract_required"
    else:
        raise AssertionError("expected missing attempt contract failure")

    assert conn.sql == []
    assert conn.rows == []


def test_terminalize_source_row_requires_existing_terminal_generation_contract() -> None:
    conn = _ConnectionWithoutTransaction()
    existing = _terminal_row(
        "terminal-1",
        worker_name="resolution_refresh",
        source_table="token_discovery_dirty_lookup_keys",
        target_key="okx_dex_search:bonk",
    )
    del existing["terminal_generation"]
    conn.rows = [existing]

    try:
        terminalize_source_row(
            conn,
            worker_name="resolution_refresh",
            source_table="token_discovery_dirty_lookup_keys",
            target_key="okx_dex_search:bonk",
            source_row={
                "provider": "okx_dex_search",
                "lookup_key": "bonk",
                "attempt_count": 4,
            },
            final_status="dead",
            final_reason="provider_error_retry_budget_exhausted",
            now_ms=1_700_000_000_000,
        )
    except RuntimeError as exc:
        assert str(exc) == "queue_terminal_generation_contract_required"
    else:
        raise AssertionError("expected malformed terminal generation failure")

    assert len(conn.sql) == 1
    assert conn.rows == [existing]


def test_terminalize_source_row_returning_requires_cursor_rowcount() -> None:
    conn = _FakeTerminalConnection(omit_returning_rowcount=True)

    with pytest.raises(TypeError, match="queue_terminal_rowcount_required"):
        terminalize_source_row(
            conn,
            worker_name="resolution_refresh",
            source_table="token_discovery_dirty_lookup_keys",
            target_key="okx_dex_search:bonk",
            source_row={
                "provider": "okx_dex_search",
                "lookup_key": "bonk",
                "attempt_count": 4,
            },
            final_status="dead",
            final_reason="provider_error_retry_budget_exhausted",
            now_ms=1_700_000_000_000,
        )


@pytest.mark.parametrize("rowcount", [True, False, "1", None, -1, 0, 2])
def test_terminalize_source_row_returning_rejects_invalid_or_mismatched_rowcount(rowcount: object) -> None:
    conn = _FakeTerminalConnection(returning_rowcount=rowcount)

    with pytest.raises(TypeError, match="queue_terminal_rowcount_invalid"):
        terminalize_source_row(
            conn,
            worker_name="resolution_refresh",
            source_table="token_discovery_dirty_lookup_keys",
            target_key="okx_dex_search:bonk",
            source_row={
                "provider": "okx_dex_search",
                "lookup_key": "bonk",
                "attempt_count": 4,
            },
            final_status="dead",
            final_reason="provider_error_retry_budget_exhausted",
            now_ms=1_700_000_000_000,
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
    assert conn.rows[0]["final_reason_bucket"] == "retry_budget_exhausted"


def test_terminalize_source_row_keeps_bucket_stable_until_final_reason_changes() -> None:
    conn = _FakeTerminalConnection()
    first = terminalize_source_row(
        conn,
        worker_name="resolution_refresh",
        source_table="token_discovery_dirty_lookup_keys",
        target_key="okx_dex_search:bonk",
        source_row={"provider": "okx_dex_search", "lookup_key": "bonk", "attempt_count": 2},
        final_status="dead",
        final_reason="retry_budget_exhausted",
        final_reason_bucket="custom_bucket",
        now_ms=1_700_000_000_000,
    )

    same_reason = terminalize_source_row(
        conn,
        worker_name="resolution_refresh",
        source_table="token_discovery_dirty_lookup_keys",
        target_key="okx_dex_search:bonk",
        source_row={"provider": "okx_dex_search", "lookup_key": "bonk", "attempt_count": 3},
        final_status="dead",
        final_reason="retry_budget_exhausted",
        final_reason_bucket="other",
        now_ms=1_700_000_000_500,
    )
    changed_reason = terminalize_source_row(
        conn,
        worker_name="resolution_refresh",
        source_table="token_discovery_dirty_lookup_keys",
        target_key="okx_dex_search:bonk",
        source_row={"provider": "okx_dex_search", "lookup_key": "bonk", "attempt_count": 4},
        final_status="dead",
        final_reason="provider_no_quote:empty",
        now_ms=1_700_000_001_000,
    )

    assert first["final_reason_bucket"] == "custom_bucket"
    assert same_reason["final_reason_bucket"] == "custom_bucket"
    assert changed_reason["final_reason_bucket"] == "provider_no_quote"


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
        _terminal_row("terminal-3", worker_name="projection", source_table="lookup", target_key="c"),
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


def test_inspect_terminal_events_filters_by_reason_bucket() -> None:
    conn = _FakeTerminalConnection()
    conn.rows = [
        _terminal_row(
            "terminal-1",
            worker_name="resolution_refresh",
            source_table="lookup",
            target_key="a",
            final_reason_bucket="llm_provider_522",
        ),
        _terminal_row(
            "terminal-2",
            worker_name="resolution_refresh",
            source_table="lookup",
            target_key="b",
            final_reason_bucket="timeout",
        ),
    ]

    payload = inspect_terminal_events(
        conn,
        worker_name="resolution_refresh",
        source_table="lookup",
        status="terminal",
        reason_bucket="llm_provider_522",
        limit=10,
    )

    assert payload["reason_bucket"] == "llm_provider_522"
    assert payload["count"] == 1
    assert payload["items"][0]["terminal_id"] == "terminal-1"


def test_list_terminal_event_ids_filters_unresolved_bucket() -> None:
    conn = _FakeTerminalConnection()
    conn.rows = [
        _terminal_row(
            "terminal-1",
            worker_name="resolution_refresh",
            source_table="token_discovery_dirty_lookup_keys",
            target_key="a",
            final_reason_bucket="retry_budget_exhausted",
        ),
        _terminal_row(
            "terminal-2",
            worker_name="resolution_refresh",
            source_table="token_discovery_dirty_lookup_keys",
            target_key="b",
            final_reason_bucket="retry_budget_exhausted",
            operator_action="archive",
        ),
        _terminal_row(
            "terminal-3",
            worker_name="event_anchor_backfill",
            source_table="event_anchor_backfill_jobs",
            target_key="c",
            final_reason_bucket="retry_budget_exhausted",
        ),
        _terminal_row(
            "terminal-4",
            worker_name="resolution_refresh",
            source_table="token_discovery_dirty_lookup_keys",
            target_key="d",
            final_reason_bucket="provider_error",
        ),
    ]

    terminal_ids = list_terminal_event_ids(
        conn,
        worker_name="resolution_refresh",
        source_table="token_discovery_dirty_lookup_keys",
        reason_bucket="retry_budget_exhausted",
        limit=10,
    )

    assert terminal_ids == ["terminal-1"]


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


def test_resolve_terminal_event_returning_rowcount_is_checked_before_retry_transition() -> None:
    conn = _FakeTerminalConnection(omit_returning_rowcount=True)
    conn.rows = [
        _terminal_row(
            "terminal-1",
            worker_name="resolution_refresh",
            source_table="token_discovery_dirty_lookup_keys",
            target_key="okx_dex_search:bonk",
            source_row_json={"provider": "okx_dex_search", "lookup_key": "bonk", "payload_hash": ""},
        )
    ]
    calls: list[str] = []

    def retry_transition(_event: dict[str, Any], *, now_ms: int, reason: str) -> dict[str, Any]:
        calls.append("called")
        return {"requeued": 1}

    with pytest.raises(TypeError, match="queue_terminal_rowcount_required"):
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

    assert calls == []
    assert conn.rows[0]["operator_action"] is None
    assert conn.rows[0]["operator_reason"] is None
    assert conn.commits == 0
    assert conn.rollbacks == 1


def test_resolve_terminal_event_archive_does_not_call_retry_transition() -> None:
    conn = _FakeTerminalConnection()
    conn.rows = [_terminal_row("terminal-1", worker_name="worker", source_table="work_items", target_key="job-1")]

    payload = resolve_terminal_event(
        conn,
        terminal_id="terminal-1",
        action="archive",
        reason="obsolete terminal row",
        now_ms=1_700_000_100_000,
        retry_transitions={
            ("worker", "work_items"): lambda *_args, **_kwargs: {"requeued": 1},
        },
    )

    assert payload["operator_action"] == "archive"
    assert "transition" not in payload
    assert conn.rows[0]["operator_reason"] == "obsolete terminal row"


def test_resolve_terminal_event_requires_connection_transaction_before_operator_action() -> None:
    conn = _ConnectionWithoutTransaction()
    conn.rows = [
        _terminal_row(
            "terminal-1",
            worker_name="resolution_refresh",
            source_table="token_discovery_dirty_lookup_keys",
            target_key="okx_dex_search:bonk",
            source_row_json={"provider": "okx_dex_search", "lookup_key": "bonk", "payload_hash": ""},
        )
    ]

    try:
        resolve_terminal_event(
            conn,
            terminal_id="terminal-1",
            action="archive",
            reason="operator checked source row",
            now_ms=1_700_000_100_000,
        )
    except RuntimeError as exc:
        assert str(exc) == "queue_terminal_transaction_required"
    else:
        raise AssertionError("expected missing transaction contract failure")

    assert conn.sql == []
    assert conn.rows[0]["operator_action"] is None
    assert conn.commits == 0


def _terminal_row(
    terminal_id: str,
    *,
    worker_name: str,
    source_table: str,
    target_key: str,
    source_row_json: dict[str, Any] | None = None,
    operator_action: str | None = None,
    final_reason_bucket: str = "other",
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
        "final_reason_bucket": final_reason_bucket,
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
    def __init__(self, rows: list[dict[str, Any]], rowcount: object = 0, omit_rowcount: bool = False) -> None:
        self._rows = rows
        if not omit_rowcount:
            self.rowcount = rowcount

    def fetchall(self) -> list[dict[str, Any]]:
        return self._rows

    def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None


class _FakeTerminalConnection:
    def __init__(self, *, returning_rowcount: object = 1, omit_returning_rowcount: bool = False) -> None:
        self.rows: list[dict[str, Any]] = []
        self.commits = 0
        self.rollbacks = 0
        self.returning_rowcount = returning_rowcount
        self.omit_returning_rowcount = omit_returning_rowcount

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
                    "final_reason_bucket": params["final_reason_bucket"],
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
                        "final_reason_bucket": (
                            params["final_reason_bucket"]
                            if existing["final_reason"] != params["final_reason"]
                            else existing["final_reason_bucket"]
                        ),
                        "attempt_count": max(existing["attempt_count"], params["attempt_count"]),
                        "payload_hash": params["payload_hash"],
                        "last_attempted_at_ms": params["last_attempted_at_ms"] or existing["last_attempted_at_ms"],
                        "terminalized_at_ms": params["terminalized_at_ms"],
                    }
                )
            return _FakeCursor(
                [existing],
                rowcount=self.returning_rowcount,
                omit_rowcount=self.omit_returning_rowcount,
            )
        if "select" in normalized and "from worker_queue_terminal_events" in normalized:
            rows = list(self.rows)
            if "terminal_id = %(terminal_id)s" in normalized:
                rows = [row for row in rows if row["terminal_id"] == params["terminal_id"]]
            if params.get("worker_name"):
                rows = [row for row in rows if row["worker_name"] == params["worker_name"]]
            if params.get("source_table"):
                rows = [row for row in rows if row["source_table"] == params["source_table"]]
            if params.get("reason_bucket"):
                rows = [row for row in rows if row["final_reason_bucket"] == params["reason_bucket"]]
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
            return _FakeCursor(
                [row],
                rowcount=self.returning_rowcount,
                omit_rowcount=self.omit_returning_rowcount,
            )
        raise AssertionError(f"unexpected SQL: {sql}")

    def commit(self) -> None:
        self.commits += 1


class _ConnectionWithoutTransaction(_FakeTerminalConnection):
    transaction = None

    def __init__(self) -> None:
        super().__init__()
        self.sql: list[str] = []

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> _FakeCursor:
        self.sql.append(sql)
        return super().execute(sql, params)


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
