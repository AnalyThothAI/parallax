from __future__ import annotations

import asyncio
from decimal import Decimal
from types import SimpleNamespace

import pytest

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.domains.asset_market.providers import DexMarketFactUpdate
from gmgn_twitter_intel.domains.asset_market.runtime.market_tick_stream_worker import (
    MarketTickStreamWorker,
)
from gmgn_twitter_intel.domains.asset_market.types import market_tick_id


def test_market_tick_stream_worker_is_not_single_writer_locked() -> None:
    state = FakeSessionState()
    repos = FakeRepos(state, [])
    worker = MarketTickStreamWorker(pool_bundle=FakeDB(state, repos), stream_dex_market=FakeDexMarketStream(state, []))

    assert worker.SINGLE_WRITER_KEY is None
    assert worker._advisory_lock_key() is None


def test_market_tick_stream_worker_reuses_stateful_provider_and_replaces_subscriptions() -> None:
    state = FakeSessionState()
    repos = FakeRepos(
        state,
        [tier_row(target_type="chain_token", target_id="solana:A", pricefeed_id="pf-A")],
    )
    db = FakeDB(state, repos)
    provider = FakeStatefulStreamProvider(
        [
            DexMarketFactUpdate(chain_id="solana", address="A", observed_at_ms=1, price_usd=1),
            DexMarketFactUpdate(chain_id="solana", address="B", observed_at_ms=2, price_usd=2),
        ]
    )
    worker = MarketTickStreamWorker(
        pool_bundle=db,
        stream_dex_market=provider,
        stream_cycle_seconds=0.05,
        clock=lambda: 1_800_000_000_100,
    )

    asyncio.run(worker.run_once())
    repos.token_capture_tiers.rows = [tier_row(target_type="chain_token", target_id="solana:B", pricefeed_id="pf-B")]
    asyncio.run(worker.run_once())

    assert provider.replace_calls == [[("solana", "A")], [("solana", "B")]]
    assert provider.close_count == 0
    # Provider was constructed once and never recreated
    assert provider.iter_call_count >= 1


def test_market_tick_stream_worker_reads_tier1_streams_outside_session_inserts_and_notifies() -> None:
    state = FakeSessionState()
    repos = FakeRepos(
        state,
        [
            tier_row(
                target_type="chain_token",
                target_id="eip155:1:0xAbC",
                pricefeed_id="pf-1",
            )
        ],
    )
    db = FakeDB(state, repos)
    stream = FakeDexMarketStream(
        state,
        [
            DexMarketFactUpdate(
                chain_id="eip155:1",
                address="0xabc",
                observed_at_ms=1_800_000_000_001,
                price_usd=123.45,
                market_cap_usd=456.7,
                liquidity_usd=89.01,
                volume_24h_usd=234.56,
                holders=333,
                raw={"source": "fake"},
            )
        ],
    )
    wake = FakeWakeEmitter()
    worker = MarketTickStreamWorker(
        pool_bundle=db,
        stream_dex_market=stream,
        wake_emitter=wake,
        subscription_limit=10,
        clock=lambda: 1_800_000_000_100,
    )

    result = asyncio.run(worker.run_once())

    assert isinstance(worker, WorkerBase)
    assert isinstance(result, WorkerResult)
    assert result.processed == 1
    assert result.skipped == 0
    assert db.session_names == ["market_tick_stream", "market_tick_stream"]
    assert repos.token_capture_tiers.calls == [{"tier": 1, "limit": 10}]
    assert stream.saw_in_session == [False]
    assert len(stream.targets) == 1
    assert stream.targets[0].chain_id == "eip155:1"
    assert stream.targets[0].address == "0xAbC"
    assert stream.targets[0].subject_type == "chain_token"
    assert stream.targets[0].subject_id == "eip155:1:0xAbC"
    assert stream.targets[0].pricefeed_id == "pf-1"
    assert repos.conn.commit_count == 1
    assert len(repos.market_ticks.inserted) == 1
    tick = repos.market_ticks.inserted[0]
    assert tick.tick_id == market_tick_id(
        target_type="chain_token",
        target_id="eip155:1:0xAbC",
        source_provider="okx_dex_ws",
        observed_at_ms=1_800_000_000_001,
    )
    assert tick.source_tier == "tier1_ws"
    assert tick.source_provider == "okx_dex_ws"
    assert tick.price_usd == Decimal("123.45")
    assert tick.market_cap_usd == Decimal("456.7")
    assert tick.liquidity_usd == Decimal("89.01")
    assert tick.volume_24h_usd == Decimal("234.56")
    assert tick.holders == 333
    assert tick.raw_payload_json == {"source": "fake"}
    assert wake.channels == ["market_tick_written"]
    assert wake.market_tick_notifications == [
        {
            "target_type": "chain_token",
            "target_id": "eip155:1:0xAbC",
        }
    ]


