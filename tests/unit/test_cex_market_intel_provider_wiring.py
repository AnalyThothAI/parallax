from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

import pytest

from parallax.app.runtime import providers_wiring
from parallax.app.runtime.provider_wiring import binance as binance_wiring
from parallax.app.runtime.provider_wiring import cex_market_intel as cex_market_intel_wiring
from parallax.app.runtime.worker_factories.cex_market_intel import construct_cex_market_intel_workers
from parallax.domains.cex_market_intel.providers import (
    CexFundingPremium,
    CexOiTicker24h,
    CexOpenInterestPoint,
)
from parallax.domains.cex_market_intel.runtime.cex_oi_radar_board_worker import (
    CexOiRadarBoardWorker,
)
from parallax.platform.config.settings import Settings


def test_binance_oi_adapter_maps_raw_client_rows_to_cex_market_intel_dtos() -> None:
    raw_client = _RawBinanceClient()
    provider = binance_wiring.BinanceUsdmFuturesOiProvider(raw_client)

    tickers = provider.list_24h_tickers(symbol="BTCUSDT")
    premiums = provider.list_funding_premium(symbol="BTCUSDT")
    history = provider.list_open_interest_history(symbol="BTCUSDT", period="5m", limit=2)
    provider.close()

    assert tickers == [
        CexOiTicker24h(
            symbol="BTCUSDT",
            quote_volume_24h=10_000_000.0,
            price_change_pct_24h=1.25,
            last_price=71_000.0,
        )
    ]
    assert premiums == [
        CexFundingPremium(symbol="BTCUSDT", mark_price=71_050.0, last_funding_rate=0.0001),
    ]
    assert history == [
        CexOpenInterestPoint(symbol="BTCUSDT", open_interest_value=1_000.0, observed_at_ms=1),
        CexOpenInterestPoint(symbol="BTCUSDT", open_interest_value=1_100.0, observed_at_ms=2),
    ]
    assert raw_client.calls == [
        ("ticker_24hr", "BTCUSDT"),
        ("premium_index", "BTCUSDT"),
        ("open_interest_hist", "BTCUSDT", "5m", 2),
        ("close",),
    ]


def test_binance_oi_adapter_rejects_malformed_ticker_rows_before_dto_mapping() -> None:
    provider = binance_wiring.BinanceUsdmFuturesOiProvider(_MalformedTickerClient())

    with pytest.raises(ValueError, match="binance_oi_provider_contract_required:quote_volume_24h"):
        provider.list_24h_tickers(symbol="BTCUSDT")


def test_binance_oi_adapter_rejects_malformed_funding_rows_before_dto_mapping() -> None:
    provider = binance_wiring.BinanceUsdmFuturesOiProvider(_MalformedFundingClient())

    with pytest.raises(ValueError, match="binance_oi_provider_contract_required:last_funding_rate"):
        provider.list_funding_premium(symbol="BTCUSDT")


def test_binance_oi_adapter_rejects_malformed_open_interest_rows_before_dto_mapping() -> None:
    provider = binance_wiring.BinanceUsdmFuturesOiProvider(_MalformedOpenInterestClient())

    with pytest.raises(ValueError, match="binance_oi_provider_contract_required:time_ms"):
        provider.list_open_interest_history(symbol="BTCUSDT", period="5m", limit=2)


def test_wire_providers_populates_cex_market_intel_oi_market_when_binance_enabled(monkeypatch) -> None:
    oi_provider = object()

    monkeypatch.setattr(
        cex_market_intel_wiring.binance,
        "binance_usdm_futures_oi_market",
        lambda settings: oi_provider,
    )

    providers = providers_wiring.wire_providers(
        Settings(
            ws_token="secret",
            providers={"binance": {"enabled": True}},
            workers={"cex_oi_radar_board": {"coinglass_enrichment_limit": 0}},
        ),
        start_collector=False,
    )

    assert providers.cex_market_intel.oi_market is oi_provider


