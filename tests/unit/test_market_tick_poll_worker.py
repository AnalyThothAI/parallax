from __future__ import annotations

import asyncio
from decimal import Decimal
from types import SimpleNamespace

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
        providers=FakeProviders(dex_quote_market=None, message_cex_market=None),
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
            tier_row(target_type="cex_symbol", target_id="okx:BTC-USDT-SWAP"),
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
            )
        ],
    )
    cex_provider = FakeCexProvider(
        state,
        {
            "BTC-USDT-SWAP": CexTicker(
                inst_id="BTC-USDT-SWAP",
                inst_type="SWAP",
                last_price=50_123.4,
                volume_24h=999.8,
                open_interest=333.2,
                raw={"ts": "1800000000020", "provider": "cex"},
            )
        },
    )
    wake = FakeWakeEmitter()
    worker = MarketTickPollWorker(
        pool_bundle=FakeDB(state, repos),
        providers=FakeProviders(dex_quote_market=dex_provider, message_cex_market=cex_provider),
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
    assert cex_provider.requests == ["BTC-USDT-SWAP"]
    assert repos.conn.commit_count == 1
    assert len(repos.market_ticks.inserted) == 2

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
    assert dex_tick.raw_payload_json == {"provider": "dex"}

    assert cex_tick.tick_id == market_tick_id(
        target_type="cex_symbol",
        target_id="okx:BTC-USDT-SWAP",
        source_provider="okx_cex_rest",
        observed_at_ms=1_800_000_000_020,
    )
    assert cex_tick.target_type == "cex_symbol"
    assert cex_tick.target_id == "okx:BTC-USDT-SWAP"
    assert cex_tick.chain is None
    assert cex_tick.token_address is None
    assert cex_tick.exchange == "okx"
    assert cex_tick.instrument == "BTC-USDT-SWAP"
    assert cex_tick.source_tier == "tier2_poll"
    assert cex_tick.source_provider == "okx_cex_rest"
    assert cex_tick.price_usd == Decimal("50123.4")
    assert cex_tick.volume_24h_usd == Decimal("999.8")
    assert cex_tick.market_cap_usd is None
    assert cex_tick.raw_payload_json == {"ts": "1800000000020", "provider": "cex"}
    assert wake.channels == ["market_tick_written", "market_tick_written"]
    assert wake.market_tick_notifications == [
        {"target_type": "chain_token", "target_id": "eip155:1:0xAbC"},
        {"target_type": "cex_symbol", "target_id": "okx:BTC-USDT-SWAP"},
    ]


def test_market_tick_poll_worker_skips_bad_targets_unavailable_quotes_and_provider_failures() -> None:
    state = FakeSessionState()
    repos = FakeRepos(
        state,
        [
            tier_row(target_type="chain_token", target_id="bad-chain-token"),
            tier_row(target_type="cex_symbol", target_id="bad-cex-symbol"),
            tier_row(target_type="nonsense", target_id="okx:ETH-USDT-SWAP"),
            tier_row(target_type="chain_token", target_id="solana:missing"),
            tier_row(target_type="chain_token", target_id="solana:failing"),
            tier_row(target_type="cex_symbol", target_id="okx:MISSING-USDT-SWAP"),
            tier_row(target_type="cex_symbol", target_id="okx:FAIL-USDT-SWAP"),
        ],
    )
    dex_provider = FakeDexQuoteProvider(
        state,
        [],
        failures={("solana", "failing"): RuntimeError("dex unavailable")},
    )
    cex_provider = FakeCexProvider(
        state,
        {"FAIL-USDT-SWAP": RuntimeError("cex unavailable")},
    )
    wake = FakeWakeEmitter()
    worker = MarketTickPollWorker(
        pool_bundle=FakeDB(state, repos),
        providers=FakeProviders(dex_quote_market=dex_provider, message_cex_market=cex_provider),
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
    assert dex_provider.saw_in_session == [False]
    assert dex_provider.requests == [("solana", "missing"), ("solana", "failing")]
    assert cex_provider.saw_in_session == [False, False]


@pytest.mark.parametrize("bad_price", [None, 0, -1, "not-a-price", float("nan"), float("inf")])
def test_market_tick_poll_worker_rejects_invalid_non_finite_and_non_positive_prices(bad_price) -> None:
    state = FakeSessionState()
    repos = FakeRepos(
        state,
        [
            tier_row(target_type="chain_token", target_id="solana:BadDex"),
            tier_row(target_type="cex_symbol", target_id="okx:BAD-USDT-SWAP"),
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
            "BAD-USDT-SWAP": CexTicker(
                inst_id="BAD-USDT-SWAP",
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
        providers=FakeProviders(dex_quote_market=dex_provider, message_cex_market=cex_provider),
        wake_emitter=wake,
    )

    result = asyncio.run(worker.run_once())

    assert result.processed == 0
    assert result.skipped == 2
    assert repos.market_ticks.inserted == []
    assert repos.conn.commit_count == 0
    assert wake.market_tick_notifications == []


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


class FakeProviders(SimpleNamespace):
    dex_quote_market: FakeDexQuoteProvider | None
    message_cex_market: FakeCexProvider | None


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


class FakeWakeEmitter:
    def __init__(self) -> None:
        self.channels: list[str] = []
        self.market_tick_notifications: list[dict[str, str]] = []

    def notify_market_tick_written(self, *, target_type: str, target_id: str) -> None:
        self.channels.append("market_tick_written")
        self.market_tick_notifications.append({"target_type": target_type, "target_id": target_id})

    def notify_market_observation_written(self, *, target_type: str, target_id: str) -> None:
        raise AssertionError("market_tick_poll must not emit legacy market observation wakes")
