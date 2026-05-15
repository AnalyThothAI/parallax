from __future__ import annotations

from gmgn_twitter_intel.domains.account_quality.repositories.account_quality_repository import AccountQualityRepository


def test_market_ticks_for_token_reads_tick_history_with_named_params():
    conn = FakeConn(rows=[{"price": 1.23, "received_at_ms": 1_700_000_000_000}])

    rows = AccountQualityRepository(conn).market_ticks_for_token(
        target_type="chain_token",
        target_id="solana:pepe",
        first_mention_ms=1_700_000_000_000,
    )

    assert rows == [{"price": 1.23, "received_at_ms": 1_700_000_000_000}]
    assert "FROM market_ticks" in conn.sql
    assert "WHERE target_type = %(target_type)s" in conn.sql
    assert "AND target_id = %(target_id)s" in conn.sql
    assert "ORDER BY observed_at_ms ASC" in conn.sql
    assert "price_observations" not in conn.sql
    assert conn.params == {
        "target_type": "chain_token",
        "target_id": "solana:pepe",
        "start_ms": 1_700_000_000_000,
        "end_ms": 1_700_086_400_000,
    }


class FakeConn:
    def __init__(self, *, rows):
        self.rows = rows
        self.sql = ""
        self.params = {}

    def execute(self, sql, params=None):
        self.sql = str(sql)
        self.params = params or {}
        return self

    def fetchall(self):
        return self.rows
