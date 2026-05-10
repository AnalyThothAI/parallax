from __future__ import annotations

from typing import Any

import httpx

from gmgn_twitter_intel.integrations.okx.models import OkxCexInstrument, OkxCexTicker


class OkxClientError(RuntimeError):
    pass


class OkxCexClient:
    def __init__(
        self,
        *,
        base_url: str = "https://www.okx.com",
        timeout_seconds: float = 15.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout_seconds, transport=transport)

    def close(self) -> None:
        self._client.close()

    def instruments(self, *, inst_type: str) -> list[OkxCexInstrument]:
        rows = self._get("/api/v5/public/instruments", params={"instType": inst_type.strip().upper()})
        instruments: list[OkxCexInstrument] = []
        for row in rows:
            instrument = _instrument_from_row(row)
            if instrument is not None:
                instruments.append(instrument)
        return instruments

    def tickers(self, *, inst_type: str) -> list[OkxCexTicker]:
        requested_inst_type = inst_type.strip().upper()
        rows = self._get("/api/v5/market/tickers", params={"instType": requested_inst_type})
        tickers: list[OkxCexTicker] = []
        for row in rows:
            ticker = _ticker_from_row(row, default_inst_type=requested_inst_type)
            if ticker is not None:
                tickers.append(ticker)
        return tickers

    def ticker(self, *, inst_id: str) -> OkxCexTicker | None:
        rows = self._get("/api/v5/market/ticker", params={"instId": inst_id.strip().upper()})
        for row in rows:
            ticker = _ticker_from_row(row)
            if ticker is not None:
                return ticker
        return None

    def _get(self, path: str, *, params: dict[str, str]) -> list[dict[str, Any]]:
        response = self._client.get(path, params=params)
        return _rows_from_response(response, endpoint=path)


def _rows_from_response(response: httpx.Response, *, endpoint: str) -> list[dict[str, Any]]:
    if response.status_code >= 400:
        raise OkxClientError(f"OKX {endpoint} returned HTTP {response.status_code}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise OkxClientError(f"OKX {endpoint} returned non-json response") from exc
    if not isinstance(payload, dict):
        raise OkxClientError(f"OKX {endpoint} returned invalid envelope")
    if payload.get("code") not in (None, "0", 0):
        message = payload.get("msg") or payload.get("message") or "unknown error"
        raise OkxClientError(f"OKX {endpoint} failed: {message}")
    data = payload.get("data")
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        nested = data.get("data") or data.get("list") or data.get("tokens")
        if isinstance(nested, list):
            return [row for row in nested if isinstance(row, dict)]
    return []


def _instrument_from_row(row: dict[str, Any]) -> OkxCexInstrument | None:
    inst_id = _text(row.get("instId") or row.get("inst_id"))
    inst_type = _text(row.get("instType") or row.get("inst_type"))
    base = _text(row.get("baseCcy") or row.get("baseCurrency") or row.get("base"))
    quote = _text(row.get("quoteCcy") or row.get("quoteCurrency") or row.get("quote"))
    if inst_id and (not base or not quote):
        parsed_base, parsed_quote = _base_quote_from_inst_id(inst_id)
        base = base or parsed_base
        quote = quote or parsed_quote
    if not inst_id or not inst_type or not base or not quote:
        return None
    return OkxCexInstrument(
        inst_id=inst_id.upper(),
        inst_type=inst_type.upper(),
        base_symbol=base.upper(),
        quote_symbol=quote.upper(),
        state=_text(row.get("state")) or "unknown",
        raw=dict(row),
    )


def _ticker_from_row(row: dict[str, Any], *, default_inst_type: str = "UNKNOWN") -> OkxCexTicker | None:
    inst_id = _text(row.get("instId") or row.get("inst_id"))
    inst_type = _text(row.get("instType") or row.get("inst_type")) or default_inst_type
    if not inst_id:
        return None
    return OkxCexTicker(
        inst_id=inst_id.upper(),
        inst_type=inst_type.upper(),
        last_price=_float(row.get("last") or row.get("lastPx") or row.get("price")),
        volume_24h=_float(row.get("volCcy24h") or row.get("vol24h") or row.get("volume24h")),
        open_interest=_float(row.get("oi") or row.get("openInterest")),
        raw=dict(row),
    )


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _base_quote_from_inst_id(inst_id: str) -> tuple[str | None, str | None]:
    parts = [part.strip() for part in inst_id.split("-") if part.strip()]
    if len(parts) < 2:
        return None, None
    return parts[0], parts[1]


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
