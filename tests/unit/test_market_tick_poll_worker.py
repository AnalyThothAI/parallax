from __future__ import annotations

import asyncio
import threading
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.domains.asset_market.providers import CexTicker, DexTokenQuote
from gmgn_twitter_intel.domains.asset_market.runtime.market_tick_poll_worker import MarketTickPollWorker
from gmgn_twitter_intel.domains.asset_market.types import market_tick_id


def test_market_tick_poll_worker_is_append_only_without_single_writer_lock() -> None:
    state = FakeSessionState()
    worker = MarketTickPollWorker(
        pool_bundle=FakeDB(state, FakeRepos(state, [])),
        providers=FakeProviders(dex_quote_market=None, cex_market=None),
    )

    assert isinstance(worker, WorkerBase)
    assert worker.SINGLE_WRITER_KEY is None
    assert worker._advisory_lock_key() is None


def test_market_tick_poll_worker_polls_tier2_targets_outside_session_inserts_and_notifies() -> None:
    state = FakeSessionState()
    repos = FakeRepos(
        state,
        [
            tier_row(target_type="chain_token", target_id="eip155:1:0xAbC"),
            tier_row(target_type="cex_symbol", target_id="binance:BTCUSDT"),
        ],
    )
    dex_provider = FakeDexQuoteProvider(
        state,
        [
            DexTokenQuote(
                chain_id="eip155:1",
                address="0xabc",
                observed_at_ms=1_800_000_000_010,
                price_usd=12.34,
                raw={"provider": "dex"},
                market_cap_usd=1234.5,
                liquidity_usd=678.9,
                volume_24h_usd=10.11,
                holders=222,
            )
        ],
    )
    cex_provider = FakeCexProvider(
        state,
        {
            "BTCUSDT": CexTicker(
                inst_id="BTCUSDT",
                inst_type="SWAP",
                last_price=50_123.4,
                volume_24h=999.8,
                open_interest=111.1,
                raw={"ts": "1800000000020", "provider": "cex", "openInterestUsd": "333.2"},
            )
        },
    )
    wake = FakeWakeEmitter()
    worker = MarketTickPollWorker(
        pool_bundle=FakeDB(state, repos),
        providers=FakeProviders(dex_quote_market=dex_provider, cex_market=cex_provider),
        wake_emitter=wake,
        batch_size=10,
        clock=lambda: 1_800_000_000_100,
    )

    result = asyncio.run(worker.run_once())

    assert isinstance(result, WorkerResult)
    assert result.processed == 2
    assert result.skipped == 0
    assert result.notes["targets_selected"] == 2
    assert result.notes["ticks_attempted"] == 2
    assert repos.token_capture_tiers.calls == [{"tier": 2, "limit": 10}]
    assert dex_provider.saw_in_session == [False]
    assert dex_provider.requests == [("eip155:1", "0xAbC")]
    assert cex_provider.saw_in_session == [False]
    assert cex_provider.requests == ["BTCUSDT"]
    assert repos.conn.commit_count == 1
    assert len(repos.market_ticks.inserted) == 2
    assert repos.token_radar_dirty_targets.enqueues == [
        {
            "rows": [
                ("chain_token", "eip155:1:0xAbC"),
                ("cex_symbol", "binance:BTCUSDT"),
            ],
            "reason": "market_tick_current_changed",
            "now_ms": 1_800_000_000_100,
            "commit": False,
        }
    ]

    dex_tick, cex_tick = repos.market_ticks.inserted
    assert dex_tick.tick_id == market_tick_id(
        target_type="chain_token",
        target_id="eip155:1:0xAbC",
        source_provider="okx_dex_rest",
        observed_at_ms=1_800_000_000_010,
    )
    assert dex_tick.target_type == "chain_token"
    assert dex_tick.target_id == "eip155:1:0xAbC"
    assert dex_tick.chain == "eip155:1"
    assert dex_tick.token_address == "0xAbC"
    assert dex_tick.exchange is None
    assert dex_tick.instrument is None
    assert dex_tick.source_tier == "tier2_poll"
    assert dex_tick.source_provider == "okx_dex_rest"
    assert dex_tick.price_usd == Decimal("12.34")
    assert dex_tick.market_cap_usd == Decimal("1234.5")
    assert dex_tick.liquidity_usd == Decimal("678.9")
    assert dex_tick.volume_24h_usd == Decimal("10.11")
    assert dex_tick.holders == 222
    assert dex_tick.raw_payload_json == {"provider": "dex"}

    assert cex_tick.tick_id == market_tick_id(
        target_type="cex_symbol",
        target_id="binance:BTCUSDT",
        source_provider="binance_cex_rest",
        observed_at_ms=1_800_000_000_020,
    )
    assert cex_tick.target_type == "cex_symbol"
    assert cex_tick.target_id == "binance:BTCUSDT"
    assert cex_tick.chain is None
    assert cex_tick.token_address is None
    assert cex_tick.exchange == "binance"
    assert cex_tick.instrument == "BTCUSDT"
    assert cex_tick.source_tier == "tier2_poll"
    assert cex_tick.source_provider == "binance_cex_rest"
    assert cex_tick.price_usd == Decimal("50123.4")
    assert cex_tick.volume_24h_usd == Decimal("999.8")
    assert cex_tick.open_interest_usd == Decimal("333.2")
    assert cex_tick.market_cap_usd is None
    assert cex_tick.raw_payload_json == {
        "ts": "1800000000020",
        "provider": "cex",
        "openInterestUsd": "333.2",
    }
    assert wake.channels == ["market_tick_written", "market_tick_written"]
    assert wake.market_tick_notifications == [
        {"target_type": "chain_token", "target_id": "eip155:1:0xAbC"},
        {"target_type": "cex_symbol", "target_id": "binance:BTCUSDT"},
    ]