def test_market_tick_stream_worker_skips_cex_symbol_tier1_targets() -> None:
    state = FakeSessionState()
    repos = FakeRepos(state, [tier_row(target_type="cex_symbol", target_id="binance:BTCUSDT")])
    db = FakeDB(state, repos)
    stream = FakeDexMarketStream(state, [])
    wake = FakeWakeEmitter()
    worker = MarketTickStreamWorker(
        pool_bundle=db,
        stream_dex_market=stream,
        wake_emitter=wake,
        subscription_limit=5,
        clock=lambda: 1_800_000_000_100,
    )

    result = asyncio.run(worker.run_once())

    assert result.processed == 0
    assert result.skipped == 1
    assert stream.targets == []
    assert repos.market_ticks.inserted == []
    assert wake.market_tick_notifications == []


def test_market_tick_stream_worker_skips_invalid_price_and_does_not_notify() -> None:
    state = FakeSessionState()
    repos = FakeRepos(state, [tier_row(target_type="chain_token", target_id="solana:TokenA")])
    db = FakeDB(state, repos)
    stream = FakeDexMarketStream(
        state,
        [
            DexMarketFactUpdate(chain_id="solana", address="TokenA", observed_at_ms=1, price_usd=None),
            DexMarketFactUpdate(chain_id="solana", address="TokenA", observed_at_ms=2, price_usd=0),
            DexMarketFactUpdate(chain_id="solana", address="TokenA", observed_at_ms=3, price_usd=-1),
            DexMarketFactUpdate(chain_id="solana", address="TokenA", observed_at_ms=4, price_usd="not-a-price"),
            DexMarketFactUpdate(chain_id="solana", address="TokenA", observed_at_ms=5, price_usd=float("nan")),
            DexMarketFactUpdate(chain_id="solana", address="TokenA", observed_at_ms=6, price_usd=float("inf")),
        ],
    )
    wake = FakeWakeEmitter()
    worker = MarketTickStreamWorker(
        pool_bundle=db,
        stream_dex_market=stream,
        wake_emitter=wake,
        clock=lambda: 1_800_000_000_100,
    )

    result = asyncio.run(worker.run_once())

    assert result.processed == 0
    assert result.skipped == 6
    assert stream.saw_in_session == [False]
    assert repos.market_ticks.inserted == []
    assert repos.conn.commit_count == 0
    assert wake.market_tick_notifications == []


def test_market_tick_stream_worker_flushes_collected_ticks_before_stream_error_surfaces() -> None:
    state = FakeSessionState()
    repos = FakeRepos(state, [tier_row(target_type="chain_token", target_id="solana:TokenA")])
    db = FakeDB(state, repos)
    stream = FailingDexMarketStream(
        state,
        [
            DexMarketFactUpdate(
                chain_id="solana",
                address="TokenA",
                observed_at_ms=1_800_000_000_001,
                price_usd=12.34,
            )
        ],
    )
    wake = FakeWakeEmitter()
    worker = MarketTickStreamWorker(
        pool_bundle=db,
        stream_dex_market=stream,
        wake_emitter=wake,
        clock=lambda: 1_800_000_000_100,
    )

    with pytest.raises(RuntimeError, match="socket dropped"):
        asyncio.run(worker.run_once())

    assert stream.saw_in_session == [False]
    assert len(repos.market_ticks.inserted) == 1
    assert repos.conn.commit_count == 1
    assert wake.channels == ["market_tick_written"]
    assert wake.market_tick_notifications == [{"target_type": "chain_token", "target_id": "solana:TokenA"}]


def test_market_tick_stream_worker_bounds_stream_cycle_and_closes_iterator() -> None:
    state = FakeSessionState()
    repos = FakeRepos(state, [tier_row(target_type="chain_token", target_id="solana:TokenA")])
    db = FakeDB(state, repos)
    stream = NeverYieldDexMarketStream(state)
    worker = MarketTickStreamWorker(
        pool_bundle=db,
        stream_dex_market=stream,
        stream_cycle_seconds=0.001,
        clock=lambda: 1_800_000_000_100,
    )

    result = asyncio.run(worker.run_once())

    assert result.processed == 0
    assert result.skipped == 0
    assert result.notes["stream_targets"] == 1
    assert stream.saw_in_session == [False]
    assert stream.closed is True
    assert repos.market_ticks.inserted == []


def test_market_tick_stream_worker_result_when_no_stream_provider() -> None:
    state = FakeSessionState()
    repos = FakeRepos(state, [tier_row(target_type="chain_token", target_id="solana:TokenA")])
    worker = MarketTickStreamWorker(pool_bundle=FakeDB(state, repos), stream_dex_market=None)

    result = asyncio.run(worker.run_once())

    assert isinstance(result, WorkerResult)
    assert result.processed == 0
    assert result.skipped == 1
    assert result.notes["reason"] == "stream_provider_unavailable"


def tier_row(*, target_type: str, target_id: str, pricefeed_id: str | None = None) -> dict[str, object]:
    row: dict[str, object] = {
        "target_type": target_type,
        "target_id": target_id,
        "tier": 1,
        "reason": "ws_subscribed",
        "score": Decimal("1"),
        "updated_at_ms": 1_800_000_000_000,
    }
    if pricefeed_id is not None:
        row["pricefeed_id"] = pricefeed_id
    return row


class FakeSessionState:
    def __init__(self) -> None:
        self.in_session = False


