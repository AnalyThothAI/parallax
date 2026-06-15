from __future__ import annotations

import pytest

from parallax.domains.account_quality.repositories.account_quality_repository import AccountQualityRepository


def test_account_quality_repository_writes_require_connection_transaction_before_sql_when_committing():
    conn = NoTransactionConn(rows=[])

    with pytest.raises(RuntimeError, match="account_quality_repository_transaction_required"):
        AccountQualityRepository(conn).upsert_profile(
            handle="Early",
            first_seen_ms=1_700_000_000_000,
            latest_seen_ms=1_700_000_010_000,
            follower_max=42,
            watched_status="watched",
        )

    assert conn.sqls == []


def test_account_quality_repository_commit_owned_writes_use_connection_transaction_without_manual_commit():
    conn = FakeConn(rows=[])
    repository = AccountQualityRepository(conn)

    repository.upsert_profile(
        handle="Early",
        first_seen_ms=1_700_000_000_000,
        latest_seen_ms=1_700_000_010_000,
        follower_max=42,
        watched_status="watched",
    )
    repository.upsert_directory_entry(
        handle="Early",
        gmgn_user_id="gmgn-1",
        user_tags=("smart",),
        platform_followers=123,
        observed_at_ms=1_700_000_000_000,
    )
    repository.upsert_token_call_stat(
        handle="Early",
        token_id="asset:eip155:1:erc20:dog",
        first_mention_ms=1_700_000_000_000,
        mention_count=2,
        was_early_author=True,
        outcome_status="settled",
    )
    snapshot_id = repository.insert_quality_snapshot(
        handle="Early",
        window="30d",
        precision_score=0.5,
        early_call_score=0.4,
        spam_risk_score=0.1,
        avg_realized_return=0.2,
        sample_size=1,
    )

    assert snapshot_id == "account-quality:early:30d:current"
    assert conn.sql_transaction_depths == [1, 1, 1, 1]
    assert conn.transaction_enter_count == 4
    assert conn.transaction_exit_count == 4
    assert conn.commit_count == 0


def test_account_quality_repository_caller_owned_writes_do_not_open_inner_transaction():
    conn = FakeConn(rows=[])
    repository = AccountQualityRepository(conn)

    repository.upsert_profile(
        handle="Early",
        first_seen_ms=1_700_000_000_000,
        latest_seen_ms=1_700_000_010_000,
        follower_max=42,
        watched_status="watched",
        commit=False,
    )
    repository.insert_quality_snapshot(
        handle="Early",
        window="30d",
        precision_score=0.5,
        early_call_score=0.4,
        spam_risk_score=0.1,
        avg_realized_return=0.2,
        sample_size=1,
        commit=False,
    )

    assert conn.sql_transaction_depths == [0, 0]
    assert conn.transaction_enter_count == 0
    assert conn.commit_count == 0


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
    assert _legacy_price_table() not in conn.sql
    assert conn.params == {
        "target_type": "chain_token",
        "target_id": "solana:pepe",
        "start_ms": 1_700_000_000_000,
        "end_ms": 1_700_086_400_000,
    }


