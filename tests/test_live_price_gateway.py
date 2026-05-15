from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.domains.asset_market.providers import DexMarketFactUpdate
from gmgn_twitter_intel.domains.asset_market.runtime.live_price_gateway import LivePriceGateway


def test_live_price_gateway_caches_and_publishes_without_market_fact_writes():
    db = FakeDB()
    wake_bus = ForbiddenWakeBus()
    stream_provider = FakeStreamProvider(
        [
            DexMarketFactUpdate(
                chain_id="solana",
                address="abc",
                observed_at_ms=1_778_000_000_500,
                price_usd=0.42,
                raw={"price": "0.42"},
            )
        ]
    )
    published: list[dict] = []
    gateway = LivePriceGateway(
        name="live_price_gateway",
        settings=worker_settings(),
        db=db,
        telemetry=object(),
        stream_provider=stream_provider,
        cex_market=None,
        projection_version="token-radar-v12-anchor-live-hard-cut",
        on_live_market_update=published.append,
        wake_bus=wake_bus,
    )

    result = asyncio.run(gateway.run_once(now_ms=1_778_000_000_000))

    assert isinstance(result, WorkerResult)
    assert result.notes["result"]["updates_received"] == 1
    assert result.processed == 1
    assert result.notes["result"]["live_market_updates_published"] == 1
    db.repos.assert_no_market_fact_access()
    assert wake_bus.touched is False
    assert published[0]["type"] == "live_market_update"
    assert published[0]["market"]["decision_latest"]["price_usd"] == 0.42
    assert published[0]["market"]["decision_latest"]["source"] == "decision_latest"
    assert "live_market" not in published[0]
    assert (
        gateway.snapshot(target_type="Asset", target_id="asset:solana:token:abc", now_ms=1_778_000_001_500)["status"]
        == "live"
    )


def test_live_price_gateway_does_not_block_event_loop_while_selecting_targets():
    db = FakeDB()
    db.repos.registry.sleep_seconds = 0.3
    gateway = LivePriceGateway(
        name="live_price_gateway",
        settings=worker_settings(reconnect_delay_seconds=0.1),
        db=db,
        telemetry=object(),
        stream_provider=None,
        cex_market=None,
        projection_version="token-radar-v12-anchor-live-hard-cut",
    )

    async def run_probe() -> None:
        started = time.monotonic()
        run_task = asyncio.create_task(gateway.run_once(now_ms=1_778_000_000_000))
        await asyncio.sleep(0.05)
        elapsed = time.monotonic() - started
        assert elapsed < 0.2
        await run_task

    asyncio.run(run_probe())


def test_live_price_gateway_run_paces_empty_stream_cycles():
    db = FakeDB()
    gateway = LivePriceGateway(
        name="live_price_gateway",
        settings=worker_settings(cex_poll_interval_seconds=0.1, reconnect_delay_seconds=0.01),
        db=db,
        telemetry=object(),
        stream_provider=None,
        cex_market=None,
        projection_version="token-radar-v12-anchor-live-hard-cut",
    )

    async def run_probe() -> None:
        task = asyncio.create_task(gateway.run())
        await asyncio.sleep(0.03)
        assert db.repos.registry.target_query_count == 1
        await gateway.stop()
        await asyncio.wait_for(task, timeout=0.5)

    asyncio.run(run_probe())


def test_live_price_gateway_bounds_dex_stream_cycle_when_no_updates_arrive():
    db = FakeDB()
    stream_provider = BlockingStreamProvider()
    gateway = LivePriceGateway(
        name="live_price_gateway",
        settings=worker_settings(cex_poll_interval_seconds=1, reconnect_delay_seconds=0.1),
        db=db,
        telemetry=object(),
        stream_provider=stream_provider,
        cex_market=None,
        projection_version="token-radar-v12-anchor-live-hard-cut",
    )

    result = asyncio.run(asyncio.wait_for(gateway.run_once(now_ms=1_778_000_000_000), timeout=2.0))

    assert result.notes["result"]["dex_targets_selected"] == 1
    assert result.notes["result"]["updates_received"] == 0
    assert stream_provider.closed is True


