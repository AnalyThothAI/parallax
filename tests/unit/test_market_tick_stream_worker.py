from __future__ import annotations

import asyncio
import time
from dataclasses import asdict
from decimal import Decimal
from types import SimpleNamespace

import pytest

from parallax.domains.asset_market.providers import DexMarketFactUpdate
from parallax.domains.asset_market.runtime.market_tick_stream_worker import (
    MarketTickStreamWorker,
)
from parallax.domains.asset_market.types import market_tick_id
from parallax.domains.token_intel._constants import TOKEN_RADAR_PROJECTION_VERSION
from parallax.platform.runtime.worker_base import WorkerBase
from parallax.platform.runtime.worker_result import WorkerResult


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
    worker = _worker(
        db=db,
        stream=provider,
        settings_overrides={"stream_cycle_seconds": 0.05},
        clock=lambda: 1_800_000_000_100,
    )

    asyncio.run(worker.run_once())
    repos.registry.rows = [tier_row(target_type="chain_token", target_id="solana:B", pricefeed_id="pf-B")]
    asyncio.run(worker.run_once())

    assert provider.replace_calls == [[("solana", "A")], [("solana", "B")]]
    assert provider.close_count == 0
    # Provider was constructed once and never recreated
    assert provider.iter_call_count >= 1


def test_market_tick_stream_worker_reads_ranked_targets_persists_current_and_publishes() -> None:
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
    publisher = FakeLiveMarketPublisher()
    worker = _worker(
        db=db,
        stream=stream,
        publisher=publisher,
        settings_overrides={"subscription_limit": 10},
        clock=lambda: 1_800_000_000_100,
    )

    result = asyncio.run(worker.run_once())

    assert isinstance(worker, WorkerBase)
    assert isinstance(result, WorkerResult)
    assert result.processed == 1
    assert result.skipped == 0
    assert db.session_names == ["market_tick_stream", "market_tick_stream"]
    assert repos.registry.calls == [
        {
            "projection_version": TOKEN_RADAR_PROJECTION_VERSION,
            "since_ms": 1_799_913_600_100,
            "target_types": ("chain_token",),
            "limit": 10,
        }
    ]
    assert stream.saw_in_session == [False]
    assert len(stream.targets) == 1
    assert stream.targets[0].chain_id == "eip155:1"
    assert stream.targets[0].address == "0xAbC"
    assert stream.targets[0].subject_type == "chain_token"
    assert stream.targets[0].subject_id == "eip155:1:0xAbC"
    assert stream.targets[0].pricefeed_id == "pf-1"
    assert repos.conn.commit_count == 1
    assert len(repos.market_ticks.inserted) == 1
    assert repos.token_radar_dirty_targets.enqueues == [
        {
            "rows": [("Asset", "asset:eip155:1:0xAbC")],
            "reason": "market_tick_current_changed",
            "now_ms": 1_800_000_000_100,
        }
    ]
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
    assert publisher.updates[0]["type"] == "live_market_update"
    assert publisher.updates[0]["target_type"] == "Asset"
    assert publisher.updates[0]["target_id"] == "asset:eip155:1:0xAbC"


def test_market_tick_stream_worker_skips_cex_symbol_tier1_targets() -> None:
    state = FakeSessionState()
    repos = FakeRepos(state, [tier_row(target_type="cex_symbol", target_id="binance:BTCUSDT")])
    db = FakeDB(state, repos)
    stream = FakeDexMarketStream(state, [])
    publisher = FakeLiveMarketPublisher()
    worker = _worker(
        db=db,
        stream=stream,
        publisher=publisher,
        settings_overrides={"subscription_limit": 5},
        clock=lambda: 1_800_000_000_100,
    )

    result = asyncio.run(worker.run_once())

    assert result.processed == 0
    assert result.skipped == 1
    assert stream.targets == []
    assert repos.market_ticks.inserted == []
    assert publisher.updates == []


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
    publisher = FakeLiveMarketPublisher()
    worker = _worker(db=db, stream=stream, publisher=publisher, clock=lambda: 1_800_000_000_100)

    result = asyncio.run(worker.run_once())

    assert result.processed == 0
    assert result.skipped == 6
    assert stream.saw_in_session == [False]
    assert repos.market_ticks.inserted == []
    assert repos.conn.commit_count == 0
    assert publisher.updates == []