def test_wire_cex_market_intel_does_not_construct_coinglass_when_worker_disabled(monkeypatch) -> None:
    constructed: list[str] = []
    _install_fake_coinglass(monkeypatch, constructed)
    monkeypatch.setattr(
        cex_market_intel_wiring.binance,
        "binance_usdm_futures_oi_market",
        lambda settings: object(),
    )

    providers = cex_market_intel_wiring.wire_cex_market_intel(
        Settings(
            ws_token="secret",
            providers={"binance": {"enabled": True}},
            workers={"cex_oi_radar_board": {"enabled": False, "coinglass_enrichment_limit": 5}},
        )
    )

    assert providers.coinglass_derivatives is None
    assert constructed == []


def test_wire_cex_market_intel_does_not_construct_coinglass_without_oi_provider(monkeypatch) -> None:
    constructed: list[str] = []
    _install_fake_coinglass(monkeypatch, constructed)

    providers = cex_market_intel_wiring.wire_cex_market_intel(
        Settings(
            ws_token="secret",
            providers={"binance": {"enabled": False}},
            workers={"cex_oi_radar_board": {"enabled": True, "coinglass_enrichment_limit": 5}},
        )
    )

    assert providers.oi_market is None
    assert providers.coinglass_derivatives is None
    assert constructed == []


def test_wire_cex_market_intel_requires_worker_enabled_setting(monkeypatch) -> None:
    constructed: list[str] = []
    _install_fake_coinglass(monkeypatch, constructed)
    monkeypatch.setattr(
        cex_market_intel_wiring.binance,
        "binance_usdm_futures_oi_market",
        lambda settings: object(),
    )
    malformed_settings = SimpleNamespace(
        binance_enabled=True,
        workers=SimpleNamespace(
            cex_oi_radar_board=SimpleNamespace(coinglass_enrichment_limit=5),
        ),
    )

    with pytest.raises(AttributeError, match="enabled"):
        cex_market_intel_wiring.wire_cex_market_intel(malformed_settings)

    assert constructed == []


def test_wire_cex_market_intel_requires_worker_coinglass_limit_setting(monkeypatch) -> None:
    constructed: list[str] = []
    _install_fake_coinglass(monkeypatch, constructed)
    monkeypatch.setattr(
        cex_market_intel_wiring.binance,
        "binance_usdm_futures_oi_market",
        lambda settings: object(),
    )
    malformed_settings = SimpleNamespace(
        binance_enabled=True,
        workers=SimpleNamespace(
            cex_oi_radar_board=SimpleNamespace(enabled=True),
        ),
    )

    with pytest.raises(AttributeError, match="coinglass_enrichment_limit"):
        cex_market_intel_wiring.wire_cex_market_intel(malformed_settings)

    assert constructed == []


def test_worker_factory_uses_cex_market_intel_oi_provider_not_generic_asset_market() -> None:
    generic_cex_market = object()
    oi_provider = object()
    coinglass_provider = object()

    workers = construct_cex_market_intel_workers(
        _factory_context(
            asset_cex_market=generic_cex_market,
            cex_oi_market=oi_provider,
            coinglass_derivatives=coinglass_provider,
        )
    )

    worker = workers["cex_oi_radar_board"]
    assert isinstance(worker, CexOiRadarBoardWorker)
    assert worker.oi_market is oi_provider
    assert worker.coinglass_derivatives is coinglass_provider
    assert not hasattr(worker, "cex_market")


def test_worker_factory_reports_missing_oi_provider_even_when_generic_asset_market_exists() -> None:
    workers = construct_cex_market_intel_workers(
        _factory_context(
            asset_cex_market=object(),
            cex_oi_market=None,
            coinglass_derivatives=None,
        )
    )

    status = workers["cex_oi_radar_board"].status_payload()
    assert status["effective_status"] == "unavailable"
    assert status["unavailable_reason"] == "missing_cex_oi_market_provider"