class FakeRepos:
    def __init__(self, state: FakeSessionState, tier_rows: list[dict[str, object]]) -> None:
        self.token_capture_tiers = FakeTokenCaptureTiers(tier_rows)
        self.market_ticks = FakeMarketTicks(state)
        self.conn = FakeConn()


class FakeTokenCaptureTiers:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.calls: list[dict[str, int]] = []

    def list_by_tier(self, tier: int, limit: int) -> list[dict[str, object]]:
        self.calls.append({"tier": tier, "limit": limit})
        return self.rows[:limit]


class FakeMarketTicks:
    def __init__(self, state: FakeSessionState) -> None:
        self.state = state
        self.inserted = []

    def insert_ticks(self, ticks) -> int:
        return len(self.insert_ticks_returning_ids(ticks))

    def insert_ticks_returning_ids(self, ticks) -> list[str]:
        assert self.state.in_session is True
        self.inserted.extend(ticks)
        return [str(tick.tick_id) for tick in ticks]


class FakeConn:
    def __init__(self) -> None:
        self.commit_count = 0

    def commit(self) -> None:
        self.commit_count += 1


class FakeDB:
    def __init__(self, state: FakeSessionState, repos: FakeRepos) -> None:
        self.state = state
        self.repos = repos
        self.session_names: list[str] = []

    def worker_session(self, name: str):
        self.session_names.append(name)
        return FakeSession(self.state, self.repos)


class FakeSession:
    def __init__(self, state: FakeSessionState, repos: FakeRepos) -> None:
        self.state = state
        self.repos = repos

    def __enter__(self) -> FakeRepos:
        assert self.state.in_session is False
        self.state.in_session = True
        return self.repos

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.state.in_session = False
        return False


class FakeDexMarketStream:
    def __init__(self, state: FakeSessionState, updates: list[DexMarketFactUpdate]) -> None:
        self.state = state
        self.updates = updates
        self.targets = []
        self.saw_in_session: list[bool] = []
        self.replace_calls: list[list[tuple[str, str]]] = []
        self.close_count = 0

    async def replace_subscriptions(self, targets) -> None:
        self.targets = list(targets)
        self.replace_calls.append([(t.chain_id, t.address) for t in self.targets])

    async def iter_price_info(self):
        if not self.targets:
            return
        self.saw_in_session.append(self.state.in_session)
        for update in self.updates:
            yield update

    async def aclose(self) -> None:
        self.close_count += 1


class FailingDexMarketStream:
    def __init__(self, state: FakeSessionState, updates: list[DexMarketFactUpdate]) -> None:
        self.state = state
        self.updates = updates
        self.saw_in_session: list[bool] = []
        self.targets = []

    async def replace_subscriptions(self, targets) -> None:
        self.targets = list(targets)

    async def iter_price_info(self):
        self.saw_in_session.append(self.state.in_session)
        for update in self.updates:
            yield update
        raise RuntimeError("socket dropped")

    async def aclose(self) -> None:
        return None


class NeverYieldDexMarketStream:
    def __init__(self, state: FakeSessionState) -> None:
        self.state = state
        self.saw_in_session: list[bool] = []
        self.closed = False
        self.targets = []

    async def replace_subscriptions(self, targets) -> None:
        self.targets = list(targets)

    async def iter_price_info(self):
        self.saw_in_session.append(self.state.in_session)
        try:
            while True:
                await asyncio.sleep(60)
        finally:
            self.closed = True
        if False:
            yield

    async def aclose(self) -> None:
        self.closed = True


class FakeStatefulStreamProvider:
    def __init__(self, updates: list[DexMarketFactUpdate]) -> None:
        self.updates = list(updates)
        self.replace_calls: list[list[tuple[str, str]]] = []
        self.close_count = 0
        self.iter_call_count = 0
        self._current_targets: list = []

    async def replace_subscriptions(self, targets) -> None:
        self._current_targets = list(targets)
        self.replace_calls.append([(t.chain_id, t.address) for t in self._current_targets])

    async def iter_price_info(self):
        self.iter_call_count += 1
        keys = {(t.chain_id, t.address) for t in self._current_targets}
        for update in list(self.updates):
            if (update.chain_id, update.address) in keys:
                yield update

    async def aclose(self) -> None:
        self.close_count += 1


class FakeWakeEmitter:
    def __init__(self) -> None:
        self.channels: list[str] = []
        self.market_tick_notifications: list[dict[str, str]] = []

    def notify_market_tick_written(self, *, target_type: str, target_id: str) -> None:
        self.channels.append("market_tick_written")
        self.market_tick_notifications.append({"target_type": target_type, "target_id": target_id})

    def __getattr__(self, name: str):
        if name == f"notify_{'_'.join(('market', 'observation', 'written'))}":
            raise AssertionError("market_tick_stream must not emit legacy market wakes")
        raise AttributeError(name)


def worker_settings(**overrides):
    values = {
        "enabled": True,
        "interval_seconds": 5.0,
        "timeout_seconds": 120.0,
        "subscription_limit": 50,
    }
    values.update(overrides)
    return SimpleNamespace(**values)
