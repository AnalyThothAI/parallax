from __future__ import annotations

from typing import Any

import httpx


class OkxClientError(RuntimeError):
    pass


def items_from_response(response: httpx.Response, *, endpoint: str) -> list[Any]:
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


__all__ = ["OkxClientError", "items_from_response", "rows_from_response"]
