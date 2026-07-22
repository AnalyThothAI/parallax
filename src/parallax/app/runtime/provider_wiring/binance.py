from __future__ import annotations

from parallax.domains.asset_market.chain_identity import canonical_chain_address
from parallax.domains.asset_market.providers import (
    CexTicker,
    DexTokenProfile,
    MarketCapability,
    ProviderHealth,
)
from parallax.integrations.binance.usdm_futures_client import (
    BinanceUsdmFuturesClient,
    BinanceUsdmTicker24hr,
)
from parallax.integrations.binance.web3_token_client import BinanceWeb3TokenClient
from parallax.platform.config.settings import Settings


class BinanceWeb3DexProfileProvider:
    def __init__(self, client: BinanceWeb3TokenClient) -> None:
        self._client = client

    def token_profile(self, *, chain_id: str, address: str) -> DexTokenProfile | None:
        metadata = self._client.token_metadata(chain_id=chain_id, address=address)
        if metadata is None:
            return None
        return DexTokenProfile(
            chain_id=metadata.chain_id,
            address=canonical_chain_address(metadata.chain_id, metadata.address),
            symbol=metadata.symbol,
            name=metadata.name,
            logo_url=metadata.logo_url,
            banner_url=None,
            website=metadata.website,
            twitter_username=metadata.twitter_username,
            telegram=metadata.telegram,
            gmgn_url=None,
            geckoterminal_url=None,
            description=metadata.description,
            raw=metadata.raw,
        )

    def close(self) -> None:
        self._client.close()


class BinanceUsdmFuturesMarketProvider:
    def __init__(self, client: BinanceUsdmFuturesClient) -> None:
        self._client = client

    def tickers(self, *, inst_type: str) -> list[CexTicker]:
        if str(inst_type or "").strip().upper() not in {"SWAP", "PERP", "PERPETUAL"}:
            return []
        tickers = self._client.ticker_24hr()
        rows = tickers if isinstance(tickers, list) else [tickers]
        return [_cex_ticker(row) for row in rows]

    def ticker(self, *, inst_id: str) -> CexTicker | None:
        ticker = self._client.ticker_24hr(symbol=inst_id)
        if isinstance(ticker, list):
            return _cex_ticker(ticker[0]) if ticker else None
        return _cex_ticker(ticker)

    def close(self) -> None:
        self._client.close()


def binance_web3_profile_market(settings: Settings) -> BinanceWeb3DexProfileProvider:
    return BinanceWeb3DexProfileProvider(
        BinanceWeb3TokenClient(
            base_url=settings.providers.binance.web3_base_url,
            timeout_seconds=settings.providers.binance.timeout_seconds,
        )
    )


def binance_usdm_futures_market(settings: Settings) -> BinanceUsdmFuturesMarketProvider:
    return BinanceUsdmFuturesMarketProvider(
        BinanceUsdmFuturesClient(
            base_url=settings.providers.binance.usdm_futures_base_url,
            timeout_seconds=settings.providers.binance.timeout_seconds,
        )
    )


def binance_provider_health(settings: Settings) -> ProviderHealth:
    capabilities = (
        frozenset({MarketCapability.PROFILE_CEX, MarketCapability.PROFILE_DEX_EXACT, MarketCapability.QUOTE_CEX})
        if settings.providers.binance.enabled
        else frozenset()
    )
    return ProviderHealth(
        provider="binance",
        capabilities=capabilities,
        configured=settings.providers.binance.enabled,
    )


def _cex_ticker(ticker: BinanceUsdmTicker24hr) -> CexTicker:
    return CexTicker(
        inst_id=ticker.symbol,
        inst_type="SWAP",
        last_price=ticker.last_price,
        volume_24h=ticker.quote_volume_24h,
        open_interest=None,
        raw=ticker.raw,
    )


__all__ = [
    "BinanceUsdmFuturesMarketProvider",
    "BinanceWeb3DexProfileProvider",
    "binance_provider_health",
    "binance_usdm_futures_market",
    "binance_web3_profile_market",
]
