from __future__ import annotations

from typing import Any

import pytest

from parallax.domains.token_intel.repositories.signal_repository import SignalRepository


def test_signal_repository_alert_insert_requires_connection_transaction_before_sql_when_committing():
    conn = NoTransactionConn(rowcount=1)

    with pytest.raises(RuntimeError, match="signal_repository_transaction_required"):
        SignalRepository(conn).insert_account_token_alert(
            event_id="event-1",
            author_handle="alice",
            entity_key="asset:1",
            entity_type="Asset",
            normalized_value="PEPE",
            chain=None,
            token_resolution_status="EXACT",
            is_first_seen_global=True,
            is_first_seen_by_author=True,
            received_at_ms=1_700_000_000_000,
        )

    assert conn.sqls == []


def test_signal_repository_alert_insert_uses_connection_transaction_without_manual_commit():
    conn = FakeConn(rowcount=1)

    alert = SignalRepository(conn).insert_account_token_alert(
        event_id="event-1",
        author_handle="alice",
        entity_key="asset:1",
        entity_type="Asset",
        normalized_value="PEPE",
        chain=None,
        token_resolution_status="EXACT",
        is_first_seen_global=True,
        is_first_seen_by_author=True,
        received_at_ms=1_700_000_000_000,
    )

    assert alert is not None
    assert "INSERT INTO account_token_alerts" in conn.sql
    assert conn.sql_transaction_depths == [1]
    assert conn.transaction_enter_count == 1
    assert conn.transaction_exit_count == 1
    assert conn.commit_count == 0


def test_signal_repository_caller_owned_alert_insert_does_not_open_inner_transaction():
    conn = FakeConn(rowcount=1)

    SignalRepository(conn).insert_account_token_alert(
        event_id="event-1",
        author_handle="alice",
        entity_key="asset:1",
        entity_type="Asset",
        normalized_value="PEPE",
        chain=None,
        token_resolution_status="EXACT",
        is_first_seen_global=True,
        is_first_seen_by_author=True,
        received_at_ms=1_700_000_000_000,
        commit=False,
    )

    assert conn.sql_transaction_depths == [0]
    assert conn.transaction_enter_count == 0
    assert conn.commit_count == 0


def test_signal_repository_alert_insert_requires_cursor_rowcount() -> None:
    conn = FakeConn(omit_rowcount=True)

    with pytest.raises(TypeError, match="signal_repository_rowcount_required"):
        SignalRepository(conn).insert_account_token_alert(
            event_id="event-1",
            author_handle="alice",
            entity_key="asset:1",
            entity_type="Asset",
            normalized_value="PEPE",
            chain=None,
            token_resolution_status="EXACT",
            is_first_seen_global=True,
            is_first_seen_by_author=True,
            received_at_ms=1_700_000_000_000,
            commit=False,
        )


@pytest.mark.parametrize("rowcount", ["bad", True, -1, 2])
def test_signal_repository_alert_insert_rejects_invalid_cursor_rowcount(rowcount: object) -> None:
    conn = FakeConn(rowcount=rowcount)

    with pytest.raises(TypeError, match="signal_repository_rowcount_invalid"):
        SignalRepository(conn).insert_account_token_alert(
            event_id="event-1",
            author_handle="alice",
            entity_key="asset:1",
            entity_type="Asset",
            normalized_value="PEPE",
            chain=None,
            token_resolution_status="EXACT",
            is_first_seen_global=True,
            is_first_seen_by_author=True,
            received_at_ms=1_700_000_000_000,
            commit=False,
        )


class FakeTransaction:
    def __init__(self, conn: FakeConn) -> None:
        self.conn = conn

    def __enter__(self):
        self.conn.transaction_enter_count += 1
        self.conn.transaction_depth += 1
        return self

    def __exit__(self, exc_type, exc, tb):
        self.conn.transaction_depth -= 1
        self.conn.transaction_exit_count += 1
        return False


class FakeConn:
    def __init__(self, *, rowcount: object = 1, omit_rowcount: bool = False) -> None:
        if not omit_rowcount:
            self.rowcount = rowcount
        self.sql = ""
        self.sqls: list[str] = []
        self.params: Any = ()
        self.commit_count = 0
        self.transaction_enter_count = 0
        self.transaction_exit_count = 0
        self.transaction_depth = 0
        self.sql_transaction_depths: list[int] = []

    def execute(self, sql, params=None):
        self.sql = str(sql)
        self.sqls.append(self.sql)
        self.sql_transaction_depths.append(self.transaction_depth)
        self.params = params or ()
        return self

    def fetchall(self):
        return []

    def commit(self):
        self.commit_count += 1
        raise AssertionError("manual commit is not allowed in repository tests")

    def transaction(self):
        return FakeTransaction(self)


class NoTransactionConn(FakeConn):
    transaction = None
