from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from parallax.domains.asset_market.repositories.registry_repository import RegistryRepository

NOW_MS = 1_779_000_000_000


def _registry_required_upsert_operations() -> list[Callable[[RegistryRepository], object]]:
    return [
        lambda repo: repo.upsert_cex_token(
            base_symbol="btc",
            source="binance_cex",
            observed_at_ms=NOW_MS,
        ),
        lambda repo: repo.upsert_chain_asset(
            chain_id="eth",
            address="0x999b49c0d1612e619a4a4f6280733184da025108",
            observed_at_ms=NOW_MS,
        ),
        lambda repo: repo.upsert_pricefeed(
            feed_type="cex_swap",
            provider="binance",
            subject_type="CexToken",
            subject_id="cex_token:BTC",
            native_market_id="btcusdt",
            base_cex_token_id="cex_token:BTC",
            base_symbol="btc",
            quote_symbol="usdt",
            observed_at_ms=NOW_MS,
        ),
        lambda repo: repo.upsert_us_equity_symbol(
            symbol="rklb",
            exchange="N",
            security_name="Rocket Lab USA, Inc. Common Stock",
            instrument_type="equity",
            source="nasdaq_trader",
            source_updated_at_ms=NOW_MS,
            raw_payload={"Symbol": "RKLB"},
            observed_at_ms=NOW_MS,
        ),
    ]


def test_deactivate_missing_us_equity_symbols_returning_counts_require_cursor_rowcount() -> None:
    conn = RegistryDeactivateRowcountConnection(omit_rowcount=True)

    with pytest.raises(TypeError, match="registry_repository_rowcount_invalid"):
        RegistryRepository(conn).deactivate_missing_us_equity_symbols(
            source="nasdaq_trader",
            active_symbols={"AAOI"},
            observed_at_ms=NOW_MS,
        )


@pytest.mark.parametrize("rowcount", [True, False, "1", None, -1, 0, 2])
def test_deactivate_missing_us_equity_symbols_returning_counts_reject_invalid_or_mismatched_rowcount(
    rowcount: Any,
) -> None:
    conn = RegistryDeactivateRowcountConnection(rowcount=rowcount)

    with pytest.raises(TypeError, match="registry_repository_rowcount_invalid"):
        RegistryRepository(conn).deactivate_missing_us_equity_symbols(
            source="nasdaq_trader",
            active_symbols={"AAOI"},
            observed_at_ms=NOW_MS,
        )


@pytest.mark.parametrize("operation", _registry_required_upsert_operations())
def test_registry_repository_upserts_require_cursor_rowcount(operation: Callable[[RegistryRepository], object]) -> None:
    conn = RegistryUpsertRowcountConnection(omit_rowcount=True)

    with pytest.raises(TypeError, match="registry_repository_rowcount_invalid"):
        operation(RegistryRepository(conn))


@pytest.mark.parametrize("operation", _registry_required_upsert_operations())
@pytest.mark.parametrize("rowcount", [True, False, "1", None, -1, 0, 2])
def test_registry_repository_upserts_reject_invalid_or_unexpected_rowcount(
    operation: Callable[[RegistryRepository], object],
    rowcount: Any,
) -> None:
    conn = RegistryUpsertRowcountConnection(rowcount=rowcount)

    with pytest.raises(TypeError, match="registry_repository_rowcount_invalid"):
        operation(RegistryRepository(conn))


@pytest.mark.parametrize("operation", _registry_required_upsert_operations())
def test_registry_repository_upserts_require_returned_row_when_rowcount_is_one(
    operation: Callable[[RegistryRepository], object],
) -> None:
    conn = RegistryUpsertRowcountConnection(rowcount=1, rows=[])

    with pytest.raises(TypeError, match="registry_repository_rowcount_invalid"):
        operation(RegistryRepository(conn))


_ROWCOUNT_FROM_ROWS = object()


class FakeCursor:
    def __init__(
        self,
        rows: list[dict[str, Any]],
        *,
        rowcount: Any = _ROWCOUNT_FROM_ROWS,
        omit_rowcount: bool = False,
    ) -> None:
        self.rows = rows
        if not omit_rowcount:
            self.rowcount = len(rows) if rowcount is _ROWCOUNT_FROM_ROWS else rowcount

    def fetchone(self) -> dict[str, Any] | None:
        return self.rows[0] if self.rows else None

    def fetchall(self) -> list[dict[str, Any]]:
        return self.rows


