from __future__ import annotations

import re
from typing import Any

from gmgn_twitter_intel.domains.asset_market.providers import (
    DexTokenProfile,
    MarketCapability,
    ProviderHealth,
)
from gmgn_twitter_intel.integrations.binance.web3_token_client import BinanceWeb3TokenClient
from gmgn_twitter_intel.platform.config.settings import Settings

EVM_ADDRESS_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")


class BinanceWeb3DexProfileProvider:
    def __init__(self, client: BinanceWeb3TokenClient) -> None:
        self._client = client

    def token_profile(self, *, chain_id: str, address: str) -> DexTokenProfile | None:
        metadata = self._client.token_metadata(chain_id=chain_id, address=address)
        if metadata is None:
            return None
        return DexTokenProfile(
            chain_id=metadata.chain_id,
            address=_normalize_address(metadata.address),
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


def binance_web3_profile_market(settings: Settings) -> BinanceWeb3DexProfileProvider:
    return BinanceWeb3DexProfileProvider(
        BinanceWeb3TokenClient(
            base_url=settings.binance_web3_base_url,
            timeout_seconds=settings.binance_timeout_seconds,
        )
    )


def binance_provider_health(settings: Settings) -> ProviderHealth:
    capabilities = (
        frozenset({MarketCapability.PROFILE_CEX, MarketCapability.PROFILE_DEX_EXACT})
        if settings.binance_enabled
        else frozenset()
    )
    return ProviderHealth(provider="binance", capabilities=capabilities, configured=settings.binance_enabled)


def _normalize_address(address: Any) -> str:
    text = str(address or "").strip()
    return text.lower() if EVM_ADDRESS_RE.match(text) else text


__all__ = [
    "BinanceWeb3DexProfileProvider",
    "binance_provider_health",
    "binance_web3_profile_market",
]
