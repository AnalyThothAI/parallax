from __future__ import annotations

import asyncio

from gmgn_twitter_intel.domains.asset_market.providers import DexMarketFactUpdate
from gmgn_twitter_intel.domains.asset_market.runtime.live_price_gateway import LivePriceGateway


def test_live_price_gateway_publishes_update_without_writing_observation():
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
    assert result["observations_written"] == 0
    assert repos.price_observations.calls == []
    assert repos.legacy_market_read_calls == []
    assert published == [
        {
            "type": "live_market_update",
            "provider": "okx_dex_ws_price_info",
            "target_type": "Asset",
            "target_id": "asset:solana:token:abc",
            "observed_at_ms": 1_778_000_000_500,
            "live_market": {
                "status": "live",
                "price_usd": 0.42,
                "price_quote": None,
                "quote_symbol": "USD",
                "price_basis": "usd",
                "market_cap_usd": None,
                "liquidity_usd": None,
                "holders": None,
                "volume_24h_usd": None,
                "observed_at_ms": 1_778_000_000_500,
                "received_at_ms": 1_778_000_000_000,
                "age_ms": 0,
                "provider": "okx_dex_ws_price_info",
            },
        }
    ]
    assert (
        gateway.snapshot(target_type="Asset", target_id="asset:solana:token:abc", now_ms=1_778_000_001_500)["status"]
        == "live"
    )


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
        self.legacy_market_read_calls: list[dict] = []


class FakeRegistry:
    def __init__(self) -> None:
        self.target_query: dict | None = None

    def active_live_market_targets(self, *, projection_version, since_ms, limit):
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

    def insert_observation(self, **kwargs):
        self.calls.append(kwargs)
        return {}
