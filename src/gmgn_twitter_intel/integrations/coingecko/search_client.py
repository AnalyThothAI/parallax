from __future__ import annotations

import time
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
    """CoinGecko free tier allows ~30 req/min; client paces requests at >= 2s apart."""

    def __init__(
        self,
        *,
        base_url: str = "https://api.coingecko.com",
        timeout_seconds: float = 10.0,
        min_interval_seconds: float = 6.0,
        max_429_retries: int = 3,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout_seconds, transport=transport)
        self._min_interval = min_interval_seconds
        self._max_429_retries = max_429_retries
        self._last_call_at: float = 0.0

    def close(self) -> None:
        self._client.close()

    def _pace(self) -> None:
        if self._min_interval <= 0:
            return
        elapsed = time.monotonic() - self._last_call_at
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_call_at = time.monotonic()

    def _get_with_retry(self, params: dict[str, str]) -> httpx.Response | None:
        """Return response, or None when we give up due to persistent 429s."""
        for _attempt in range(self._max_429_retries + 1):
            self._pace()
            response = self._client.get("/api/v3/search", params=params)
            if response.status_code != 429:
                return response
            retry_after = response.headers.get("retry-after")
            backoff = float(retry_after) if retry_after and retry_after.isdigit() else 60.0
            time.sleep(backoff)
        return None

    def search(self, *, symbol: str, chain: str) -> list[CoingeckoSearchHit]:
        platform = CHAIN_TO_COINGECKO_PLATFORM.get(chain)
        if platform is None:
            return []
        response = self._get_with_retry({"query": symbol})
        if response is None:
            return []  # gave up after retries; treat as no-hit so audit continues
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