def test_worker_factory_requires_cex_market_intel_provider_bundle_root() -> None:
    ctx = _factory_context(
        asset_cex_market=object(),
        cex_oi_market=object(),
        coinglass_derivatives=None,
    )
    ctx.providers = SimpleNamespace(asset_market=ctx.providers.asset_market)

    with pytest.raises(AttributeError, match="cex_market_intel"):
        construct_cex_market_intel_workers(ctx)


def test_worker_factory_requires_cex_market_intel_provider_bundle_fields() -> None:
    ctx = _factory_context(
        asset_cex_market=object(),
        cex_oi_market=object(),
        coinglass_derivatives=None,
    )
    ctx.providers.cex_market_intel = SimpleNamespace(coinglass_derivatives=None)

    with pytest.raises(AttributeError, match="oi_market"):
        construct_cex_market_intel_workers(ctx)


def _factory_context(
    *,
    asset_cex_market: object | None,
    cex_oi_market: object | None,
    coinglass_derivatives: object | None,
) -> SimpleNamespace:
    return SimpleNamespace(
        settings=Settings(
            ws_token="secret",
            workers={"cex_oi_radar_board": {"enabled": True}},
        ),
        db=object(),
        telemetry=object(),
        providers=SimpleNamespace(
            asset_market=SimpleNamespace(cex_market=asset_cex_market),
            cex_market_intel=SimpleNamespace(
                oi_market=cex_oi_market,
                coinglass_derivatives=coinglass_derivatives,
            ),
        ),
    )


class _RawBinanceClient:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    def ticker_24hr(self, symbol: str | None = None):
        self.calls.append(("ticker_24hr", symbol))
        return SimpleNamespace(
            symbol="BTCUSDT",
            quote_volume_24h=10_000_000.0,
            price_change_percent=1.25,
            last_price=71_000.0,
        )

    def premium_index(self, symbol: str | None = None):
        self.calls.append(("premium_index", symbol))
        return SimpleNamespace(symbol="BTCUSDT", mark_price=71_050.0, last_funding_rate=0.0001)

    def open_interest_hist(self, symbol: str, period: str, limit: int):
        self.calls.append(("open_interest_hist", symbol, period, limit))
        return [
            SimpleNamespace(symbol=symbol, open_interest_value=1_000.0, time_ms=1),
            SimpleNamespace(symbol=symbol, open_interest_value=1_100.0, time_ms=2),
        ]

    def close(self) -> None:
        self.calls.append(("close",))


class _MalformedTickerClient(_RawBinanceClient):
    def ticker_24hr(self, symbol: str | None = None):
        self.calls.append(("ticker_24hr", symbol))
        return SimpleNamespace(
            symbol="BTCUSDT",
            price_change_percent=1.25,
            last_price=71_000.0,
        )


class _MalformedFundingClient(_RawBinanceClient):
    def premium_index(self, symbol: str | None = None):
        self.calls.append(("premium_index", symbol))
        return SimpleNamespace(symbol="BTCUSDT", mark_price=71_050.0)


class _MalformedOpenInterestClient(_RawBinanceClient):
    def open_interest_hist(self, symbol: str, period: str, limit: int):
        self.calls.append(("open_interest_hist", symbol, period, limit))
        return [SimpleNamespace(symbol=symbol, open_interest_value=1_000.0)]


def _install_fake_coinglass(monkeypatch, constructed: list[str]) -> None:
    package = ModuleType("coinglass_cli")
    client_module = ModuleType("coinglass_cli.client")

    class FakeCoinglassClient:
        def __init__(self) -> None:
            constructed.append("coinglass")

    client_module.CoinglassClient = FakeCoinglassClient
    monkeypatch.setitem(sys.modules, "coinglass_cli", package)
    monkeypatch.setitem(sys.modules, "coinglass_cli.client", client_module)
