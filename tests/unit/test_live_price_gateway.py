from __future__ import annotations

import asyncio
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest

from parallax.domains.asset_market.runtime.live_price_gateway import LivePriceGateway


def test_live_price_gateway_uses_market_ticks_without_upstream_price_providers() -> None:
    repos = FakeRepos(
        active_targets=[_live_target("chain_token", "solana:abc", chain_id="solana", address="abc")],
        latest_ticks={
            ("chain_token", "solana:abc"): _market_tick_row(
                target_type="chain_token",
                target_id="solana:abc",
                source_provider="binance_dex_ws",
                price_usd="1.23",
            ),
        },
    )
    providers = SimpleNamespace(
        stream_dex_market=ExplodingStreamProvider(),
        cex_market=ExplodingCexProvider(),
    )
    published: list[dict[str, Any]] = []
    gateway = LivePriceGateway(
        pool_bundle=FakeDB(repos),
        providers=providers,
        interval_seconds=0.01,
        projection_version="token_radar_v7",
        on_live_market_update=published.append,
        clock=lambda: 1_777_800_000_000,
    )

    asyncio.run(gateway.run_once(now_ms=1_777_800_000_000))

    assert len(published) == 1
    assert published[0]["target_type"] == "chain_token"
    assert published[0]["target_id"] == "solana:abc"
    assert published[0]["provider"] == "binance_dex_ws"
    assert published[0]["market"]["decision_latest"]["price_usd"] == pytest.approx(1.23)
    # The gateway must never have touched the upstream providers
    assert providers.stream_dex_market.calls == []
    assert providers.cex_market.calls == []


def test_live_price_gateway_publishes_cex_tick_with_quote_basis() -> None:
    repos = FakeRepos(
        active_targets=[
            _live_target(
                "cex_symbol",
                "binance:BTCUSDT",
                provider="binance",
                native_market_id="BTCUSDT",
                quote_symbol="USDT",
            )
        ],
        latest_ticks={
            ("cex_symbol", "binance:BTCUSDT"): _market_tick_row(
                target_type="cex_symbol",
                target_id="binance:BTCUSDT",
                source_provider="binance_cex_rest",
                price_usd="65000.0",
                open_interest_usd="123456789.0",
            ),
        },
    )
    published: list[dict[str, Any]] = []
    gateway = LivePriceGateway(
        pool_bundle=FakeDB(repos),
        providers=SimpleNamespace(
            stream_dex_market=ExplodingStreamProvider(),
            cex_market=ExplodingCexProvider(),
        ),
        interval_seconds=0.01,
        projection_version="token_radar_v7",
        on_live_market_update=published.append,
        clock=lambda: 1_777_800_000_000,
    )

    asyncio.run(gateway.run_once(now_ms=1_777_800_000_000))

    assert len(published) == 1
    assert published[0]["target_type"] == "cex_symbol"
    assert published[0]["provider"] == "binance_cex_rest"
    assert published[0]["market"]["decision_latest"]["open_interest_usd"] == pytest.approx(123456789.0)


def test_live_price_gateway_skips_targets_without_recent_tick() -> None:
    repos = FakeRepos(
        active_targets=[_live_target("chain_token", "solana:abc", chain_id="solana", address="abc")],
        latest_ticks={},
    )
    published: list[dict[str, Any]] = []
    gateway = LivePriceGateway(
        pool_bundle=FakeDB(repos),
        providers=SimpleNamespace(
            stream_dex_market=ExplodingStreamProvider(),
            cex_market=ExplodingCexProvider(),
        ),
        interval_seconds=0.01,
        projection_version="token_radar_v7",
        on_live_market_update=published.append,
        clock=lambda: 1_777_800_000_000,
    )

    result = asyncio.run(gateway.run_once(now_ms=1_777_800_000_000))

    assert published == []
    assert result.processed == 0
    assert result.notes["result"]["targets_selected"] == 1
    assert result.notes["result"]["live_market_updates_published"] == 0


