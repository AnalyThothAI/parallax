from __future__ import annotations

import csv
from dataclasses import dataclass
from io import StringIO
from typing import Any

import httpx

SOURCE_NASDAQ_TRADER = "nasdaq_trader"
NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"


@dataclass(frozen=True, slots=True)
class NasdaqTraderSymbol:
    symbol: str
    exchange: str | None
    security_name: str | None
    instrument_type: str
    raw_payload: dict[str, str]


class NasdaqTraderSymbolClient:
    def __init__(
        self,
        *,
        timeout_seconds: float = 15.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(timeout=timeout_seconds, transport=transport)

    def close(self) -> None:
        self._client.close()

    def symbols(self) -> list[NasdaqTraderSymbol]:
        nasdaq_listed = self._get_text(NASDAQ_LISTED_URL)
        other_listed = self._get_text(OTHER_LISTED_URL)
        return parse_nasdaq_trader_symbols(nasdaq_listed_text=nasdaq_listed, other_listed_text=other_listed)

    def _get_text(self, url: str) -> str:
        response = self._client.get(url)
        if response.status_code >= 400:
            raise RuntimeError(f"Nasdaq Trader symbol directory returned HTTP {response.status_code}: {url}")
        return response.text


def sync_us_equity_symbols(*, registry: Any, client: Any, observed_at_ms: int) -> dict[str, Any]:
    rows = client.symbols()
    active_symbols: set[str] = set()
    written = 0
    for row in rows:
        active_symbols.add(row.symbol)
        registry.upsert_us_equity_symbol(
            symbol=row.symbol,
            exchange=row.exchange,
            security_name=row.security_name,
            instrument_type=row.instrument_type,
            source=SOURCE_NASDAQ_TRADER,
            source_updated_at_ms=observed_at_ms,
            raw_payload=row.raw_payload,
            observed_at_ms=observed_at_ms,
            commit=False,
        )
        written += 1
    deactivated = registry.deactivate_missing_us_equity_symbols(
        source=SOURCE_NASDAQ_TRADER,
        active_symbols=active_symbols,
        observed_at_ms=observed_at_ms,
        commit=False,
    )
    registry.conn.commit()
    return {
        "source": SOURCE_NASDAQ_TRADER,
        "symbols_seen": len(rows),
        "symbols_written": written,
        "symbols_deactivated": int(deactivated),
        "observed_at_ms": int(observed_at_ms),
    }


def parse_nasdaq_trader_symbols(*, nasdaq_listed_text: str, other_listed_text: str) -> list[NasdaqTraderSymbol]:
    rows: list[NasdaqTraderSymbol] = []
    rows.extend(_parse_nasdaq_listed(nasdaq_listed_text))
    rows.extend(_parse_other_listed(other_listed_text))
    return rows


def _parse_nasdaq_listed(text: str) -> list[NasdaqTraderSymbol]:
    rows: list[NasdaqTraderSymbol] = []
    for raw in _dict_rows(text):
        symbol = _symbol(raw.get("Symbol"))
        if not symbol or _is_test_issue(raw) or _is_file_creation_row(symbol):
            continue
        rows.append(
            NasdaqTraderSymbol(
                symbol=symbol,
                exchange="NASDAQ",
                security_name=_text(raw.get("Security Name")),
                instrument_type=_instrument_type(raw),
                raw_payload=dict(raw),
            )
        )
    return rows


def _parse_other_listed(text: str) -> list[NasdaqTraderSymbol]:
    rows: list[NasdaqTraderSymbol] = []
    for raw in _dict_rows(text):
        symbol = _symbol(raw.get("ACT Symbol") or raw.get("NASDAQ Symbol"))
        if not symbol or _is_test_issue(raw) or _is_file_creation_row(symbol):
            continue
        rows.append(
            NasdaqTraderSymbol(
                symbol=symbol,
                exchange=_text(raw.get("Exchange")),
                security_name=_text(raw.get("Security Name")),
                instrument_type=_instrument_type(raw),
                raw_payload=dict(raw),
            )
        )
    return rows


def _dict_rows(text: str) -> list[dict[str, str]]:
    reader = csv.DictReader(StringIO(text.strip()), delimiter="|")
    return [{str(key): str(value or "") for key, value in row.items() if key is not None} for row in reader if row]


def _instrument_type(row: dict[str, str]) -> str:
    return "etf" if _text(row.get("ETF")).upper() == "Y" else "equity"


def _is_test_issue(row: dict[str, str]) -> bool:
    return _text(row.get("Test Issue")).upper() == "Y"


def _is_file_creation_row(symbol: str) -> bool:
    return symbol.upper().startswith("FILE CREATION TIME")


def _symbol(value: str | None) -> str:
    return str(value or "").strip().lstrip("$").upper()


def _text(value: str | None) -> str:
    return str(value or "").strip()