def test_live_price_gateway_publishes_every_valid_live_update_without_debounce():
    db = FakeDB()
    stream_provider = FakeStreamProvider(
        [
            DexMarketFactUpdate(
                chain_id="solana",
                address="abc",
                observed_at_ms=1_778_000_001_000,
                price_usd=1.0001,
                raw={"price": "1.0001"},
            )
        ],
    )
    published: list[dict] = []
    gateway = LivePriceGateway(
        name="live_price_gateway",
        settings=worker_settings(),
        db=db,
        telemetry=object(),
        stream_provider=stream_provider,
        cex_market=None,
        projection_version="token-radar-v12-anchor-live-hard-cut",
        on_live_market_update=published.append,
    )

    result = asyncio.run(gateway.run_once(now_ms=1_778_000_001_000))

    assert result.processed == 1
    assert result.notes["result"]["live_market_updates_published"] == 1
    assert len(published) == 1
    assert published[0]["market"]["decision_latest"]["price_usd"] == 1.0001
    db.repos.assert_no_market_fact_access()


class FakeStreamProvider:
    def __init__(self, updates: list[DexMarketFactUpdate], state_payloads: list[dict] | None = None) -> None:
        self.updates = updates
        self.targets: list[dict] = []
        self.state_payloads = list(state_payloads or [{"state": "streaming", "last_state_change_at_ms": 1}])
        self._state_index = 0

    def connection_state_payload(self):
        value = self.state_payloads[min(self._state_index, len(self.state_payloads) - 1)]
        self._state_index += 1
        return dict(value)

    async def stream_price_info(self, targets):
        self.targets = [
            {
                "chain_id": target.chain_id,
                "address": target.address,
                "subject_type": target.subject_type,
                "subject_id": target.subject_id,
            }
            for target in targets
        ]
        for update in self.updates:
            yield update


class BlockingStreamProvider:
    def __init__(self) -> None:
        self.closed = False

    async def stream_price_info(self, targets):
        try:
            await asyncio.sleep(10)
            if False:
                yield
        finally:
            self.closed = True


def worker_settings(**overrides):
    values = {
        "enabled": True,
        "interval_seconds": 30.0,
        "timeout_seconds": 120.0,
        "subscription_limit": 10,
        "hot_target_ttl_seconds": 60.0,
        "reconnect_delay_seconds": 0.1,
        "cex_poll_interval_seconds": 30.0,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class FakeDB:
    def __init__(self) -> None:
        self.repos = FakeRepos()
        self.session_names: list[str] = []

    def worker_session(self, name: str):
        self.session_names.append(name)
        return FakeSession(self.repos)


class FakeSession:
    def __init__(self, repos):
        self.repos = repos

    def __enter__(self):
        return self.repos

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeRepos:
    def __init__(self) -> None:
        self.registry = FakeRegistry()
        self.price_observations = ForbiddenRepository("price_observations")
        self.market_ticks = ForbiddenRepository("market_ticks")
        self.enriched_events = ForbiddenRepository("enriched_events")

    def assert_no_market_fact_access(self) -> None:
        assert self.price_observations.touched is False
        assert self.market_ticks.touched is False
        assert self.enriched_events.touched is False


class FakeRegistry:
    def __init__(self) -> None:
        self.target_query: dict | None = None
        self.target_query_count = 0
        self.sleep_seconds = 0.0

    def active_live_market_targets(self, *, projection_version, since_ms, limit):
        if self.sleep_seconds:
            time.sleep(self.sleep_seconds)
        self.target_query_count += 1
        self.target_query = {"projection_version": projection_version, "since_ms": since_ms, "limit": limit}
        return [
            {
                "target_type": "Asset",
                "target_id": "asset:solana:token:abc",
                "chain_id": "solana",
                "address": "abc",
                "native_market_id": None,
                "quote_symbol": None,
                "provider": "okx",
            }
        ]


class ForbiddenRepository:
    def __init__(self, name: str) -> None:
        self.name = name
        self.touched = False

    def __getattr__(self, method_name: str):
        self.touched = True
        raise AssertionError(f"LivePriceGateway must not touch {self.name}.{method_name}")


class ForbiddenWakeBus:
    def __init__(self) -> None:
        self.touched = False

    def __getattr__(self, method_name: str):
        self.touched = True
        raise AssertionError(f"LivePriceGateway must not touch wake bus method {method_name}")