def test_live_price_gateway_publishes_every_live_frame_without_material_writes() -> None:
    # legacy test, updated for DB-backed fan-out: a single active target with a fresh tick
    # produces a single publish (no streaming sequencing).
    repos = FakeRepos(
        active_targets=[_live_target("chain_token", "solana:abc", chain_id="solana", address="abc")],
        latest_ticks={
            ("chain_token", "solana:abc"): _market_tick_row(
                target_type="chain_token",
                target_id="solana:abc",
                source_provider="binance_dex_ws",
                price_usd="1.0001",
            ),
        },
    )
    published: list[dict[str, Any]] = []
    gateway = LivePriceGateway(
        pool_bundle=FakeDB(repos),
        providers=SimpleNamespace(
            stream_dex_market=ExplodingStreamProvider(),
            cex_market=ExplodingCexProvider(),
        ),
        interval_seconds=0.1,
        projection_version="token-radar-v12-anchor-live-hard-cut",
        on_live_market_update=published.append,
        clock=lambda: 1_778_000_000_000,
    )

    result = asyncio.run(gateway.run_once(now_ms=1_778_000_000_000))

    assert result.processed == 1
    assert result.notes["result"]["live_market_updates_published"] == 1
    assert len(published) == 1
    assert published[0]["market"]["decision_latest"]["price_usd"] == pytest.approx(1.0001)


def _live_target(
    target_type: str,
    target_id: str,
    *,
    chain_id: str | None = None,
    address: str | None = None,
    provider: str | None = None,
    native_market_id: str | None = None,
    quote_symbol: str | None = None,
    pricefeed_id: str | None = None,
) -> dict[str, Any]:
    return {
        "target_type": target_type,
        "target_id": target_id,
        "chain_id": chain_id,
        "address": address,
        "provider": provider,
        "native_market_id": native_market_id,
        "quote_symbol": quote_symbol,
        "pricefeed_id": pricefeed_id,
    }


def _market_tick_row(
    *,
    target_type: str,
    target_id: str,
    source_provider: str,
    price_usd: str,
    open_interest_usd: str | None = None,
    observed_at_ms: int = 1_777_800_000_000,
    received_at_ms: int = 1_777_800_000_000,
) -> dict[str, Any]:
    return {
        "target_type": target_type,
        "target_id": target_id,
        "source_provider": source_provider,
        "source_tier": "tier1_ws",
        "observed_at_ms": observed_at_ms,
        "received_at_ms": received_at_ms,
        "price_usd": Decimal(price_usd),
        "market_cap_usd": None,
        "liquidity_usd": None,
        "volume_24h_usd": None,
        "open_interest_usd": Decimal(open_interest_usd) if open_interest_usd is not None else None,
        "holders": None,
        "pricefeed_id": None,
    }


class FakeDB:
    def __init__(self, repos: FakeRepos) -> None:
        self.repos = repos
        self.session_names: list[str] = []

    def worker_session(self, name: str) -> FakeSession:
        self.session_names.append(name)
        return FakeSession(self.repos)


class FakeSession:
    def __init__(self, repos: FakeRepos) -> None:
        self.repos = repos

    def __enter__(self) -> FakeRepos:
        return self.repos

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class FakeRepos:
    def __init__(
        self,
        *,
        active_targets: list[dict[str, Any]],
        latest_ticks: dict[tuple[str, str], dict[str, Any]],
    ) -> None:
        self.token_capture_tiers = FakeTokenCaptureTiers(active_targets)
        self.market_ticks = FakeMarketTickRepo(latest_ticks)


class FakeTokenCaptureTiers:
    def __init__(self, targets: list[dict[str, Any]]) -> None:
        self._targets = targets
        self.calls: list[dict[str, Any]] = []

    def live_target_rows(self, *, limit: int) -> list[dict[str, Any]]:
        self.calls.append({"limit": limit})
        return list(self._targets)


class FakeMarketTickRepo:
    def __init__(self, latest: dict[tuple[str, str], dict[str, Any]]) -> None:
        self._latest = latest
        self.calls: list[dict[str, Any]] = []

    def latest_for_targets(
        self,
        *,
        targets: list[dict[str, str]],
        max_age_ms: int,
        now_ms: int,
    ) -> dict[tuple[str, str], dict[str, Any]]:
        self.calls.append({"targets": list(targets), "max_age_ms": max_age_ms, "now_ms": now_ms})
        result: dict[tuple[str, str], dict[str, Any]] = {}
        for target in targets:
            key = (str(target["target_type"]), str(target["target_id"]))
            if key in self._latest:
                result[key] = self._latest[key]
        return result


class ExplodingStreamProvider:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def replace_subscriptions(self, targets) -> None:
        self.calls.append("replace_subscriptions")
        raise AssertionError("LivePriceGateway must not call upstream stream provider")

    async def iter_price_info(self):
        self.calls.append("iter_price_info")
        raise AssertionError("LivePriceGateway must not call upstream stream provider")
        if False:
            yield None

    async def aclose(self) -> None:
        self.calls.append("aclose")


class ExplodingCexProvider:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def ticker(self, *, inst_id: str):
        self.calls.append(inst_id)
        raise AssertionError("LivePriceGateway must not call upstream CEX provider")
