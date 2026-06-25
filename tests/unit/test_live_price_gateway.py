from __future__ import annotations

import asyncio
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest

from parallax.domains.asset_market.runtime.live_price_gateway import LivePriceGateway
from parallax.platform.config.settings import LivePriceGatewayWorkerSettings


def _live_settings(**overrides: Any) -> LivePriceGatewayWorkerSettings:
    payload: dict[str, Any] = {
        "interval_seconds": 0.01,
        "target_limit": 100,
        "target_ttl_seconds": 300.0,
    }
    payload.update(overrides)
    return LivePriceGatewayWorkerSettings(**payload)


def _raw_live_settings(**overrides: Any) -> SimpleNamespace:
    payload: dict[str, Any] = {
        "enabled": True,
        "interval_seconds": 0.01,
        "soft_timeout_seconds": 120.0,
        "hard_timeout_seconds": 180.0,
        "target_limit": 100,
        "target_ttl_seconds": 300.0,
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


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
    publisher = RecordingLivePublisher()
    gateway = LivePriceGateway(
        settings=_live_settings(),
        pool_bundle=FakeDB(repos),
        projection_version="token_radar_v7",
        on_live_market_update=publisher.publish,
        clock=lambda: 1_777_800_000_000,
    )

    assert not hasattr(gateway, "providers")
    asyncio.run(gateway.run_once(now_ms=1_777_800_000_000))

    published = publisher.payloads
    assert len(published) == 1
    assert published[0]["target_type"] == "chain_token"
    assert published[0]["target_id"] == "solana:abc"
    assert published[0]["provider"] == "binance_dex_ws"
    assert published[0]["market"]["decision_latest"]["price_usd"] == pytest.approx(1.23)


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
    publisher = RecordingLivePublisher()
    gateway = LivePriceGateway(
        settings=_live_settings(),
        pool_bundle=FakeDB(repos),
        projection_version="token_radar_v7",
        on_live_market_update=publisher.publish,
        clock=lambda: 1_777_800_000_000,
    )

    asyncio.run(gateway.run_once(now_ms=1_777_800_000_000))

    published = publisher.payloads
    assert len(published) == 1
    assert published[0]["target_type"] == "cex_symbol"
    assert published[0]["provider"] == "binance_cex_rest"
    assert published[0]["market"]["decision_latest"]["open_interest_usd"] == pytest.approx(123456789.0)


def test_live_price_gateway_skips_targets_without_recent_tick() -> None:
    repos = FakeRepos(
        active_targets=[_live_target("chain_token", "solana:abc", chain_id="solana", address="abc")],
        latest_ticks={},
    )
    publisher = RecordingLivePublisher()
    gateway = LivePriceGateway(
        settings=_live_settings(),
        pool_bundle=FakeDB(repos),
        projection_version="token_radar_v7",
        on_live_market_update=publisher.publish,
        clock=lambda: 1_777_800_000_000,
    )

    result = asyncio.run(gateway.run_once(now_ms=1_777_800_000_000))

    assert publisher.payloads == []
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
    publisher = RecordingLivePublisher()
    gateway = LivePriceGateway(
        settings=_live_settings(),
        pool_bundle=FakeDB(repos),
        projection_version="token-radar-v12-anchor-live-hard-cut",
        on_live_market_update=publisher.publish,
        clock=lambda: 1_778_000_000_000,
    )

    result = asyncio.run(gateway.run_once(now_ms=1_778_000_000_000))

    assert result.processed == 1
    assert result.notes["result"]["live_market_updates_published"] == 1
    published = publisher.payloads
    assert len(published) == 1
    assert published[0]["market"]["decision_latest"]["price_usd"] == pytest.approx(1.0001)


def test_live_price_gateway_requires_async_publish_contract_without_sync_callback_fallback() -> None:
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
    published: list[dict[str, Any]] = []
    gateway = LivePriceGateway(
        settings=_live_settings(),
        pool_bundle=FakeDB(repos),
        projection_version="token_radar_v7",
        on_live_market_update=published.append,
        clock=lambda: 1_777_800_000_000,
    )

    with pytest.raises(TypeError):
        asyncio.run(gateway.run_once(now_ms=1_777_800_000_000))

    assert len(published) == 1


def test_live_price_gateway_reads_formal_settings_for_target_limit_and_tick_ttl() -> None:
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
    publisher = RecordingLivePublisher()
    gateway = LivePriceGateway(
        settings=_live_settings(target_limit=2, target_ttl_seconds=12.5),
        pool_bundle=FakeDB(repos),
        projection_version="token_radar_v7",
        on_live_market_update=publisher.publish,
        clock=lambda: 1_777_800_000_000,
    )

    asyncio.run(gateway.run_once(now_ms=1_777_800_000_000))

    assert repos.token_capture_tiers.calls == [{"limit": 2}]
    assert repos.market_ticks.calls == [
        {
            "targets": [{"target_type": "chain_token", "target_id": "solana:abc"}],
            "max_age_ms": 12_500,
            "now_ms": 1_777_800_000_000,
        }
    ]


@pytest.mark.parametrize(
    ("overrides", "error_code"),
    [
        pytest.param({"target_limit": -1}, "live_price_gateway_target_limit_required", id="limit-negative"),
        pytest.param({"target_limit": True}, "live_price_gateway_target_limit_required", id="limit-bool"),
        pytest.param({"target_limit": "100"}, "live_price_gateway_target_limit_required", id="limit-string"),
        pytest.param({"target_ttl_seconds": -0.1}, "live_price_gateway_target_ttl_seconds_required", id="ttl-negative"),
        pytest.param({"target_ttl_seconds": True}, "live_price_gateway_target_ttl_seconds_required", id="ttl-bool"),
        pytest.param({"target_ttl_seconds": "300"}, "live_price_gateway_target_ttl_seconds_required", id="ttl-string"),
    ],
)
def test_live_price_gateway_rejects_malformed_runtime_settings(
    overrides: dict[str, Any],
    error_code: str,
) -> None:
    with pytest.raises(ValueError, match=error_code):
        LivePriceGateway(
            settings=_raw_live_settings(**overrides),
            pool_bundle=FakeDB(FakeRepos(active_targets=[], latest_ticks={})),
            projection_version="token_radar_v7",
        )


def test_live_price_gateway_does_not_repair_legacy_target_type_rows() -> None:
    repos = FakeRepos(
        active_targets=[
            _live_target(
                "Asset",
                "legacy-asset-id",
                chain_id="solana",
                address="abc",
            ),
            _live_target(
                "CexToken",
                "legacy-cex-token-id",
                provider="binance",
                native_market_id="BTCUSDT",
                quote_symbol="USDT",
            ),
        ],
        latest_ticks={
            ("chain_token", "solana:abc"): _market_tick_row(
                target_type="chain_token",
                target_id="solana:abc",
                source_provider="binance_dex_ws",
                price_usd="1.23",
            ),
            ("cex_symbol", "binance:BTCUSDT"): _market_tick_row(
                target_type="cex_symbol",
                target_id="binance:BTCUSDT",
                source_provider="binance_cex_rest",
                price_usd="65000.0",
            ),
        },
    )
    publisher = RecordingLivePublisher()
    gateway = LivePriceGateway(
        settings=_live_settings(),
        pool_bundle=FakeDB(repos),
        projection_version="token_radar_v7",
        on_live_market_update=publisher.publish,
        clock=lambda: 1_777_800_000_000,
    )

    result = asyncio.run(gateway.run_once(now_ms=1_777_800_000_000))

    assert publisher.payloads == []
    assert repos.market_ticks.calls == []
    assert result.notes["result"]["targets_selected"] == 2
    assert result.notes["result"]["targets_loaded"] == 2
    assert result.notes["result"]["live_market_updates_published"] == 0


def test_live_price_gateway_requires_formal_settings_contract() -> None:
    repos = FakeRepos(active_targets=[], latest_ticks={})

    with pytest.raises(RuntimeError, match="live_price_gateway_settings_required"):
        LivePriceGateway(
            settings=None,
            pool_bundle=FakeDB(repos),
            projection_version="token_radar_v7",
        )


def test_live_price_gateway_requires_db_pool_bundle_contract() -> None:
    with pytest.raises(RuntimeError, match="live_price_gateway_db_required"):
        LivePriceGateway(
            settings=_live_settings(),
            pool_bundle=None,
            projection_version="token_radar_v7",
        )


class RecordingLivePublisher:
    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []

    async def publish(self, payload: dict[str, Any]) -> None:
        self.payloads.append(payload)


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
