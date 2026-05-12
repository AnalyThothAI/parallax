from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

CHAIN_TO_COINGECKO_PLATFORM: dict[str, str] = {
    "ethereum": "ethereum",
    "solana": "solana",
    "bsc": "binance-smart-chain",
    "base": "base",
    "tron": "tron",
}


@dataclass(frozen=True, slots=True)
class CoingeckoSearchHit:
    coin_id: str
    symbol: str
    chain: str
    address: str


class CoingeckoSearchClient:
    def __init__(
        self,
        *,
        base_url: str = "https://api.coingecko.com",
        timeout_seconds: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout_seconds, transport=transport)

    def close(self) -> None:
        self._client.close()

    def search(self, *, symbol: str, chain: str) -> list[CoingeckoSearchHit]:
        platform = CHAIN_TO_COINGECKO_PLATFORM.get(chain)
        if platform is None:
            return []
        response = self._client.get("/api/v3/search", params={"query": symbol})
        response.raise_for_status()
        payload: dict[str, Any] = response.json() or {}
        hits: list[CoingeckoSearchHit] = []
        for coin in payload.get("coins") or []:
            address = ((coin.get("platforms") or {}).get(platform) or "").strip()
            if not address:
                continue
            hits.append(
                CoingeckoSearchHit(
                    coin_id=str(coin.get("id") or ""),
                    symbol=str(coin.get("symbol") or "").lower(),
                    chain=chain,
                    address=address.lower() if address.startswith("0x") else address,
                )
            )
        return hits
