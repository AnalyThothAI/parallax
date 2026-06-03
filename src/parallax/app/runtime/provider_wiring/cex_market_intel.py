from __future__ import annotations

from parallax.app.runtime.provider_wiring import binance
from parallax.app.runtime.provider_wiring.types import CexMarketIntelProviders
from parallax.domains.cex_market_intel.providers import CoinglassDerivativesProvider
from parallax.platform.config.settings import Settings


def wire_cex_market_intel(settings: Settings) -> CexMarketIntelProviders:
    return CexMarketIntelProviders(
        oi_market=binance.binance_usdm_futures_oi_market(settings) if settings.binance_enabled else None,
        coinglass_derivatives=_coinglass_derivatives(settings),
    )


def _coinglass_derivatives(settings: Settings) -> CoinglassDerivativesProvider | None:
    worker_settings = settings.workers.cex_oi_radar_board
    if int(getattr(worker_settings, "coinglass_enrichment_limit", 0)) <= 0:
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
