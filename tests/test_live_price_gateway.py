from __future__ import annotations

import asyncio
import time

from gmgn_twitter_intel.domains.asset_market.providers import DexMarketFactUpdate
from gmgn_twitter_intel.domains.asset_market.runtime.live_price_gateway import LivePriceGateway


def test_live_price_gateway_persists_and_publishes_first_material_update():
    repos = FakeRepos()
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
        stream_provider=stream_provider,
        cex_market=None,
        repository_session=lambda: FakeSession(repos),
        projection_version="token-radar-v12-anchor-live-hard-cut",
        subscription_limit=10,
        hot_target_ttl_seconds=60,
        cex_poll_interval_seconds=30,
        reconnect_delay_seconds=0.1,
        on_live_market_update=published.append,
    )

    result = asyncio.run(gateway.run_once(now_ms=1_778_000_000_000))

    assert result["updates_received"] == 1
    assert result["observations_written"] == 1
    assert len(repos.price_observations.calls) == 1
    assert published[0]["type"] == "live_market_update"
    assert published[0]["market"]["decision_latest"]["price_usd"] == 0.42
    assert published[0]["market"]["decision_latest"]["source"] == "decision_latest"
    assert "live_market" not in published[0]
    assert (
        gateway.snapshot(target_type="Asset", target_id="asset:solana:token:abc", now_ms=1_778_000_001_500)["status"]
        == "live"
    )


def test_live_price_gateway_does_not_block_event_loop_while_selecting_targets():
    repos = FakeRepos()
    repos.registry.sleep_seconds = 0.3
    gateway = LivePriceGateway(
        stream_provider=None,
        cex_market=None,
        repository_session=lambda: FakeSession(repos),
        projection_version="token-radar-v12-anchor-live-hard-cut",
        subscription_limit=10,
        hot_target_ttl_seconds=60,
        reconnect_delay_seconds=0.1,
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
    repos = FakeRepos()
    gateway = LivePriceGateway(
        stream_provider=None,
        cex_market=None,
        repository_session=lambda: FakeSession(repos),
        projection_version="token-radar-v12-anchor-live-hard-cut",
        subscription_limit=10,
        hot_target_ttl_seconds=60,
        cex_poll_interval_seconds=0.1,
        reconnect_delay_seconds=0.01,
    )

    async def run_probe() -> None:
        task = asyncio.create_task(gateway.run())
        await asyncio.sleep(0.03)
        assert repos.registry.target_query_count == 1
        gateway.stop()
        await asyncio.wait_for(task, timeout=0.5)

    asyncio.run(run_probe())


def test_live_price_gateway_bounds_dex_stream_cycle_when_no_updates_arrive():
    repos = FakeRepos()
    stream_provider = BlockingStreamProvider()
    gateway = LivePriceGateway(
        stream_provider=stream_provider,
        cex_market=None,
        repository_session=lambda: FakeSession(repos),
        projection_version="token-radar-v12-anchor-live-hard-cut",
        subscription_limit=10,
        hot_target_ttl_seconds=60,
        cex_poll_interval_seconds=1,
        reconnect_delay_seconds=0.1,
    )

    result = asyncio.run(asyncio.wait_for(gateway.run_once(now_ms=1_778_000_000_000), timeout=2.0))

    assert result["dex_targets_selected"] == 1
    assert result["updates_received"] == 0
    assert stream_provider.closed is True


class FakeStreamProvider:
    def __init__(self, updates: list[DexMarketFactUpdate]) -> None:
        self.updates = updates
        self.targets: list[dict] = []

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
        self.price_observations = FakePriceObservations()


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


class FakePriceObservations:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.latest = {}

    def latest_for_target(self, *, target_type, target_id, now_ms, max_age_ms):
        return self.latest.get((target_type, target_id))

    def insert_market_observation(
        self,
        observation,
        *,
        observation_kind,
        source_event_id,
        source_intent_id,
        source_resolution_id,
        event_received_at_ms,
        commit,
    ):
        self.calls.append(
            {
                "observation": observation,
                "observation_kind": observation_kind,
                "source_event_id": source_event_id,
                "source_intent_id": source_intent_id,
                "source_resolution_id": source_resolution_id,
                "event_received_at_ms": event_received_at_ms,
                "commit": commit,
            }
        )
        self.latest[(observation.target.target_type, observation.target.target_id)] = observation
        return "observation-id"