def test_market_tick_poll_worker_preserves_gmgn_quote_source_provider() -> None:
    state = FakeSessionState()
    repos = FakeRepos(state, [tier_row(target_type="chain_token", target_id="eip155:1:0xAbC")])
    dex_provider = FakeDexQuoteProvider(
        state,
        [
            DexTokenQuote(
                chain_id="eip155:1",
                address="0xabc",
                observed_at_ms=1_800_000_000_010,
                price_usd=12.34,
                raw={"source_provider": "gmgn_dex_quote"},
                market_cap_usd=1234.5,
                liquidity_usd=678.9,
                volume_24h_usd=10.11,
                holders=222,
            )
        ],
    )
    worker = MarketTickPollWorker(
        pool_bundle=FakeDB(state, repos),
        providers=FakeProviders(dex_quote_market=dex_provider, cex_market=None),
        clock=lambda: 1_800_000_000_100,
    )

    result = asyncio.run(worker.run_once())

    assert result.processed == 1
    assert repos.market_ticks.inserted[0].source_provider == "gmgn_dex_quote"
    assert repos.market_ticks.inserted[0].tick_id == market_tick_id(
        target_type="chain_token",
        target_id="eip155:1:0xAbC",
        source_provider="gmgn_dex_quote",
        observed_at_ms=1_800_000_000_010,
    )


def test_market_tick_poll_worker_skips_bad_targets_unavailable_quotes_and_provider_failures() -> None:
    state = FakeSessionState()
    repos = FakeRepos(
        state,
        [
            tier_row(target_type="chain_token", target_id="bad-chain-token"),
            tier_row(target_type="cex_symbol", target_id="bad-cex-symbol"),
            tier_row(target_type="nonsense", target_id="binance:ETHUSDT"),
            tier_row(target_type="chain_token", target_id="solana:missing"),
            tier_row(target_type="chain_token", target_id="solana:failing"),
            tier_row(target_type="cex_symbol", target_id="binance:MISSINGUSDT"),
            tier_row(target_type="cex_symbol", target_id="binance:FAILUSDT"),
        ],
    )
    dex_provider = FakeDexQuoteProvider(
        state,
        [],
        failures={("solana", "failing"): RuntimeError("dex unavailable")},
    )
    cex_provider = FakeCexProvider(
        state,
        {"FAILUSDT": RuntimeError("cex unavailable")},
    )
    wake = FakeWakeEmitter()
    worker = MarketTickPollWorker(
        pool_bundle=FakeDB(state, repos),
        providers=FakeProviders(dex_quote_market=dex_provider, cex_market=cex_provider),
        wake_emitter=wake,
        batch_size=20,
    )

    result = asyncio.run(worker.run_once())

    assert result.processed == 0
    assert result.skipped == 7
    assert result.notes["targets_selected"] == 7
    assert result.notes["ticks_attempted"] == 0
    assert repos.market_ticks.inserted == []
    assert repos.conn.commit_count == 0
    assert wake.market_tick_notifications == []
    assert dex_provider.saw_in_session == [False, False, False]
    # Batch records both in order; individual fallback runs the two retries
    # via asyncio.gather so their relative order is non-deterministic.
    assert dex_provider.requests[:2] == [("solana", "missing"), ("solana", "failing")]
    assert sorted(dex_provider.requests[2:]) == sorted(
        [("solana", "missing"), ("solana", "failing")],
    )
    assert cex_provider.saw_in_session == [False, False]


