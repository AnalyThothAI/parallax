from __future__ import annotations

from parallax.app.runtime.provider_wiring import binance
from parallax.app.runtime.provider_wiring.types import CexMarketIntelProviders
from parallax.domains.cex_market_intel.providers import CoinglassDerivativesProvider
from parallax.platform.config.settings import Settings


def wire_cex_market_intel(settings: Settings) -> CexMarketIntelProviders:
    oi_market = binance.binance_usdm_futures_oi_market(settings) if settings.binance_enabled else None
    return CexMarketIntelProviders(
        oi_market=oi_market,
        coinglass_derivatives=_coinglass_derivatives(settings, oi_market=oi_market),
    )


def _coinglass_derivatives(
    settings: Settings,
    *,
    oi_market: object | None,
) -> CoinglassDerivativesProvider | None:
    worker_settings = settings.workers.cex_oi_radar_board
    if not worker_settings.enabled:
        return None
    if oi_market is None:
        return None
    if worker_settings.coinglass_enrichment_limit <= 0:
        return None
    try:
        from coinglass_cli.client import CoinglassClient
    except Exception:
        return None
    try:
        return CoinglassClient()
    except Exception:
        return None


__all__ = ["wire_cex_market_intel"]
