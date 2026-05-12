from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any

import httpx
from curl_cffi import CurlOpt
from curl_cffi import requests as curl_requests
from eth_utils import is_address

CURL_IPRESOLVE_V4 = 1


@dataclass(frozen=True, slots=True)
class GmgnTokenInfo:
    chain: str
    address: str
    symbol: str
    name: str | None
    icon_url: str | None
    banner_url: str | None
    decimals: int | None
    price: float | None
    previous_price: float | None
    market_cap: float | None
    liquidity: float | None
    holder_count: int | None
    circulating_supply: float | None
    total_supply: float | None
    max_supply: float | None
    website: str | None
    twitter_username: str | None
    telegram: str | None
    gmgn_url: str | None
    geckoterminal_url: str | None
    description: str | None
    pool: dict[str, Any] | None
    dev: dict[str, Any] | None
    stat: dict[str, Any] | None
    link: dict[str, Any] | None
    raw: dict[str, Any]


@dataclass(frozen=True, slots=True)
class GmgnTokenKlineCandle:
    time_ms: int
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: float | None
    volume_usd: float | None
    raw: dict[str, Any]


@dataclass(frozen=True, slots=True)
class GmgnTokenInfoLookup:
    info: GmgnTokenInfo | None
    cache_status: str


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
        min_request_interval_seconds: float = 0.12,
        transport: httpx.BaseTransport | None = None,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.cache_ttl_seconds = max(0, int(cache_ttl_seconds))
        self._cache: dict[tuple[str, str], tuple[float, GmgnTokenInfo | None]] = {}
        self._timeout_seconds = timeout_seconds
        self._min_request_interval_seconds = max(0.0, float(min_request_interval_seconds))
        self._last_request_monotonic = 0.0
        self._headers = {"X-APIKEY": api_key, "Content-Type": "application/json"}
        self._curl_session: curl_requests.Session | None = None
        self._httpx_client: httpx.Client | None = None
        resolved_transport = transport
        if resolved_transport is None and force_ipv4:
            self._curl_session = curl_requests.Session(
                impersonate="chrome",
                curl_options={CurlOpt.IPRESOLVE: CURL_IPRESOLVE_V4},
            )
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

    def lookup_token_info(self, *, chain: str, address: str) -> GmgnTokenInfoLookup:
        api_chain = _api_chain(chain)
        api_address = _api_address(chain=api_chain, address=address)
        key = (api_chain, api_address)
        cached = self._cache.get(key)
        now = time.time()
        if cached and now - cached[0] <= self.cache_ttl_seconds:
            return GmgnTokenInfoLookup(info=cached[1], cache_status="hit")

        data = self._request("GET", "/v1/token/info", {"chain": api_chain, "address": api_address})
        info = _token_info_from_response(chain=chain, address=api_address, data=data)
        self._cache[key] = (now, info)
        return GmgnTokenInfoLookup(info=info, cache_status="miss")

    def token_kline(
        self,
        *,
        chain: str,
        address: str,
        resolution: str,
        limit: int,
        now_ms: int | None = None,
    ) -> list[GmgnTokenKlineCandle]:
        api_chain = _api_chain(chain)
        api_address = _api_address(chain=api_chain, address=address)
        to_seconds = int((now_ms if now_ms is not None else time.time() * 1000) // 1000)
        from_seconds = to_seconds - _resolution_seconds(resolution) * max(1, int(limit))
        data = self._request(
            "GET",
            "/v1/market/token_kline",
            {
                "chain": api_chain,
                "address": api_address,
                "resolution": _api_resolution(resolution),
                "from": str(from_seconds),
                "to": str(to_seconds),
            },
        )
        rows = data.get("list") if isinstance(data, dict) else data
        if not isinstance(rows, list):
            return []
        candles: list[GmgnTokenKlineCandle] = []
        for row in rows:
            candle = _kline_candle_from_response(row)
            if candle is not None:
                candles.append(candle)
        return candles

    def _request(self, method: str, path: str, params: dict[str, str]) -> Any:
        query = {
            **params,
            "timestamp": str(int(time.time())),
            "client_id": str(uuid.uuid4()),
        }
        self._throttle()
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

    def _throttle(self) -> None:
        if self._min_request_interval_seconds <= 0:
            return
        now = time.monotonic()
        next_allowed = self._last_request_monotonic + self._min_request_interval_seconds
        wait_seconds = next_allowed - now
        if wait_seconds > 0:
            time.sleep(wait_seconds)
            now = time.monotonic()
        self._last_request_monotonic = now

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
    link = data.get("link") if isinstance(data.get("link"), dict) else None
    return GmgnTokenInfo(
        chain=_internal_chain(chain),
        address=_string(data.get("address")) or address,
        symbol=symbol.strip().lstrip("$").upper() if symbol.isascii() else symbol.strip().lstrip("$"),
        name=_string(data.get("name")),
        icon_url=_string(data.get("logo")) or _string(data.get("icon_url")),
        banner_url=_string(data.get("banner")),
        decimals=_int_or_none(data.get("decimals")),
        price=price,
        previous_price=_float_or_none(data.get("previous_price")),
        market_cap=market_cap,
        liquidity=_float_or_none(data.get("liquidity")),
        holder_count=_int_or_none(data.get("holder_count") or data.get("holders")),
        circulating_supply=_float_or_none(data.get("circulating_supply")),
        total_supply=_float_or_none(data.get("total_supply")),
        max_supply=_float_or_none(data.get("max_supply")),
        website=_link_string(link, "website"),
        twitter_username=_link_string(link, "twitter_username") or _link_string(link, "twitter"),
        telegram=_link_string(link, "telegram"),
        gmgn_url=_link_string(link, "gmgn"),
        geckoterminal_url=_link_string(link, "geckoterminal"),
        description=_link_string(link, "description") or _string(data.get("description")),
        pool=dict(data["pool"]) if isinstance(data.get("pool"), dict) else None,
        dev=dict(data["dev"]) if isinstance(data.get("dev"), dict) else None,
        stat=dict(data["stat"]) if isinstance(data.get("stat"), dict) else None,
        link=dict(link) if link is not None else None,
        raw=dict(data),
    )


def _api_chain(chain: str) -> str:
    normalized = chain.strip().lower()
    if normalized == "eip155:1":
        return "eth"
    if normalized == "eip155:56":
        return "bsc"
    if normalized == "eip155:8453":
        return "base"
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


def _int_or_none(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _link_string(link: dict[str, Any] | None, key: str) -> str | None:
    if link is None:
        return None
    return _string(link.get(key))


def _api_resolution(value: str) -> str:
    text = str(value or "").strip()
    return text.lower() or "1m"


def _resolution_seconds(value: str) -> int:
    text = _api_resolution(value)
    unit = text[-1:]
    try:
        amount = int(text[:-1])
    except ValueError:
        return 60
    if unit == "m":
        return amount * 60
    if unit == "h":
        return amount * 60 * 60
    if unit == "d":
        return amount * 24 * 60 * 60
    return 60


def _kline_candle_from_response(row: Any) -> GmgnTokenKlineCandle | None:
    if not isinstance(row, dict):
        return None
    time_ms = _int_or_none(row.get("time") or row.get("time_ms"))
    if time_ms is None:
        return None
    return GmgnTokenKlineCandle(
        time_ms=time_ms,
        open=_float_or_none(row.get("open")),
        high=_float_or_none(row.get("high")),
        low=_float_or_none(row.get("low")),
        close=_float_or_none(row.get("close")),
        volume=_float_or_none(row.get("amount")),
        volume_usd=_float_or_none(row.get("volume")),
        raw=dict(row),
    )
