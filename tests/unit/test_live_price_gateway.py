from __future__ import annotations

import asyncio
from types import SimpleNamespace

from gmgn_twitter_intel.domains.asset_market.providers import DexMarketFactUpdate
from gmgn_twitter_intel.domains.asset_market.runtime.live_price_gateway import LivePriceGateway


def test_live_price_gateway_publishes_every_live_frame_without_material_writes():
    db = FakeDB()
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
        pool_bundle=db,
        providers=SimpleNamespace(stream_dex_market=stream_provider, message_cex_market=None),
        interval_seconds=0.1,
        projection_version="token-radar-v12-anchor-live-hard-cut",
        on_live_market_update=published.append,
        clock=lambda: 1_778_000_000_000,
    )

    result = asyncio.run(gateway.run_once(now_ms=1_778_000_000_000))

    assert result.notes["result"]["updates_received"] == 2
    assert result.processed == 2
    assert result.notes["result"]["live_market_updates_published"] == 2
    db.repos.assert_no_market_fact_access()
    assert len(published) == 2
    assert published[0]["market"]["decision_latest"]["price_usd"] == 1.0
    assert published[1]["market"]["decision_latest"]["price_usd"] == 1.0001


class FakeStreamProvider:
    def __init__(self, updates: list[DexMarketFactUpdate]) -> None:
        self.updates = updates

    async def stream_price_info(self, targets):
        for update in self.updates:
            yield update

class FakeDB:
    def __init__(self) -> None:
        self.repos = FakeRepos()

    def worker_session(self, name: str):
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
        self._legacy_market_facts = ForbiddenRepository(_legacy_price_table())
        self.market_ticks = ForbiddenRepository("market_ticks")
        self.enriched_events = ForbiddenRepository("enriched_events")

    def __getattr__(self, name: str):
        if name == _legacy_price_table():
            return self._legacy_market_facts
        raise AttributeError(name)

    def assert_no_market_fact_access(self) -> None:
        assert self._legacy_market_facts.touched is False
        assert self.market_ticks.touched is False
        assert self.enriched_events.touched is False


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


class ForbiddenRepository:
    def __init__(self, name: str) -> None:
        self.name = name
        self.touched = False

    def __getattr__(self, method_name: str):
        self.touched = True
        raise AssertionError(f"LivePriceGateway must not touch {self.name}.{method_name}")


def _legacy_price_table() -> str:
    return "_".join(("price", "observations"))