def test_market_tick_poll_worker_retries_dex_batch_individually_to_preserve_valid_ticks() -> None:
    state = FakeSessionState()
    repos = FakeRepos(
        state,
        [
            tier_row(target_type="chain_token", target_id="solana:Good"),
            tier_row(target_type="chain_token", target_id="solana:Failing"),
        ],
    )
    dex_provider = FakeDexQuoteProvider(
        state,
        [
            DexTokenQuote(
                chain_id="solana",
                address="Good",
                observed_at_ms=1_800_000_000_001,
                price_usd=7.89,
                raw={"provider": "dex"},
            )
        ],
        failures={("solana", "Failing"): RuntimeError("dex unavailable")},
    )
    wake = FakeWakeEmitter()
    worker = MarketTickPollWorker(
        pool_bundle=FakeDB(state, repos),
        providers=FakeProviders(dex_quote_market=dex_provider, cex_market=None),
        wake_emitter=wake,
        clock=lambda: 1_800_000_000_100,
    )

    result = asyncio.run(worker.run_once())

    assert result.processed == 1
    assert result.skipped == 1
    assert result.notes["ticks_attempted"] == 1
    assert len(repos.market_ticks.inserted) == 1
    assert repos.market_ticks.inserted[0].target_id == "solana:Good"
    assert repos.market_ticks.inserted[0].source_provider == "okx_dex_rest"
    assert wake.market_tick_notifications == [{"target_type": "chain_token", "target_id": "solana:Good"}]
    assert dex_provider.saw_in_session == [False, False, False]
    # Batch records both targets in order; the individual fallback runs the two
    # retries via asyncio.gather so their relative order is non-deterministic.
    assert dex_provider.requests[:2] == [("solana", "Good"), ("solana", "Failing")]
    assert sorted(dex_provider.requests[2:]) == sorted(
        [("solana", "Good"), ("solana", "Failing")],
    )


@pytest.mark.parametrize("bad_price", [None, 0, -1, "not-a-price", float("nan"), float("inf")])
def test_market_tick_poll_worker_rejects_invalid_non_finite_and_non_positive_prices(bad_price) -> None:
    state = FakeSessionState()
    repos = FakeRepos(
        state,
        [
            tier_row(target_type="chain_token", target_id="solana:BadDex"),
            tier_row(target_type="cex_symbol", target_id="binance:BADUSDT"),
        ],
    )
    dex_provider = FakeDexQuoteProvider(
        state,
        [
            DexTokenQuote(
                chain_id="solana",
                address="BadDex",
                observed_at_ms=1,
                price_usd=bad_price,
                raw={},
            )
        ],
    )
    cex_provider = FakeCexProvider(
        state,
        {
            "BADUSDT": CexTicker(
                inst_id="BADUSDT",
                inst_type="SWAP",
                last_price=bad_price,
                volume_24h=None,
                open_interest=None,
                raw={"ts": 2},
            )
        },
    )
    wake = FakeWakeEmitter()
    worker = MarketTickPollWorker(
        pool_bundle=FakeDB(state, repos),
        providers=FakeProviders(dex_quote_market=dex_provider, cex_market=cex_provider),
        wake_emitter=wake,
    )

    result = asyncio.run(worker.run_once())

    assert result.processed == 0
    assert result.skipped == 2
    assert repos.market_ticks.inserted == []
    assert repos.conn.commit_count == 0
    assert wake.market_tick_notifications == []


