from __future__ import annotations

import asyncio

from gmgn_twitter_intel.domains.asset_market.providers import DexMarketFactUpdate
from gmgn_twitter_intel.domains.asset_market.runtime.live_price_gateway import LivePriceGateway


def test_live_price_gateway_persists_only_material_decision_latest_frames():
    repos = FakeRepos()
    stream_provider = FakeStreamProvider(
        [
            DexMarketFactUpdate(
                chain_id="solana",
                address="abc",
                observed_at_ms=1_778_000_000_000,
                price_usd=1.0,
                raw={"price": "1.0"},
            ),
            DexMarketFactUpdate(
                chain_id="solana",
                address="abc",
                observed_at_ms=1_778_000_001_000,
                price_usd=1.0001,
                raw={"price": "1.0001"},
            ),
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
        live_observation_heartbeat_seconds=60,
        live_observation_min_price_change_pct=0.005,
        live_observation_min_write_interval_seconds=5,
    )

    result = asyncio.run(gateway.run_once(now_ms=1_778_000_000_000))

    assert result["updates_received"] == 2
    assert result["observations_written"] == 1
    assert len(repos.price_observations.calls) == 1
    assert repos.price_observations.calls[0]["observation_kind"] == "decision_latest"
    assert published[0]["market"]["decision_latest"]["price_usd"] == 1.0


class FakeStreamProvider:
    def __init__(self, updates: list[DexMarketFactUpdate]) -> None:
        self.updates = updates

    async def stream_price_info(self, targets):
        for update in self.updates:
            yield update


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
    def active_live_market_targets(self, *, projection_version, since_ms, limit):
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
        self.calls.append({"observation": observation, "observation_kind": observation_kind, "commit": commit})
        self.latest[(observation.target.target_type, observation.target.target_id)] = observation
        return "observation-id"