def test_market_tick_stream_worker_flushes_collected_ticks_before_stream_error_returns_degraded_result() -> None:
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
    publisher = FakeLiveMarketPublisher()
    worker = _worker(db=db, stream=stream, publisher=publisher, clock=lambda: 1_800_000_000_100)

    result = asyncio.run(worker.run_once())

    assert result.failed == 0
    assert result.notes["degraded"] is True
    assert result.notes["provider_state"] == "degraded_recoverable"
    assert result.notes["failure_category"] == "stream_error"
    assert stream.saw_in_session == [False]
    assert len(repos.market_ticks.inserted) == 1
    assert repos.conn.commit_count == 1
    assert [row["target_id"] for row in publisher.updates] == ["asset:solana:TokenA"]


def test_market_tick_stream_worker_persists_collected_ticks_once_when_error_and_close_error() -> None:
    state = FakeSessionState()
    repos = FakeRepos(state, [tier_row(target_type="chain_token", target_id="solana:TokenA")])
    db = FakeDB(state, repos)
    stream = CloseFailingDexMarketStream(
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
    publisher = FakeLiveMarketPublisher()
    worker = _worker(db=db, stream=stream, publisher=publisher, clock=lambda: 1_800_000_000_100)

    result = asyncio.run(worker.run_once())

    assert result.failed == 0
    assert result.notes["degraded"] is True
    assert len(repos.market_ticks.inserted) == 1
    assert repos.conn.commit_count == 1
    assert [row["target_id"] for row in publisher.updates] == ["asset:solana:TokenA"]


def test_market_tick_stream_worker_provider_circuit_open_returns_degraded_result() -> None:
    state = FakeSessionState()
    repos = FakeRepos(state, [tier_row(target_type="chain_token", target_id="solana:TokenA")])
    db = FakeDB(state, repos)
    stream = FailingReplaceDexMarketStream(
        RuntimeError("OKX DEX WS circuit open"),
        provider_state={
            "provider": "okx_dex_ws",
            "state": "circuit_open",
            "last_error_category": "connect_timeout",
        },
    )
    worker = _worker(
        db=db,
        stream=stream,
        settings_overrides={"stream_cycle_seconds": 0.05},
        clock=lambda: 1_800_000_000_100,
    )

    result = asyncio.run(worker.run_once())

    assert result.processed == 0
    assert result.failed == 0
    assert result.notes["degraded"] is True
    assert result.notes["provider_state"] == "circuit_open"
    assert result.notes["failure_category"] == "connect_timeout"
    assert repos.market_ticks.inserted == []


def test_market_tick_stream_worker_recoverable_provider_failure_returns_degraded_result() -> None:
    state = FakeSessionState()
    repos = FakeRepos(state, [tier_row(target_type="chain_token", target_id="solana:TokenA")])
    db = FakeDB(state, repos)
    stream = FailingReplaceDexMarketStream(
        RuntimeError("recoverable reconnect"),
        provider_state={
            "provider": "okx_dex_ws",
            "state": "degraded_recoverable",
            "last_error_category": "notice_reconnect",
        },
    )
    worker = _worker(
        db=db,
        stream=stream,
        settings_overrides={"stream_cycle_seconds": 0.05},
        clock=lambda: 1_800_000_000_100,
    )

    result = asyncio.run(worker.run_once())

    assert result.processed == 0
    assert result.failed == 0
    assert result.notes["degraded"] is True
    assert result.notes["provider_state"] == "degraded_recoverable"
    assert result.notes["failure_category"] == "notice_reconnect"
    assert repos.market_ticks.inserted == []


def test_market_tick_stream_worker_provider_state_hook_is_required_for_stream_failures() -> None:
    state = FakeSessionState()
    repos = FakeRepos(state, [tier_row(target_type="chain_token", target_id="solana:TokenA")])
    db = FakeDB(state, repos)
    stream = MissingConnectionStateFailingStream(RuntimeError("socket dropped"))
    worker = _worker(
        db=db,
        stream=stream,
        settings_overrides={"stream_cycle_seconds": 0.05},
        clock=lambda: 1_800_000_000_100,
    )

    result = asyncio.run(worker.run_once())

    assert result.failed == 0
    assert result.notes["degraded"] is True
    assert result.notes["provider_state"] == "failed"
    assert result.notes["provider_state_payload"] == {
        "state": "failed",
        "last_error_category": "provider_connection_state_contract_missing",
    }
    assert result.notes["failure_category"] == "provider_connection_state_contract_missing"
    assert repos.market_ticks.inserted == []


def test_market_tick_stream_worker_bounds_stream_cycle_and_closes_iterator() -> None:
    state = FakeSessionState()
    repos = FakeRepos(state, [tier_row(target_type="chain_token", target_id="solana:TokenA")])
    db = FakeDB(state, repos)
    stream = NeverYieldDexMarketStream(state)
    worker = _worker(
        db=db,
        stream=stream,
        settings_overrides={"stream_cycle_seconds": 0.001},
        clock=lambda: 1_800_000_000_100,
    )

    result = asyncio.run(worker.run_once())

    assert result.processed == 0
    assert result.skipped == 0
    assert result.notes["stream_targets"] == 1
    assert stream.saw_in_session == [False]
    assert stream.closed is True
    assert repos.market_ticks.inserted == []


def test_market_tick_stream_worker_requires_iterator_aclose_contract() -> None:
    state = FakeSessionState()
    repos = FakeRepos(state, [tier_row(target_type="chain_token", target_id="solana:TokenA")])
    db = FakeDB(state, repos)
    stream = MissingIteratorCloseDexMarketStream(
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
    worker = _worker(
        db=db,
        stream=stream,
        settings_overrides={"stream_cycle_seconds": 0.01},
        clock=lambda: 1_800_000_000_100,
    )

    result = asyncio.run(worker.run_once())

    assert result.processed == 1
    assert result.failed == 0
    assert result.notes["degraded"] is True
    assert result.notes["failure_category"] == "AttributeError"
    assert repos.conn.commit_count == 1
    assert len(repos.market_ticks.inserted) == 1


def test_market_tick_stream_worker_bounds_subscription_replace_by_stream_cycle() -> None:
    state = FakeSessionState()
    repos = FakeRepos(state, [tier_row(target_type="chain_token", target_id="solana:TokenA")])
    db = FakeDB(state, repos)
    stream = HangingReplaceDexMarketStream()
    worker = _worker(
        db=db,
        stream=stream,
        settings_overrides={"stream_cycle_seconds": 0.001},
        clock=lambda: 1_800_000_000_100,
    )

    started = time.perf_counter()
    result = asyncio.run(asyncio.wait_for(worker.run_once(), timeout=0.2))
    elapsed = time.perf_counter() - started

    assert result.failed == 0
    assert result.notes["degraded"] is True
    assert result.notes["failure_category"] == "timeout"
    assert elapsed < 0.05
    assert stream.replace_cancelled is True
    assert repos.market_ticks.inserted == []


def test_market_tick_stream_worker_requires_stream_provider_contract() -> None:
    state = FakeSessionState()
    repos = FakeRepos(state, [tier_row(target_type="chain_token", target_id="solana:TokenA")])

    with pytest.raises(RuntimeError, match="market_tick_stream_provider_required"):
        _worker(db=FakeDB(state, repos), stream=None)


def test_market_tick_stream_worker_requires_db_pool_bundle_contract() -> None:
    state = FakeSessionState()

    with pytest.raises(RuntimeError, match="market_tick_stream_db_required"):
        MarketTickStreamWorker(
            pool_bundle=None,
            stream_dex_market=FakeDexMarketStream(state, []),
            settings=_stream_settings(),
            telemetry=object(),
        )


def _worker(
    *,
    db: object,
    stream: object | None,
    publisher: FakeLiveMarketPublisher | None = None,
    settings_overrides: dict[str, object] | None = None,
    clock: object | None = None,
) -> MarketTickStreamWorker:
    return MarketTickStreamWorker(
        pool_bundle=db,
        stream_dex_market=stream,
        on_live_market_update=publisher.publish if publisher is not None else None,
        clock=clock,
        settings=_stream_settings(**(settings_overrides or {})),
        telemetry=object(),
    )


def _stream_settings(**overrides: object) -> SimpleNamespace:
    values = {
        "enabled": True,
        "interval_seconds": 5.0,
        "subscription_limit": 50,
        "stream_cycle_seconds": 30.0,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


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
        self.registry = FakeRegistry(tier_rows)
        self.market_ticks = FakeMarketTicks(state)
        self.market_tick_current = FakeMarketTickCurrent()
        self.token_radar_dirty_targets = FakeRadarDirtyTargets()
        self.conn = FakeConn()

    def transaction(self):
        return FakeTransaction(self.conn)

    def require_transaction(self, *, operation: str) -> None:
        return None


class FakeRegistry:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.calls: list[dict[str, object]] = []

    def ranked_market_targets(self, **kwargs: object) -> list[dict[str, object]]:
        self.calls.append(dict(kwargs))
        limit = int(kwargs["limit"])
        return self.rows[:limit]

    def product_targets_for_market_targets(
        self,
        targets: list[tuple[str, str]],
    ) -> dict[tuple[str, str], tuple[str, str]]:
        return {target: ("Asset", f"asset:{target[1]}") for target in targets if target[0] == "chain_token"}


class FakeMarketTicks:
    def __init__(self, state: FakeSessionState) -> None:
        self.state = state
        self.inserted = []

    def insert_ticks_returning_rows(self, ticks) -> list[dict[str, object]]:
        assert self.state.in_session is True
        self.inserted.extend(ticks)
        return [asdict(tick) for tick in ticks]


class FakeMarketTickCurrent:
    def upsert_current_from_tick(self, tick_row: dict[str, object]) -> bool:
        return True


class FakeRadarDirtyTargets:
    def __init__(self) -> None:
        self.enqueues: list[dict[str, object]] = []

    def enqueue_market_product_targets(self, rows, *, reason, now_ms) -> int:
        self.enqueues.append({"rows": list(rows), "reason": reason, "now_ms": now_ms})
        return len(self.enqueues[-1]["rows"])


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


class FakeTransaction:
    def __init__(self, conn: FakeConn) -> None:
        self.conn = conn

    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type is None:
            self.conn.commit()
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

    def connection_state_payload(self):
        return {
            "provider": "okx_dex_ws",
            "state": "connected",
            "last_state_change_at_ms": 1_800_000_000_000,
        }


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

    def connection_state_payload(self):
        return {
            "provider": "okx_dex_ws",
            "state": "degraded_recoverable",
            "last_error_category": "stream_error",
        }


class CloseFailingDexMarketStream:
    def __init__(self, state: FakeSessionState, updates: list[DexMarketFactUpdate]) -> None:
        self.state = state
        self.updates = updates
        self.saw_in_session: list[bool] = []
        self.targets = []

    async def replace_subscriptions(self, targets) -> None:
        self.targets = list(targets)

    def iter_price_info(self):
        return CloseFailingPriceIterator(self.state, self.updates, self.saw_in_session)

    def connection_state_payload(self):
        return {
            "provider": "okx_dex_ws",
            "state": "degraded_recoverable",
            "last_error_category": "stream_error",
        }


class CloseFailingPriceIterator:
    def __init__(
        self,
        state: FakeSessionState,
        updates: list[DexMarketFactUpdate],
        saw_in_session: list[bool],
    ) -> None:
        self.state = state
        self.updates = list(updates)
        self.saw_in_session = saw_in_session
        self.index = 0

    def __aiter__(self):
        self.saw_in_session.append(self.state.in_session)
        return self

    async def __anext__(self):
        if self.index < len(self.updates):
            update = self.updates[self.index]
            self.index += 1
            return update
        raise RuntimeError("socket dropped")

    async def aclose(self) -> None:
        raise RuntimeError("close dropped")


class MissingIteratorCloseDexMarketStream:
    def __init__(self, state: FakeSessionState, updates: list[DexMarketFactUpdate]) -> None:
        self.state = state
        self.updates = updates
        self.targets = []
        self.saw_in_session: list[bool] = []

    async def replace_subscriptions(self, targets) -> None:
        self.targets = list(targets)

    def iter_price_info(self):
        return MissingClosePriceIterator(self.state, self.updates, self.saw_in_session)

    def connection_state_payload(self):
        return {
            "provider": "okx_dex_ws",
            "state": "connected",
            "last_state_change_at_ms": 1_800_000_000_000,
        }


class MissingClosePriceIterator:
    def __init__(
        self,
        state: FakeSessionState,
        updates: list[DexMarketFactUpdate],
        saw_in_session: list[bool],
    ) -> None:
        self.state = state
        self.updates = list(updates)
        self.saw_in_session = saw_in_session
        self.index = 0

    def __aiter__(self):
        self.saw_in_session.append(self.state.in_session)
        return self

    async def __anext__(self):
        if self.index < len(self.updates):
            update = self.updates[self.index]
            self.index += 1
            return update
        raise StopAsyncIteration


class FailingReplaceDexMarketStream:
    def __init__(self, error: BaseException, *, provider_state: dict[str, object]) -> None:
        self.error = error
        self.provider_state = provider_state

    async def replace_subscriptions(self, targets) -> None:
        raise self.error

    async def iter_price_info(self):
        if False:
            yield

    def connection_state_payload(self):
        return dict(self.provider_state)


class MissingConnectionStateFailingStream:
    def __init__(self, error: BaseException) -> None:
        self.error = error

    async def replace_subscriptions(self, targets) -> None:
        raise self.error

    async def iter_price_info(self):
        if False:
            yield


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

    def connection_state_payload(self):
        return {
            "provider": "okx_dex_ws",
            "state": "connected",
            "last_state_change_at_ms": 1_800_000_000_000,
        }


class HangingReplaceDexMarketStream:
    def __init__(self) -> None:
        self.replace_cancelled = False

    async def replace_subscriptions(self, targets) -> None:
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            self.replace_cancelled = True
            raise

    async def iter_price_info(self):
        if False:
            yield

    def connection_state_payload(self):
        return {
            "provider": "okx_dex_ws",
            "state": "connected",
            "last_state_change_at_ms": 1_800_000_000_000,
        }


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

    def connection_state_payload(self):
        return {
            "provider": "okx_dex_ws",
            "state": "connected",
            "last_state_change_at_ms": 1_800_000_000_000,
        }


class FakeLiveMarketPublisher:
    def __init__(self) -> None:
        self.updates: list[dict[str, object]] = []

    async def publish(self, payload: dict[str, object]) -> None:
        self.updates.append(payload)


def worker_settings(**overrides):
    values = {
        "enabled": True,
        "interval_seconds": 5.0,
        "timeout_seconds": 120.0,
        "subscription_limit": 50,
    }
    values.update(overrides)
    return SimpleNamespace(**values)
