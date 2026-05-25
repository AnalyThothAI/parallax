from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from gmgn_twitter_intel.app.runtime.repository_session import repositories_for_connection
from gmgn_twitter_intel.domains.asset_market.repositories.market_tick_current_dirty_target_repository import (
    MarketTickCurrentDirtyTargetRepository,
)
from gmgn_twitter_intel.domains.asset_market.repositories.market_tick_repository import MarketTickRepository
from gmgn_twitter_intel.domains.asset_market.runtime.market_tick_poll_worker import MarketTickPollWorker
from gmgn_twitter_intel.domains.asset_market.runtime.market_tick_stream_worker import MarketTickStreamWorker
from gmgn_twitter_intel.domains.asset_market.types import MarketTick, MarketTickSourceProvider, market_tick_id
from tests.postgres_test_utils import connect_postgres_test
from tests.postgres_test_utils import reset_postgres_schema as migrate

NOW_MS = 1_800_000_000_000
TARGET_ID = "eip155:1:0x1111111111111111111111111111111111111111"


def test_market_tick_repository_insert_ticks_returns_actual_inserted_count(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        repo = MarketTickRepository(conn)
        tick = _tick(source_provider="okx_dex_ws")

        assert repo.insert_ticks([tick, tick]) == 1
        conn.commit()
        assert repo.insert_ticks([tick]) == 0
        conn.commit()

        row = conn.execute("SELECT count(*) AS count FROM market_ticks").fetchone()
        assert row["count"] == 1
    finally:
        conn.close()


def test_market_tick_poll_worker_persist_ticks_wakes_only_inserted_targets(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        wake = _RecordingWakeEmitter()
        worker = MarketTickPollWorker(
            db=_DB(conn),
            providers=SimpleNamespace(dex_quote_market=None, cex_market=None),
            wake_emitter=wake,
        )
        tick = _tick(source_provider="okx_dex_rest")

        assert worker._persist_ticks([tick, tick]) == 1
        assert wake.market_tick_notifications == [{"target_type": "chain_token", "target_id": TARGET_ID}]

        assert worker._persist_ticks([tick]) == 0
        assert wake.market_tick_notifications == [{"target_type": "chain_token", "target_id": TARGET_ID}]
    finally:
        conn.close()


def test_market_tick_stream_worker_persist_ticks_wakes_only_inserted_targets(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    try:
        migrate(conn)
        wake = _RecordingWakeEmitter()
        worker = MarketTickStreamWorker(db=_DB(conn), stream_dex_market=None, wake_emitter=wake)
        tick = _tick(source_provider="okx_dex_ws")

        assert worker._persist_ticks([tick, tick]) == 1
        assert wake.market_tick_notifications == [{"target_type": "chain_token", "target_id": TARGET_ID}]

        assert worker._persist_ticks([tick]) == 0
        assert wake.market_tick_notifications == [{"target_type": "chain_token", "target_id": TARGET_ID}]
    finally:
        conn.close()


def test_market_tick_current_dirty_claim_token_protects_reenqueued_work(tmp_path) -> None:
    conn = connect_postgres_test(tmp_path / "postgres_test_db", read_only=False)
    target = ("chain_token", "eip155:1:0x2222222222222222222222222222222222222222")
    try:
        migrate(conn)
        repo = MarketTickCurrentDirtyTargetRepository(conn)
        repo.enqueue_targets([target], reason="market_tick_written", now_ms=NOW_MS, commit=True)

        old_claim = repo.claim_due(
            limit=1,
            now_ms=NOW_MS + 1,
            lease_ms=60_000,
            lease_owner="worker-a",
            commit=True,
        )[0]
        repo.enqueue_targets([target], reason="market_tick_written", now_ms=NOW_MS + 2, commit=True)

        assert repo.mark_done([old_claim], now_ms=NOW_MS + 3, commit=True) == 0
        assert repo.mark_error([old_claim], error="stale", retry_ms=30_000, now_ms=NOW_MS + 4, commit=True) == 0

        successor_claim = repo.claim_due(
            limit=1,
            now_ms=NOW_MS + 5,
            lease_ms=60_000,
            lease_owner="worker-b",
            commit=True,
        )[0]
        assert successor_claim["attempt_count"] == old_claim["attempt_count"] + 1
        assert repo.mark_error(
            [successor_claim],
            error="retry later",
            retry_ms=30_000,
            now_ms=NOW_MS + 6,
            commit=True,
        ) == 1
        assert repo.claim_due(
            limit=1,
            now_ms=NOW_MS + 7,
            lease_ms=60_000,
            lease_owner="worker-c",
            commit=True,
        ) == []
        assert repo.claim_due(
            limit=1,
            now_ms=NOW_MS + 30_006,
            lease_ms=60_000,
            lease_owner="worker-c",
            commit=True,
        )
    finally:
        conn.execute(
            "DELETE FROM market_tick_current_dirty_targets WHERE target_type = %s AND target_id = %s",
            target,
        )
        conn.commit()
        conn.close()


class _DB:
    def __init__(self, conn: Any) -> None:
        self.conn = conn

    @contextmanager
    def worker_session(self, name: str, **_: Any):
        yield repositories_for_connection(self.conn)

    @contextmanager
    def worker_transaction(self, name: str, **_: Any):
        with self.conn.transaction():
            yield repositories_for_connection(self.conn)


class _RecordingWakeEmitter:
    def __init__(self) -> None:
        self.market_tick_notifications: list[dict[str, str]] = []

    def notify_market_tick_written(self, *, target_type: str, target_id: str) -> None:
        self.market_tick_notifications.append({"target_type": target_type, "target_id": target_id})


def _tick(*, source_provider: MarketTickSourceProvider) -> MarketTick:
    return MarketTick(
        tick_id=market_tick_id(
            target_type="chain_token",
            target_id=TARGET_ID,
            source_provider=source_provider,
            observed_at_ms=NOW_MS,
        ),
        target_type="chain_token",
        target_id=TARGET_ID,
        chain="eip155:1",
        token_address="0x1111111111111111111111111111111111111111",
        exchange=None,
        instrument=None,
        pricefeed_id=None,
        source_tier="tier1_ws" if source_provider == "okx_dex_ws" else "tier2_poll",
        source_provider=source_provider,
        observed_at_ms=NOW_MS,
        received_at_ms=NOW_MS + 1,
        price_usd=Decimal("1.23"),
        liquidity_usd=Decimal("1000"),
        volume_24h_usd=Decimal("5000"),
        market_cap_usd=Decimal("100000"),
        holders=123,
        created_at_ms=NOW_MS + 2,
        raw_payload_json={"test": True},
    )