def test_accounts_quality_batches_profiles_stats_and_snapshots_by_handle_keyset():
    conn = BatchReadConn(
        result_sets=[
            [
                {
                    "requested_handle": "early",
                    "handle": "early",
                    "first_seen_ms": 1,
                    "latest_seen_ms": 2,
                    "follower_max": 42,
                    "watched_status": "watched",
                    "created_at_ms": 1,
                    "updated_at_ms": 2,
                    "gmgn_user_id": None,
                    "gmgn_user_tags": None,
                    "gmgn_platform_followers": None,
                    "gmgn_directory_observed_at_ms": None,
                },
                {
                    "requested_handle": "late",
                    "handle": None,
                    "first_seen_ms": None,
                    "latest_seen_ms": None,
                    "follower_max": None,
                    "watched_status": None,
                    "created_at_ms": None,
                    "updated_at_ms": None,
                    "gmgn_user_id": None,
                    "gmgn_user_tags": None,
                    "gmgn_platform_followers": None,
                    "gmgn_directory_observed_at_ms": None,
                },
            ],
            [
                {
                    "handle": "early",
                    "token_id": "asset:early",
                    "first_mention_ms": 2,
                    "mention_count": 1,
                    "was_early_author": True,
                    "price_change_5m_pct": None,
                    "price_change_1h_pct": 0.1,
                    "price_change_24h_pct": None,
                    "max_drawdown_1h_pct": None,
                    "outcome_status": "settled",
                    "updated_at_ms": 3,
                }
            ],
            [
                {
                    "snapshot_id": "account-quality:early:30d:current",
                    "handle": "early",
                    "window": "30d",
                    "precision_score": 0.7,
                    "early_call_score": 0.6,
                    "spam_risk_score": 0.1,
                    "avg_realized_return": 0.2,
                    "sample_size": 5,
                    "updated_at_ms": 4,
                }
            ],
        ]
    )

    rows = AccountQualityRepository(conn).accounts_quality([" Early ", "@early", "Late"])

    assert len(conn.calls) == 3
    assert rows == [
        {
            "profile": {
                "handle": "early",
                "first_seen_ms": 1,
                "latest_seen_ms": 2,
                "follower_max": 42,
                "watched_status": "watched",
                "created_at_ms": 1,
                "updated_at_ms": 2,
                "gmgn_user_id": None,
                "gmgn_user_tags": None,
                "gmgn_platform_followers": None,
                "gmgn_directory_observed_at_ms": None,
            },
            "token_call_stats": [
                {
                    "handle": "early",
                    "token_id": "asset:early",
                    "first_mention_ms": 2,
                    "mention_count": 1,
                    "was_early_author": True,
                    "price_change_5m_pct": None,
                    "price_change_1h_pct": 0.1,
                    "price_change_24h_pct": None,
                    "max_drawdown_1h_pct": None,
                    "outcome_status": "settled",
                    "updated_at_ms": 3,
                }
            ],
            "quality_snapshots": [
                {
                    "snapshot_id": "account-quality:early:30d:current",
                    "handle": "early",
                    "window": "30d",
                    "precision_score": 0.7,
                    "early_call_score": 0.6,
                    "spam_risk_score": 0.1,
                    "avg_realized_return": 0.2,
                    "sample_size": 5,
                    "updated_at_ms": 4,
                }
            ],
        },
        {"profile": None, "token_call_stats": [], "quality_snapshots": []},
    ]
    assert all("WITH input_handles AS" in call["sql"] for call in conn.calls)
    assert all("WITH ORDINALITY" in call["sql"] for call in conn.calls)
    assert conn.calls[0]["params"] == (["early", "late"],)
    assert "ROW_NUMBER() OVER (" in conn.calls[1]["sql"]
    assert "PARTITION BY stats.handle" in conn.calls[1]["sql"]
    assert "stat_rank <= 50" in conn.calls[1]["sql"]
    assert "ROW_NUMBER() OVER (" in conn.calls[2]["sql"]
    assert "PARTITION BY snapshots.handle" in conn.calls[2]["sql"]
    assert "snapshot_rank <= 20" in conn.calls[2]["sql"]


class FakeConn:
    def __init__(self, *, rows):
        self.rows = rows
        self.sql = ""
        self.sqls: list[str] = []
        self.params = {}
        self.commit_count = 0
        self.transaction_enter_count = 0
        self.transaction_exit_count = 0
        self.transaction_depth = 0
        self.sql_transaction_depths: list[int] = []

    def execute(self, sql, params=None):
        self.sql = str(sql)
        self.sqls.append(self.sql)
        self.sql_transaction_depths.append(self.transaction_depth)
        self.params = params or {}
        return self

    def fetchall(self):
        return self.rows

    def commit(self):
        self.commit_count += 1
        raise AssertionError("manual commit is not allowed in repository tests")

    def transaction(self):
        return FakeTransaction(self)


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


class NoTransactionConn(FakeConn):
    transaction = None


class BatchReadConn:
    def __init__(self, *, result_sets):
        self.result_sets = result_sets
        self.calls: list[dict[str, object]] = []

    def execute(self, sql, params=None):
        self.calls.append({"sql": str(sql), "params": params})
        result_index = len(self.calls) - 1
        rows = self.result_sets[result_index] if result_index < len(self.result_sets) else []
        return BatchReadResult(rows)


class BatchReadResult:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


def _legacy_price_table() -> str:
    return "_".join(("price", "observations"))