def test_market_tick_poll_worker_reselects_from_freshness_order_each_run() -> None:
    state = FakeSessionState()
    repos = FakeRepos(
        state,
        [tier_row(target_type="cex_symbol", target_id=f"binance:SYM{i}USDT") for i in range(4)],
        sort_fresh_targets_last=True,
    )
    provider = FakeCexProvider(
        state,
        {
            f"SYM{i}USDT": CexTicker(
                inst_id=f"SYM{i}USDT",
                inst_type="SPOT",
                last_price=Decimal(i + 1),
                volume_24h=None,
                open_interest=None,
                raw={"ts": str(1_800_000_000_000 + i)},
            )
            for i in range(4)
        },
    )
    worker = MarketTickPollWorker(
        pool_bundle=FakeDB(state, repos),
        providers=FakeProviders(dex_quote_market=None, cex_market=provider),
        batch_size=2,
        settings=SimpleNamespace(
            enabled=True,
            interval_seconds=5.0,
            timeout_seconds=120.0,
            batch_size=2,
            concurrency=2,
        ),
    )

    asyncio.run(worker.run_once())
    asyncio.run(worker.run_once())

    assert repos.token_capture_tiers.calls == [
        {"tier": 2, "limit": 2},
        {
            "tier": 2,
            "limit": 2,
            "exclude_keys": [
                {"target_type": "cex_symbol", "target_id": "binance:SYM0USDT"},
                {"target_type": "cex_symbol", "target_id": "binance:SYM1USDT"},
            ],
        },
    ]
    assert set(provider.requests[:2]) == {"SYM0USDT", "SYM1USDT"}
    assert set(provider.requests[2:]) == {"SYM2USDT", "SYM3USDT"}


def test_market_tick_poll_worker_uses_stable_freshness_order_without_empty_page_wrap() -> None:
    state = FakeSessionState()
    repos = FakeRepos(
        state,
        [tier_row(target_type="cex_symbol", target_id=f"binance:SYM{i}USDT") for i in range(3)],
    )
    worker = MarketTickPollWorker(
        pool_bundle=FakeDB(state, repos),
        providers=FakeProviders(dex_quote_market=None, cex_market=FakeCexProvider(state, {})),
        batch_size=2,
        settings=SimpleNamespace(
            enabled=True,
            interval_seconds=5.0,
            timeout_seconds=120.0,
            batch_size=2,
            concurrency=2,
        ),
    )

    asyncio.run(worker.run_once())
    asyncio.run(worker.run_once())  # same freshness-ordered query, no cursor state

    assert repos.token_capture_tiers.calls == [
        {"tier": 2, "limit": 2},
        {
            "tier": 2,
            "limit": 2,
            "exclude_keys": [
                {"target_type": "cex_symbol", "target_id": "binance:SYM0USDT"},
                {"target_type": "cex_symbol", "target_id": "binance:SYM1USDT"},
            ],
        },
    ]


def test_market_tick_poll_worker_rotates_recently_attempted_no_quote_targets_without_offset() -> None:
    state = FakeSessionState()
    repos = FakeRepos(
        state,
        [tier_row(target_type="cex_symbol", target_id=f"binance:SYM{i}USDT") for i in range(4)],
    )
    provider = FakeCexProvider(state, {})
    worker = MarketTickPollWorker(
        pool_bundle=FakeDB(state, repos),
        providers=FakeProviders(dex_quote_market=None, cex_market=provider),
        batch_size=2,
        settings=SimpleNamespace(
            enabled=True,
            interval_seconds=5.0,
            timeout_seconds=120.0,
            batch_size=2,
            concurrency=2,
        ),
    )

    asyncio.run(worker.run_once())
    asyncio.run(worker.run_once())

    assert set(provider.requests[:2]) == {"SYM0USDT", "SYM1USDT"}
    assert set(provider.requests[2:]) == {"SYM2USDT", "SYM3USDT"}
    assert repos.token_capture_tiers.calls == [
        {"tier": 2, "limit": 2},
        {
            "tier": 2,
            "limit": 2,
            "exclude_keys": [
                {"target_type": "cex_symbol", "target_id": "binance:SYM0USDT"},
                {"target_type": "cex_symbol", "target_id": "binance:SYM1USDT"},
            ],
        },
    ]