class FakeRegistryConnection:
    def __init__(self) -> None:
        self.sql: list[str] = []
        self.params: list[Any] = []
        self.sql_depths: list[int] = []
        self.commits = 0
        self.transaction_commits = 0
        self.transaction_rollbacks = 0
        self.transaction_depth = 0

    def execute(self, sql: str, params: Any = None) -> FakeCursor:
        text = " ".join(str(sql).split())
        self.sql.append(text)
        self.params.append(params)
        self.sql_depths.append(self.transaction_depth)
        if "INSERT INTO cex_tokens" in text:
            return FakeCursor(
                [
                    {
                        "cex_token_id": "cex_token:BTC",
                        "base_symbol": "BTC",
                        "status": "canonical",
                    }
                ]
            )
        if "SELECT * FROM cex_tokens WHERE cex_token_id = %s" in text:
            return FakeCursor(
                [
                    {
                        "cex_token_id": "cex_token:BTC",
                        "base_symbol": "BTC",
                        "status": "canonical",
                    }
                ]
            )
        if "INSERT INTO registry_assets" in text:
            return FakeCursor(
                [
                    {
                        "asset_id": "asset:eip155:1:erc20:0x999b49c0d1612e619a4a4f6280733184da025108",
                        "chain_id": "eip155:1",
                        "token_standard": "erc20",
                        "address": "0x999b49c0d1612e619a4a4f6280733184da025108",
                        "status": "candidate",
                    }
                ]
            )
        if "INSERT INTO price_feeds" in text:
            return FakeCursor(
                [
                    {
                        "pricefeed_id": "pricefeed:cex:binance:swap:BTCUSDT",
                        "provider": "binance",
                        "feed_type": "cex_swap",
                        "native_market_id": "BTCUSDT",
                        "subject_type": "CexToken",
                        "subject_id": "cex_token:BTC",
                    }
                ]
            )
        if "SELECT * FROM price_feeds WHERE pricefeed_id = %s" in text:
            return FakeCursor(
                [
                    {
                        "pricefeed_id": "pricefeed:cex:binance:swap:BTCUSDT",
                        "provider": "binance",
                        "feed_type": "cex_swap",
                        "native_market_id": "BTCUSDT",
                        "subject_type": "CexToken",
                        "subject_id": "cex_token:BTC",
                    }
                ]
            )
        if "INSERT INTO us_equity_symbols" in text:
            return FakeCursor(
                [
                    {
                        "symbol": "RKLB",
                        "market_instrument_id": "market_instrument:us_equity:RKLB",
                        "status": "active",
                    }
                ]
            )
        if "SELECT * FROM us_equity_symbols WHERE symbol = %s" in text:
            return FakeCursor(
                [
                    {
                        "symbol": "RKLB",
                        "market_instrument_id": "market_instrument:us_equity:RKLB",
                        "status": "active",
                    }
                ]
            )
        if "UPDATE us_equity_symbols" in text and "RETURNING symbol" in text:
            return FakeCursor([{"symbol": "OLD"}])
        raise AssertionError(f"unexpected SQL: {text}")

    def commit(self) -> None:
        self.commits += 1

    def transaction(self) -> RegistryTransaction:
        return RegistryTransaction(self)


class NoTransactionRegistryConnection(FakeRegistryConnection):
    transaction = None


class RegistryDeactivateRowcountConnection(FakeRegistryConnection):
    def __init__(
        self,
        *,
        rowcount: Any = 1,
        omit_rowcount: bool = False,
        rows: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__()
        self.rowcount = rowcount
        self.omit_rowcount = omit_rowcount
        self.rows = rows if rows is not None else [{"symbol": "OLD"}]

    def execute(self, sql: str, params: Any = None) -> FakeCursor:
        text = " ".join(str(sql).split())
        if "UPDATE us_equity_symbols" in text and "RETURNING symbol" in text:
            self.sql.append(text)
            self.params.append(params)
            self.sql_depths.append(self.transaction_depth)
            return FakeCursor(self.rows, rowcount=self.rowcount, omit_rowcount=self.omit_rowcount)
        return super().execute(sql, params)


class RegistryUpsertRowcountConnection(FakeRegistryConnection):
    def __init__(
        self,
        *,
        rowcount: Any = 1,
        omit_rowcount: bool = False,
        rows: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__()
        self.rowcount = rowcount
        self.omit_rowcount = omit_rowcount
        self.rows = rows

    def execute(self, sql: str, params: Any = None) -> FakeCursor:
        text = " ".join(str(sql).split())
        if "INSERT INTO cex_tokens" in text:
            return self._cursor(
                text,
                params,
                [{"cex_token_id": "cex_token:BTC", "base_symbol": "BTC", "status": "canonical"}],
            )
        if "WITH existing AS" in text and "registry_assets" in text:
            return self._cursor(
                text,
                params,
                [
                    {
                        "asset_id": "asset:eip155:1:erc20:0x999b49c0d1612e619a4a4f6280733184da025108",
                        "chain_id": "eip155:1",
                        "address": "0x999b49c0d1612e619a4a4f6280733184da025108",
                        "status": "candidate",
                    }
                ],
            )
        if "INSERT INTO price_feeds" in text:
            return self._cursor(
                text,
                params,
                [
                    {
                        "pricefeed_id": "pricefeed:cex:binance:swap:BTCUSDT",
                        "provider": "binance",
                        "feed_type": "cex_swap",
                        "subject_type": "CexToken",
                        "subject_id": "cex_token:BTC",
                    }
                ],
            )
        if "INSERT INTO us_equity_symbols" in text:
            return self._cursor(
                text,
                params,
                [{"symbol": "RKLB", "market_instrument_id": "market_instrument:us_equity:RKLB", "status": "active"}],
            )
        return super().execute(sql, params)

    def _cursor(self, text: str, params: Any, default_rows: list[dict[str, Any]]) -> FakeCursor:
        self.sql.append(text)
        self.params.append(params)
        self.sql_depths.append(self.transaction_depth)
        rows = default_rows if self.rows is None else self.rows
        return FakeCursor(rows, rowcount=self.rowcount, omit_rowcount=self.omit_rowcount)


class RegistryTransaction:
    def __init__(self, conn: FakeRegistryConnection) -> None:
        self.conn = conn

    def __enter__(self) -> FakeRegistryConnection:
        self.conn.transaction_depth += 1
        return self.conn

    def __exit__(self, exc_type: object, *_args: object) -> bool:
        self.conn.transaction_depth -= 1
        if exc_type is None:
            self.conn.transaction_commits += 1
        else:
            self.conn.transaction_rollbacks += 1
        return False
