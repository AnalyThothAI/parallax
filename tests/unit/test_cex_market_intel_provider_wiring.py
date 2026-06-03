from __future__ import annotations

from types import SimpleNamespace

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


def test_wire_providers_populates_cex_market_intel_oi_market_when_binance_enabled(monkeypatch) -> None:
    oi_provider = object()

    monkeypatch.setattr(
        cex_market_intel_wiring.binance,
        "binance_usdm_futures_oi_market",
        lambda settings: oi_provider,
    )

    providers = providers_wiring.wire_providers(
        Settings(ws_token="secret", providers={"binance": {"enabled": True}}),
        start_collector=False,
    )

    assert providers.cex_market_intel.oi_market is oi_provider


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