def test_market_tick_poll_worker_polls_cex_targets_with_bounded_concurrency() -> None:
    state = FakeSessionState()
    repos = FakeRepos(
        state,
        [tier_row(target_type="cex_symbol", target_id=f"binance:SYM{i}USDT") for i in range(4)],
    )
    provider = BlockingCexProvider(state)
    worker = MarketTickPollWorker(
        pool_bundle=FakeDB(state, repos),
        providers=FakeProviders(dex_quote_market=None, cex_market=provider),
        batch_size=4,
        settings=SimpleNamespace(
            enabled=True,
            interval_seconds=5.0,
            timeout_seconds=120.0,
            batch_size=4,
            concurrency=2,
        ),
    )

    async def driver() -> WorkerResult:
        task = asyncio.create_task(worker.run_once())
        await provider.wait_until_active(2)
        provider.release_all()
        return await task

    result = asyncio.run(driver())

    assert provider.max_active == 2
    assert result.processed == 0  # tickers map is empty, so all CEX skipped
    assert sorted(provider.requests) == ["SYM0USDT", "SYM1USDT", "SYM2USDT", "SYM3USDT"]
    # All 4 targets must be attempted, none in-session.
    assert len(provider.saw_in_session) == 4
    assert all(not seen for seen in provider.saw_in_session)


def tier_row(*, target_type: str, target_id: str) -> dict[str, object]:
    return {
        "target_type": target_type,
        "target_id": target_id,
        "tier": 2,
        "reason": "batch_poll",
        "score": Decimal("1"),
        "updated_at_ms": 1_800_000_000_000,
    }


class FakeSessionState:
    def __init__(self) -> None:
        self.in_session = False


class FakeRepos:
    def __init__(
        self,
        state: FakeSessionState,
        tier_rows: list[dict[str, object]],
        *,
        sort_fresh_targets_last: bool = False,
    ) -> None:
        self.market_ticks = FakeMarketTicks(state)
        self.token_radar_dirty_targets = FakeDirtyTargets()
        self.token_capture_tiers = FakeTokenCaptureTiers(
            tier_rows,
            market_ticks=self.market_ticks,
            sort_fresh_targets_last=sort_fresh_targets_last,
        )
        self.conn = FakeConn()


class FakeTokenCaptureTiers:
    def __init__(
        self,
        rows: list[dict[str, object]],
        *,
        market_ticks: FakeMarketTicks,
        sort_fresh_targets_last: bool = False,
    ) -> None:
        self.rows = rows
        self.market_ticks = market_ticks
        self.sort_fresh_targets_last = sort_fresh_targets_last
        self.calls: list[dict[str, Any]] = []

    def list_by_tier(
        self,
        tier: int,
        limit: int,
        *,
        exclude_keys: list[dict[str, str]] | None = None,
    ) -> list[dict[str, object]]:
        call = {"tier": tier, "limit": limit}
        if exclude_keys is not None:
            call["exclude_keys"] = list(exclude_keys)
        self.calls.append(call)
        rows = list(self.rows)
        if exclude_keys:
            excluded = {(item["target_type"], item["target_id"]) for item in exclude_keys}
            rows = [row for row in rows if (str(row["target_type"]), str(row["target_id"])) not in excluded]
        if self.sort_fresh_targets_last:
            fresh = self.market_ticks.inserted_target_ids
            rows.sort(key=lambda row: (str(row["target_id"]) in fresh, str(row["target_id"])))
        return rows[:limit]


