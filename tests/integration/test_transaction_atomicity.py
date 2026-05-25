from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest

from gmgn_twitter_intel.app.runtime.db_pool_bundle import DBPoolBundle
from gmgn_twitter_intel.app.runtime.repository_session import repositories_for_connection
from gmgn_twitter_intel.domains.asset_market.services.market_tick_current_rebuild import (
    MarketTickCurrentRebuildService,
)
from gmgn_twitter_intel.domains.asset_market.services.market_tick_persistence import MarketTickPersistenceService
from gmgn_twitter_intel.domains.asset_market.types import MarketTick, market_tick_id
from gmgn_twitter_intel.platform.db import postgres_client
from gmgn_twitter_intel.platform.db.postgres_client import create_pool
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import test_postgres_dsn as postgres_test_dsn


def test_worker_transaction_rolls_back_all_statements() -> None:
    setup_conn = connect_postgres_test(read_only=False)
    pool = create_pool(
        postgres_test_dsn(),
        min_size=0,
        max_size=1,
        connect_timeout_seconds=5,
        application_name="gmgn_test_worker",
        statement_timeout_seconds=5,
    )
    try:
        setup_conn.execute("DROP TABLE IF EXISTS transaction_atomicity_probe")
        setup_conn.execute(
            """
            CREATE TABLE transaction_atomicity_probe (
                id text PRIMARY KEY,
                label text NOT NULL
            )
            """
        )
        setup_conn.commit()
        bundle = DBPoolBundle(api_pool=None, worker_pool=pool, wake_pool=None)

        with pytest.raises(RuntimeError, match="boom"), bundle.worker_transaction("atomicity_probe") as repos:
            repos.conn.execute(
                "INSERT INTO transaction_atomicity_probe (id, label) VALUES (%s, %s)",
                ("first", "inside"),
            )
            repos.conn.execute(
                "INSERT INTO transaction_atomicity_probe (id, label) VALUES (%s, %s)",
                ("second", "inside"),
            )
            raise RuntimeError("boom")

        row = setup_conn.execute("SELECT count(*) AS row_count FROM transaction_atomicity_probe").fetchone()
        assert row["row_count"] == 0
    finally:
        setup_conn.execute("DROP TABLE IF EXISTS transaction_atomicity_probe")
        setup_conn.commit()
        setup_conn.close()
        pool.close()


def test_require_transaction_rejects_real_postgres_autocommit_connection() -> None:
    conn = connect_postgres_test(read_only=False)
    try:
        with pytest.raises(RuntimeError, match="projection_write_requires_explicit_transaction"):
            postgres_client.require_transaction(conn, operation="projection_write")
    finally:
        conn.close()


def test_require_transaction_accepts_real_postgres_transaction() -> None:
    conn = connect_postgres_test(read_only=False)
    try:
        with conn.transaction():
            postgres_client.require_transaction(conn, operation="projection_write")
    finally:
        conn.close()


def test_require_transaction_allows_fake_connections_without_psycopg_info() -> None:
    postgres_client.require_transaction(object(), operation="fake_write")


def test_repository_session_transaction_alias_uses_unit_of_work() -> None:
    conn = FakeTransactionConnection()
    repos = repositories_for_connection(conn)

    with repos.transaction():
        conn.events.append("body")

    assert conn.events == ["begin", "body", "commit"]


def test_market_tick_persistence_rolls_back_tick_and_dirty_target_after_enqueue() -> None:
    setup_conn = connect_postgres_test(read_only=False)
    pool = create_pool(
        postgres_test_dsn(),
        min_size=0,
        max_size=1,
        connect_timeout_seconds=5,
        application_name="gmgn_test_market_tick_atomicity",
        statement_timeout_seconds=5,
    )
    now_ms = 1_900_000_000_000
    tick = _market_tick(observed_at_ms=now_ms)
    try:
        setup_conn.execute(
            "DELETE FROM market_tick_current_dirty_targets WHERE target_type = %s AND target_id = %s",
            (tick.target_type, tick.target_id),
        )
        setup_conn.execute(
            "DELETE FROM market_ticks WHERE observed_at_ms = %s AND tick_id = %s",
            (tick.observed_at_ms, tick.tick_id),
        )
        setup_conn.commit()

        bundle = DBPoolBundle(api_pool=None, worker_pool=pool, wake_pool=None)
        with pytest.raises(RuntimeError, match="fail_after_ticks_for_test"), bundle.worker_transaction(
            "market_tick_atomicity"
        ) as repos:
            dirty_recorder = DirtyTargetRecorder(repos.market_tick_current_dirty_targets)
            service = MarketTickPersistenceService(
                SimpleNamespace(
                    conn=repos.conn,
                    market_ticks=repos.market_ticks,
                    market_tick_current_dirty_targets=dirty_recorder,
                )
            )
            service.insert_ticks_and_enqueue_current_dirty(
                [tick],
                reason="test_atomicity",
                now_ms=now_ms,
                fail_after_ticks_for_test=True,
            )

        assert dirty_recorder.calls == [
            {
                "targets": [(tick.target_type, tick.target_id)],
                "reason": "test_atomicity",
                "now_ms": now_ms,
                "commit": False,
            }
        ]

        tick_count = setup_conn.execute(
            "SELECT count(*) AS row_count FROM market_ticks WHERE observed_at_ms = %s AND tick_id = %s",
            (tick.observed_at_ms, tick.tick_id),
        ).fetchone()
        dirty_count = setup_conn.execute(
            """
            SELECT count(*) AS row_count
            FROM market_tick_current_dirty_targets
            WHERE target_type = %s AND target_id = %s
            """,
            (tick.target_type, tick.target_id),
        ).fetchone()
        assert tick_count["row_count"] == 0
        assert dirty_count["row_count"] == 0
    finally:
        setup_conn.execute(
            "DELETE FROM market_tick_current_dirty_targets WHERE target_type = %s AND target_id = %s",
            (tick.target_type, tick.target_id),
        )
        setup_conn.execute(
            "DELETE FROM market_ticks WHERE observed_at_ms = %s AND tick_id = %s",
            (tick.observed_at_ms, tick.tick_id),
        )
        setup_conn.commit()
        setup_conn.close()
        pool.close()


