from __future__ import annotations

from typing import Any

import pytest

from parallax.domains.asset_market.repositories.cex_token_profile_repository import (
    BINANCE_CEX_PROFILE_PROVIDER,
    CexTokenProfileRepository,
)

_ROWCOUNT_MISSING = object()
_ROW_MISSING = object()


def test_cex_token_profile_mutation_requires_connection_transaction_before_sql_when_committing() -> None:
    conn = NoTransactionCexTokenProfileConnection()
    repo = CexTokenProfileRepository(conn)

    with pytest.raises(RuntimeError, match="cex_token_profile_repository_transaction_required"):
        _upsert_ready(repo)

    assert conn.sql == []
    assert conn.commits == 0


def test_cex_token_profile_commit_owned_write_uses_connection_transaction_without_manual_commit() -> None:
    conn = FakeCexTokenProfileConnection()
    repo = CexTokenProfileRepository(conn)

    row = _upsert_ready(repo)

    assert row == {"cex_token_id": "cex_token:BTC", "status": "ready"}
    assert conn.transaction_commits == 1
    assert conn.commits == 0
    assert conn.sql_depths == [1]


def test_cex_token_profile_returning_write_requires_cursor_rowcount() -> None:
    conn = FakeCexTokenProfileConnection(rowcount=_ROWCOUNT_MISSING)

    with pytest.raises(TypeError, match="cex_token_profile_repository_rowcount_required"):
        _upsert_ready(CexTokenProfileRepository(conn), commit=False)


@pytest.mark.parametrize(
    ("rowcount", "row"),
    [
        pytest.param(True, {"cex_token_id": "cex_token:BTC", "status": "ready"}, id="bool-true"),
        pytest.param(False, None, id="bool-false"),
        pytest.param("1", {"cex_token_id": "cex_token:BTC", "status": "ready"}, id="numeric-string"),
        pytest.param(-1, None, id="negative"),
        pytest.param(2, {"cex_token_id": "cex_token:BTC", "status": "ready"}, id="multi-row"),
        pytest.param(0, {"cex_token_id": "cex_token:BTC", "status": "ready"}, id="zero-with-row"),
        pytest.param(1, None, id="one-without-row"),
    ],
)
def test_cex_token_profile_returning_write_rejects_invalid_or_mismatched_rowcount(
    rowcount: object,
    row: dict[str, Any] | None,
) -> None:
    conn = FakeCexTokenProfileConnection(row=row, rowcount=rowcount)

    with pytest.raises(TypeError, match="cex_token_profile_repository_rowcount_invalid"):
        _upsert_ready(CexTokenProfileRepository(conn), commit=False)


def test_cex_token_profile_returning_write_accepts_zero_rowcount_without_existing_token() -> None:
    conn = FakeCexTokenProfileConnection(row=None, rowcount=0)

    assert _upsert_ready(CexTokenProfileRepository(conn), commit=False) is None


def test_cex_token_profile_returning_write_accepts_valid_single_rowcount() -> None:
    conn = FakeCexTokenProfileConnection(rowcount=1)

    assert _upsert_ready(CexTokenProfileRepository(conn), commit=False) == {
        "cex_token_id": "cex_token:BTC",
        "status": "ready",
    }


def _upsert_ready(repo: CexTokenProfileRepository, *, commit: bool = True) -> dict[str, Any] | None:
    return repo.upsert_ready_profile_if_token_exists(
        base_symbol="BTC",
        provider=BINANCE_CEX_PROFILE_PROVIDER,
        symbol="BTC",
        name="Bitcoin",
        logo_url="https://bin.bnbstatic.com/btc.png",
        source_ref="binance_marketing_symbol_list:BTC",
        raw_payload={"rank": 1},
        observed_at_ms=1_779_100_000_000,
        commit=commit,
    )


class FakeCexTokenProfileConnection:
    def __init__(
        self,
        *,
        row: dict[str, Any] | None | object = _ROW_MISSING,
        rowcount: object = 1,
    ) -> None:
        self.depth = 0
        self.commits = 0
        self.transaction_commits = 0
        self.sql_depths: list[int] = []
        if row is _ROW_MISSING:
            self.row: dict[str, Any] | None = {"cex_token_id": "cex_token:BTC", "status": "ready"}
        else:
            self.row = row if isinstance(row, dict) else None
        self.rowcount = rowcount

    def transaction(self) -> _Transaction:
        return _Transaction(self)

    def execute(self, sql: str, params: tuple[Any, ...]) -> _Result:
        assert "INSERT INTO cex_token_profiles" in sql
        assert params[0] == BINANCE_CEX_PROFILE_PROVIDER
        self.sql_depths.append(self.depth)
        return _Result(self.row, rowcount=self.rowcount)

    def commit(self) -> None:
        self.commits += 1
        raise AssertionError("repository-owned writes must use conn.transaction(), not conn.commit()")


class NoTransactionCexTokenProfileConnection:
    def __init__(self) -> None:
        self.sql: list[str] = []
        self.commits = 0

    def execute(self, sql: str, params: tuple[Any, ...]) -> _Result:
        self.sql.append(sql)
        return _Result({"cex_token_id": "cex_token:BTC", "status": "ready"})

    def commit(self) -> None:
        self.commits += 1


class _Transaction:
    def __init__(self, conn: FakeCexTokenProfileConnection) -> None:
        self.conn = conn

    def __enter__(self) -> _Transaction:
        self.conn.depth += 1
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        if exc_type is None:
            self.conn.transaction_commits += 1
        self.conn.depth -= 1
        return False


class _Result:
    def __init__(self, row: dict[str, Any] | None, *, rowcount: object = 1) -> None:
        self.row = row
        if rowcount is not _ROWCOUNT_MISSING:
            self.rowcount = rowcount

    def fetchone(self) -> dict[str, Any] | None:
        return self.row
