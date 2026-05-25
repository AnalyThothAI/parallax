from __future__ import annotations

from typing import Any

from gmgn_twitter_intel.domains.token_intel.queries.stocks_radar_query import StocksRadarQuery

from .asset_flow_service import WINDOW_MS


class StocksRadarService:
    def __init__(
        self,
        *,
        conn: Any,
        stock_rows_query: Any | None = None,
    ) -> None:
        self.stock_rows_query = stock_rows_query or StocksRadarQuery(conn)

    def stocks_radar(
        self,
        *,
        window: str,
        limit: int,
        scope: str,
        now_ms: int,
    ) -> dict[str, Any]:
        parsed_limit = max(0, int(limit))
        since_ms = int(now_ms) - WINDOW_MS[window]
        rows = self.stock_rows_query.stock_rows(
            since_ms=since_ms,
            now_ms=int(now_ms),
            scope=scope,
            limit=parsed_limit,
        )
        quotes = self._quote_snapshots([str(row["symbol"]) for row in rows])
        items = [
            _public_row(row, quote=quotes.get(str(row["symbol"])) or _unavailable_quote("missing_quote"))
            for row in rows
        ]
        quote_ready_count = sum(1 for item in items if item["quote"]["status"] == "ready")
        quote_unavailable_count = len(items) - quote_ready_count
        return {
            "window": window,
            "scope": scope,
            "query": {
                "window": window,
                "scope": scope,
                "limit": parsed_limit,
                "window_start_ms": since_ms,
                "window_end_ms": int(now_ms),
            },
            "rows": items,
            "health": {
                "returned_count": len(items),
                "quote_ready_count": quote_ready_count,
                "quote_unavailable_count": quote_unavailable_count,
            },
        }

    def _quote_snapshots(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
        unique_symbols = []
        seen: set[str] = set()
        for symbol in symbols:
            normalized = symbol.strip().upper()
            if normalized and normalized not in seen:
                unique_symbols.append(normalized)
                seen.add(normalized)
        if not unique_symbols:
            return {}
        return {symbol: _unavailable_quote("read_model_unavailable") for symbol in unique_symbols}


def _public_row(row: dict[str, Any], *, quote: dict[str, Any]) -> dict[str, Any]:
    return {
        "target": {
            "target_type": "MarketInstrument",
            "target_id": row.get("target_id"),
            "symbol": row.get("symbol"),
            "market": "us_equity",
            "exchange": row.get("exchange"),
            "instrument_type": row.get("instrument_type"),
            "name": row.get("security_name"),
        },
        "attention": {
            "mentions": int(row.get("mentions") or 0),
            "unique_authors": int(row.get("unique_authors") or 0),
            "watched_mentions": int(row.get("watched_mentions") or 0),
            "latest_seen_ms": _int_or_none(row.get("latest_seen_ms")),
        },
        "latest_event": {
            "event_id": row.get("latest_event_id"),
            "author_handle": row.get("latest_author_handle"),
            "text": row.get("latest_text"),
            "received_at_ms": _int_or_none(row.get("latest_seen_ms")),
        },
        "quote": quote,
        "source_event_ids": [str(value) for value in (row.get("source_event_ids") or []) if value],
        "row_health": [] if quote.get("status") == "ready" else ["quote_unavailable"],
    }


def _unavailable_quote(error: str) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "price": None,
        "reference_close_price": None,
        "change_pct": None,
        "asof": None,
        "provider": None,
        "provider_symbol": None,
        "latency_class": None,
        "freshness_class": None,
        "error": error,
    }


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