def test_market_tick_current_rebuild_rolls_back_truncate_and_upsert_on_failure() -> None:
    conn = connect_postgres_test(read_only=False)
    old_tick = _market_tick(observed_at_ms=1_900_000_100_000)
    new_tick = _market_tick(observed_at_ms=1_900_000_200_000)
    try:
        _delete_market_tick_target(conn, old_tick)
        repos = repositories_for_connection(conn)
        repos.market_ticks.insert_tick(old_tick)
        old_row = repos.market_tick_current.latest_tick_for_target(
            target_type=old_tick.target_type,
            target_id=old_tick.target_id,
        )
        assert old_row is not None
        repos.market_tick_current.upsert_current_from_tick(old_row, now_ms=old_tick.received_at_ms + 100)
        repos.market_ticks.insert_tick(new_tick)
        conn.commit()

        failing_repos = SimpleNamespace(
            transaction=repos.transaction,
            market_tick_current=FailingMarketTickCurrentRepository(repos.market_tick_current),
        )
        with pytest.raises(RuntimeError, match="rebuild upsert failed"):
            MarketTickCurrentRebuildService(failing_repos).rebuild_all(now_ms=new_tick.received_at_ms + 100)

        current = conn.execute(
            """
            SELECT tick_id, updated_at_ms
            FROM market_tick_current
            WHERE target_type = %s AND target_id = %s
            """,
            (old_tick.target_type, old_tick.target_id),
        ).fetchone()
        assert current["tick_id"] == old_tick.tick_id
        assert current["updated_at_ms"] == old_tick.received_at_ms
    finally:
        _delete_market_tick_target(conn, old_tick)
        conn.commit()
        conn.close()


class FakeTransactionConnection:
    def __init__(self) -> None:
        self.events: list[str] = []

    @contextmanager
    def transaction(self) -> Any:
        self.events.append("begin")
        try:
            yield
        except BaseException:
            self.events.append("rollback")
            raise
        else:
            self.events.append("commit")


class DirtyTargetRecorder:
    def __init__(self, delegate: Any) -> None:
        self.delegate = delegate
        self.calls: list[dict[str, Any]] = []

    def enqueue_targets(self, targets: Any, *, reason: str, now_ms: int, commit: bool) -> int:
        materialized = list(targets)
        self.calls.append(
            {
                "targets": materialized,
                "reason": reason,
                "now_ms": now_ms,
                "commit": commit,
            }
        )
        return self.delegate.enqueue_targets(materialized, reason=reason, now_ms=now_ms, commit=commit)


class FailingMarketTickCurrentRepository:
    def __init__(self, delegate: Any) -> None:
        self.delegate = delegate

    def truncate_current(self) -> None:
        self.delegate.truncate_current()

    def latest_ticks_for_all_targets(self) -> list[dict[str, Any]]:
        latest = self.delegate.latest_tick_for_target(target_type="chain_token", target_id="solana:atomicity")
        assert latest is not None
        return [latest]

    def upsert_current_from_tick(self, tick_row: dict[str, Any], *, now_ms: int) -> bool:
        self.delegate.upsert_current_from_tick(tick_row, now_ms=now_ms)
        raise RuntimeError("rebuild upsert failed")


def _delete_market_tick_target(conn: Any, tick: MarketTick) -> None:
    conn.execute(
        "DELETE FROM market_tick_current WHERE target_type = %s AND target_id = %s",
        (tick.target_type, tick.target_id),
    )
    conn.execute(
        "DELETE FROM market_tick_current_dirty_targets WHERE target_type = %s AND target_id = %s",
        (tick.target_type, tick.target_id),
    )
    conn.execute(
        "DELETE FROM market_ticks WHERE target_type = %s AND target_id = %s",
        (tick.target_type, tick.target_id),
    )


def _market_tick(*, observed_at_ms: int) -> MarketTick:
    target_type = "chain_token"
    target_id = "solana:atomicity"
    source_provider = "okx_dex_ws"
    return MarketTick(
        tick_id=market_tick_id(
            target_type=target_type,
            target_id=target_id,
            source_provider=source_provider,
            observed_at_ms=observed_at_ms,
        ),
        target_type=target_type,
        target_id=target_id,
        chain="solana",
        token_address="atomicity",
        exchange=None,
        instrument=None,
        pricefeed_id=None,
        source_tier="tier1_ws",
        source_provider=source_provider,
        observed_at_ms=observed_at_ms,
        received_at_ms=observed_at_ms + 1,
        price_usd=Decimal("1.23"),
        liquidity_usd=None,
        volume_24h_usd=None,
        open_interest_usd=None,
        market_cap_usd=None,
        holders=None,
        created_at_ms=observed_at_ms + 2,
        raw_payload_json={"source": "atomicity"},
    )
