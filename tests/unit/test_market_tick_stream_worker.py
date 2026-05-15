from __future__ import annotations

import asyncio
from decimal import Decimal
from types import SimpleNamespace

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.domains.asset_market.providers import DexMarketFactUpdate
from gmgn_twitter_intel.domains.asset_market.runtime.market_tick_stream_worker import MarketTickStreamWorker
from gmgn_twitter_intel.domains.asset_market.types import market_tick_id


def test_market_tick_stream_worker_reads_tier1_streams_outside_session_inserts_and_notifies() -> None:
    state = FakeSessionState()
    repos = FakeRepos(
        state,
        [
            tier_row(
                target_type="chain_token",
                target_id="solana:So11111111111111111111111111111111111111112",
                pricefeed_id="pf-1",
            )
        ],
    )
    db = FakeDB(state, repos)
    stream = FakeDexMarketStream(
        state,
        [
            DexMarketFactUpdate(
                chain_id="solana",
                address="So11111111111111111111111111111111111111112",
                observed_at_ms=1_800_000_000_001,
                price_usd=123.45,
                market_cap_usd=456.7,
                liquidity_usd=89.01,
                volume_24h_usd=234.56,
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
    assert stream.targets[0].chain_id == "solana"
    assert stream.targets[0].address == "So11111111111111111111111111111111111111112"
    assert stream.targets[0].subject_type == "chain_token"
    assert stream.targets[0].subject_id == "solana:So11111111111111111111111111111111111111112"
    assert stream.targets[0].pricefeed_id == "pf-1"
    assert repos.conn.commit_count == 1
    assert len(repos.market_ticks.inserted) == 1
    tick = repos.market_ticks.inserted[0]
    assert tick.tick_id == market_tick_id(
        target_type="chain_token",
        target_id="solana:So11111111111111111111111111111111111111112",
        source_provider="okx_dex_ws",
        observed_at_ms=1_800_000_000_001,
    )
    assert tick.source_tier == "tier1_ws"
    assert tick.source_provider == "okx_dex_ws"
    assert tick.price_usd == Decimal("123.45")
    assert tick.market_cap_usd == Decimal("456.7")
    assert tick.liquidity_usd == Decimal("89.01")
    assert tick.volume_24h_usd == Decimal("234.56")
    assert tick.raw_payload_json == {"source": "fake"}
    assert wake.market_notifications == [
        {
            "target_type": "chain_token",
            "target_id": "solana:So11111111111111111111111111111111111111112",
        }
    ]


def test_market_tick_stream_worker_skips_cex_symbol_tier1_targets() -> None:
    state = FakeSessionState()
    repos = FakeRepos(state, [tier_row(target_type="cex_symbol", target_id="okx:BTC-USDT-SWAP")])
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
    assert wake.market_notifications == []


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
    assert result.skipped == 4
    assert stream.saw_in_session == [False]
    assert repos.market_ticks.inserted == []
    assert repos.conn.commit_count == 0
    assert wake.market_notifications == []


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
        assert self.state.in_session is True
        self.inserted.extend(ticks)
        return len(ticks)


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

    async def stream_price_info(self, targets):
        self.targets = list(targets)
        if not self.targets:
            return
        self.saw_in_session.append(self.state.in_session)
        for update in self.updates:
            yield update


class FakeWakeEmitter:
    def __init__(self) -> None:
        self.market_notifications: list[dict[str, str]] = []

    def notify_market_observation_written(self, *, target_type: str, target_id: str) -> None:
        self.market_notifications.append({"target_type": target_type, "target_id": target_id})


def worker_settings(**overrides):
    values = {
        "enabled": True,
        "interval_seconds": 5.0,
        "timeout_seconds": 120.0,
        "subscription_limit": 50,
    }
    values.update(overrides)
    return SimpleNamespace(**values)
