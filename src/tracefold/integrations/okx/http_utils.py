from __future__ import annotations

from typing import Any

import httpx


class OkxClientError(RuntimeError):
    pass


class OkxPaymentRequiredError(OkxClientError):
    pass


def items_from_response(response: httpx.Response, *, endpoint: str) -> list[Any]:
    if response.status_code == 402 and _is_x402_payment_required(response):
        raise OkxPaymentRequiredError(f"OKX {endpoint} returned x402 payment required")
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
        return list(data)
    if isinstance(data, dict):
        nested = data.get("data") or data.get("list") or data.get("tokens")
        if isinstance(nested, list):
            return list(nested)
    return []


def rows_from_response(response: httpx.Response, *, endpoint: str) -> list[dict[str, Any]]:
    return [row for row in items_from_response(response, endpoint=endpoint) if isinstance(row, dict)]


def _is_x402_payment_required(response: httpx.Response) -> bool:
    try:
        payload = response.json()
    except ValueError:
        return False
    if not isinstance(payload, dict):
        return False
    accepts = payload.get("accepts")
    resource = payload.get("resource")
    return payload.get("x402Version") is not None and isinstance(accepts, list) and isinstance(resource, dict)


__all__ = ["OkxClientError", "OkxPaymentRequiredError", "items_from_response", "rows_from_response"]