class FakeMarketTicks:
    def __init__(self, state: FakeSessionState) -> None:
        self.state = state
        self.inserted = []
        self.inserted_target_ids: set[str] = set()

    def insert_ticks(self, ticks) -> int:
        return len(self.insert_ticks_returning_ids(ticks))

    def insert_ticks_returning_ids(self, ticks) -> list[str]:
        assert self.state.in_session is True
        self.inserted.extend(ticks)
        self.inserted_target_ids.update(str(tick.target_id) for tick in ticks)
        return [str(tick.tick_id) for tick in ticks]


class FakeDirtyTargets:
    def __init__(self) -> None:
        self.enqueues: list[dict[str, object]] = []

    def enqueue_market_targets(self, rows, *, reason, now_ms, commit) -> int:
        self.enqueues.append({"rows": list(rows), "reason": reason, "now_ms": now_ms, "commit": commit})
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


class FakeProviders(SimpleNamespace):
    dex_quote_market: FakeDexQuoteProvider | None
    cex_market: FakeCexProvider | None


class FakeDexQuoteProvider:
    def __init__(
        self,
        state: FakeSessionState,
        quotes: list[DexTokenQuote],
        *,
        failures: dict[tuple[str, str], Exception] | None = None,
    ) -> None:
        self.state = state
        self.quotes = quotes
        self.failures = failures or {}
        self.requests: list[tuple[str, str]] = []
        self.saw_in_session: list[bool] = []

    def token_quotes(self, requests):
        self.saw_in_session.append(self.state.in_session)
        self.requests.extend((request.chain_id, request.address) for request in requests)
        for request in requests:
            exc = self.failures.get((request.chain_id, request.address))
            if exc is not None:
                raise exc
        requested = {(request.chain_id, request.address.lower()) for request in requests}
        return [quote for quote in self.quotes if (quote.chain_id, quote.address.lower()) in requested]


class FakeCexProvider:
    def __init__(self, state: FakeSessionState, tickers: dict[str, CexTicker | Exception]) -> None:
        self.state = state
        self.tickers = tickers
        self.requests: list[str] = []
        self.saw_in_session: list[bool] = []

    def ticker(self, *, inst_id: str):
        self.saw_in_session.append(self.state.in_session)
        self.requests.append(inst_id)
        result = self.tickers.get(inst_id)
        if isinstance(result, Exception):
            raise result
        return result


class BlockingCexProvider:
    """CEX provider that blocks each ticker() call (in a thread pool) until released.

    Records max concurrent active calls so tests can assert bounded concurrency.
    """

    def __init__(self, state: FakeSessionState) -> None:
        self.state = state
        self.requests: list[str] = []
        self.saw_in_session: list[bool] = []
        self._gate = threading.Event()
        self._lock = threading.Lock()
        self._active = 0
        self.max_active = 0
        self._target_active = 0
        self._target_reached = asyncio.Event()
        self._loop: asyncio.AbstractEventLoop | None = None

    async def wait_until_active(self, count: int) -> None:
        self._loop = asyncio.get_running_loop()
        self._target_active = count
        with self._lock:
            already = self._active >= count
        if already:
            return
        await self._target_reached.wait()

    def release_all(self) -> None:
        self._gate.set()

    def ticker(self, *, inst_id: str):
        self.saw_in_session.append(self.state.in_session)
        self.requests.append(inst_id)
        with self._lock:
            self._active += 1
            self.max_active = max(self.max_active, self._active)
            reached = self._active >= self._target_active and self._target_active > 0
        if reached and self._loop is not None:
            self._loop.call_soon_threadsafe(self._target_reached.set)
        try:
            self._gate.wait(timeout=5.0)
        finally:
            with self._lock:
                self._active -= 1


class FakeWakeEmitter:
    def __init__(self) -> None:
        self.channels: list[str] = []
        self.market_tick_notifications: list[dict[str, str]] = []

    def notify_market_tick_written(self, *, target_type: str, target_id: str) -> None:
        self.channels.append("market_tick_written")
        self.market_tick_notifications.append({"target_type": target_type, "target_id": target_id})

    def __getattr__(self, name: str):
        if name == f"notify_{'_'.join(('market', 'observation', 'written'))}":
            raise AssertionError("market_tick_poll must not emit legacy market wakes")
        raise AttributeError(name)
