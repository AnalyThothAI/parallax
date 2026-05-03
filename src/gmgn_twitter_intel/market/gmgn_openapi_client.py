from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any

import httpx
from curl_cffi import requests as curl_requests
from eth_utils import is_address


@dataclass(frozen=True, slots=True)
class GmgnTokenInfo:
    chain: str
    address: str
    symbol: str
    name: str | None
    icon_url: str | None
    price: float | None
    previous_price: float | None
    market_cap: float | None
    raw: dict[str, Any]


class GmgnOpenApiError(RuntimeError):
    pass


class GmgnOpenApiClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://openapi.gmgn.ai",
        timeout_seconds: float = 5.0,
        cache_ttl_seconds: int = 60,
        force_ipv4: bool = True,
        transport: httpx.BaseTransport | None = None,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.cache_ttl_seconds = max(0, int(cache_ttl_seconds))
        self._cache: dict[tuple[str, str], tuple[float, GmgnTokenInfo | None]] = {}
        self._timeout_seconds = timeout_seconds
        self._headers = {"X-APIKEY": api_key, "Content-Type": "application/json"}
        self._curl_session: curl_requests.Session | None = None
        self._httpx_client: httpx.Client | None = None
        resolved_transport = transport
        if resolved_transport is None and force_ipv4:
            self._curl_session = curl_requests.Session(impersonate="chrome")
        else:
            self._httpx_client = httpx.Client(
                base_url=self.base_url,
                timeout=timeout_seconds,
                transport=resolved_transport,
                headers=self._headers,
            )

    def close(self) -> None:
        if self._httpx_client is not None:
            self._httpx_client.close()
        if self._curl_session is not None:
            self._curl_session.close()

    def get_token_info(self, *, chain: str, address: str) -> GmgnTokenInfo | None:
        api_chain = _api_chain(chain)
        api_address = _api_address(chain=api_chain, address=address)
        key = (api_chain, api_address)
        cached = self._cache.get(key)
        now = time.time()
        if cached and now - cached[0] <= self.cache_ttl_seconds:
            return cached[1]

        data = self._request("GET", "/v1/token/info", {"chain": api_chain, "address": api_address})
        info = _token_info_from_response(chain=chain, address=api_address, data=data)
        self._cache[key] = (now, info)
        return info

    def _request(self, method: str, path: str, params: dict[str, str]) -> Any:
        query = {
            **params,
            "timestamp": str(int(time.time())),
            "client_id": str(uuid.uuid4()),
        }
        response = self._send(method, path, query)
        text = response["text"]
        try:
            payload = response["json"]()
        except ValueError as exc:
            raise GmgnOpenApiError(f"{method} {path} returned non-json HTTP {response['status_code']}") from exc
        if not isinstance(payload, dict):
            raise GmgnOpenApiError(f"{method} {path} returned invalid envelope")
        if payload.get("code") != 0:
            message = payload.get("message") or payload.get("error") or text
            raise GmgnOpenApiError(f"{method} {path} failed: {message}")
        return payload.get("data")

    def _send(self, method: str, path: str, query: dict[str, str]) -> dict[str, Any]:
        if self._httpx_client is not None:
            response = self._httpx_client.request(method, path, params=query)
            return {"status_code": response.status_code, "text": response.text, "json": response.json}
        if self._curl_session is None:
            raise GmgnOpenApiError("GMGN HTTP client is not initialized")
        response = self._curl_session.request(
            method,
            f"{self.base_url}{path}",
            params=query,
            headers=self._headers,
            timeout=self._timeout_seconds,
        )
        return {"status_code": response.status_code, "text": response.text, "json": response.json}


def _token_info_from_response(*, chain: str, address: str, data: Any) -> GmgnTokenInfo | None:
    if not isinstance(data, dict):
        return None
    symbol = _string(data.get("symbol"))
    if not symbol:
        return None
    price = _float_or_none(data.get("price"))
    market_cap = _market_cap(data, price=price)
    return GmgnTokenInfo(
        chain=_internal_chain(chain),
        address=_string(data.get("address")) or address,
        symbol=symbol.strip().lstrip("$").upper() if symbol.isascii() else symbol.strip().lstrip("$"),
        name=_string(data.get("name")),
        icon_url=_string(data.get("logo")) or _string(data.get("icon_url")),
        price=price,
        previous_price=_float_or_none(data.get("previous_price")),
        market_cap=market_cap,
        raw=dict(data),
    )


def _api_chain(chain: str) -> str:
    normalized = chain.strip().lower()
    if normalized == "solana":
        return "sol"
    return normalized


def _api_address(*, chain: str, address: str) -> str:
    if chain in {"eth", "base", "bsc"} and is_address(address):
        return address.lower()
    return address


def _internal_chain(chain: str) -> str:
    normalized = chain.strip().lower()
    if normalized == "sol":
        return "solana"
    return normalized


def _market_cap(data: dict[str, Any], *, price: float | None) -> float | None:
    direct = _float_or_none(data.get("market_cap") or data.get("mcap"))
    if direct is not None:
        return direct
    supply = _float_or_none(data.get("circulating_supply"))
    if price is None or supply is None:
        return None
    return price * supply


def _string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
