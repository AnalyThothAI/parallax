from __future__ import annotations

import importlib
import inspect
from decimal import Decimal
from typing import Any

import pytest

from parallax.app.runtime.provider_wiring.types import AssetMarketProviders
from parallax.domains.asset_market.providers import CexTicker, DexTokenQuote
from parallax.domains.asset_market.services.event_market_capture import (
    EventMarketCaptureService,
    TickLookup,
)
from parallax.domains.asset_market.types import MarketTick, market_tick_id

NOW_MS = 1_700_000_100_000
EVENT_MS = 1_700_000_090_000


def test_existing_recent_tick_hit_returns_capture_without_provider_io() -> None:
    provider = RaisingDexQuoteProvider()
    service = EventMarketCaptureService(
        providers=AssetMarketProviders(dex_quote_market=provider),
        now_ms=lambda: NOW_MS,
        max_existing_tick_lag_ms=30_000,
    )
    lookup = RecordingTickLookup(row=_market_tick_row(observed_at_ms=EVENT_MS - 2_000, source_tier="tier1_ws"))

    result = service.capture_for_event(
        event_id="event-1",
        intent_id="intent-1",
        resolution_id="resolution-1",
        resolution={
            "target_type": "chain_token",
            "target_id": "solana:ABC111",
            "chain_id": "solana",
            "token_address": "ABC111",
        },
        event_ms=EVENT_MS,
        tick_lookup=lookup.as_tick_lookup(),
    )

    assert lookup.calls == [("chain_token", "solana:ABC111", EVENT_MS, 30_000)]
    assert provider.calls == []
    assert result.tick == MarketTick(**lookup.row)
    assert result.capture.event_id == "event-1"
    assert result.capture.intent_id == "intent-1"
    assert result.capture.resolution_id == "resolution-1"
    assert result.capture.target_type == "chain_token"
    assert result.capture.target_id == "solana:ABC111"
    assert result.capture.t_event_ms == EVENT_MS
    assert result.capture.tick_id == "tick-existing"
    assert result.capture.tick_lag_ms == 2_000
    assert result.capture.capture_method == "tier1_ws"
    assert result.capture.capture_reason == "fresh_tick"
    assert result.capture.created_at_ms == NOW_MS


def test_capture_for_event_does_not_call_provider_when_no_fresh_tick() -> None:
    dex_provider = RaisingDexQuoteProvider()
    cex_provider = RaisingCexMarketProvider()
    service = EventMarketCaptureService(
        providers=AssetMarketProviders(dex_quote_market=dex_provider, cex_market=cex_provider),
        now_ms=lambda: NOW_MS,
    )
    lookup = RecordingTickLookup(row=None)

    result = service.capture_for_event(
        event_id="evt",
        intent_id="intent",
        resolution_id="res",
        resolution={
            "target_type": "chain_token",
            "target_id": "solana:ABC111",
            "chain_id": "solana",
            "token_address": "ABC111",
        },
        event_ms=EVENT_MS,
        tick_lookup=lookup.as_tick_lookup(),
    )

    assert dex_provider.calls == []
    assert cex_provider.calls == []
    assert result.tick is None
    assert result.capture.capture_method == "unavailable"
    assert result.capture.capture_reason == "pending_backfill"
    assert result.capture.tick_id is None
    assert result.capture.tick_lag_ms is None
    assert result.capture.created_at_ms == NOW_MS


def test_capture_backfill_quote_dispatches_chain_token_to_dex_provider() -> None:
    quote = DexTokenQuote(
        chain_id="solana",
        address="ABC111",
        observed_at_ms=EVENT_MS + 100,
        price_usd=1.23,
        raw={},
    )
    provider = RecordingDexQuoteProvider([quote])
    service = EventMarketCaptureService(
        providers=AssetMarketProviders(dex_quote_market=provider),
        now_ms=lambda: NOW_MS,
    )

    result = service.capture_backfill_quote(
        event_id="event-1",
        intent_id="intent-1",
        resolution_id="resolution-1",
        resolution={
            "target_type": "chain_token",
            "target_id": "solana:ABC111",
            "chain_id": "solana",
            "token_address": "ABC111",
        },
        event_ms=EVENT_MS,
    )

    assert result.tick is not None
    assert result.tick.source_tier == "tier3_inline"
    assert result.capture.capture_method == "tier3_inline"
    assert result.capture.capture_reason == "inline_quote"


def test_capture_backfill_quote_dispatches_cex_symbol_to_cex_provider() -> None:
    provider = RecordingCexMarketProvider(
        CexTicker(
            inst_id="BTCUSDT",
            inst_type="SPOT",
            last_price=70_000.25,
            volume_24h=None,
            open_interest=None,
            raw={"ts": str(EVENT_MS + 50)},
        )
    )
    service = EventMarketCaptureService(
        providers=AssetMarketProviders(cex_market=provider),
        now_ms=lambda: NOW_MS,
    )

    result = service.capture_backfill_quote(
        event_id="event-2",
        intent_id="intent-2",
        resolution_id="resolution-2",
        resolution={
            "target_type": "cex_symbol",
            "target_id": "OKX:BTCUSDT",
            "exchange": "OKX",
            "instrument": "BTCUSDT",
        },
        event_ms=EVENT_MS,
    )

    assert provider.calls == ["BTCUSDT"]
    assert result.tick is not None
    assert result.tick.source_tier == "tier3_inline"
    assert result.capture.capture_method == "tier3_inline"
    assert result.capture.capture_reason == "inline_ticker"


def test_capture_backfill_quote_returns_unavailable_for_invalid_resolution() -> None:
    service = EventMarketCaptureService(
        providers=AssetMarketProviders(),
        now_ms=lambda: NOW_MS,
    )

    result = service.capture_backfill_quote(
        event_id="event-1",
        intent_id="intent-1",
        resolution_id="resolution-1",
        resolution={"target_type": "unknown", "target_id": ""},
        event_ms=EVENT_MS,
    )

    assert result.tick is None
    assert result.capture.capture_method == "unavailable"
    assert result.capture.capture_reason == "invalid_resolution"


def test_inline_dex_quote_returns_tier3_market_tick_and_capture() -> None:
    quote = DexTokenQuote(
        chain_id="solana",
        address="ABC111",
        observed_at_ms=EVENT_MS + 100,
        price_usd=1.23,
        market_cap_usd=123_000.0,
        liquidity_usd=45_000.5,
        volume_24h_usd=9_876.5,
        holders=321,
        raw={"price": "1.23"},
    )
    provider = RecordingDexQuoteProvider([quote])
    service = EventMarketCaptureService(
        providers=AssetMarketProviders(dex_quote_market=provider),
        now_ms=lambda: NOW_MS,
    )

    result = service.capture_backfill_quote(
        event_id="event-1",
        intent_id="intent-1",
        resolution_id="resolution-1",
        resolution={
            "target_type": "chain_token",
            "target_id": "solana:ABC111",
            "chain_id": "solana",
            "token_address": "ABC111",
        },
        event_ms=EVENT_MS,
    )

    assert [(item.chain_id, item.address) for item in provider.calls[0]] == [("solana", "ABC111")]
    assert result.tick is not None
    assert result.tick.tick_id == market_tick_id(
        target_type="chain_token",
        target_id="solana:ABC111",
        source_provider="okx_dex_rest",
        observed_at_ms=EVENT_MS + 100,
    )
    assert result.tick.target_type == "chain_token"
    assert result.tick.target_id == "solana:ABC111"
    assert result.tick.chain == "solana"
    assert result.tick.token_address == "ABC111"
    assert result.tick.exchange is None
    assert result.tick.instrument is None
    assert result.tick.pricefeed_id is None
    assert result.tick.source_tier == "tier3_inline"
    assert result.tick.source_provider == "okx_dex_rest"
    assert result.tick.observed_at_ms == EVENT_MS + 100
    assert result.tick.received_at_ms == NOW_MS
    assert result.tick.created_at_ms == NOW_MS
    assert result.tick.price_usd == Decimal("1.23")
    assert result.tick.market_cap_usd == Decimal("123000.0")
    assert result.tick.liquidity_usd == Decimal("45000.5")
    assert result.tick.volume_24h_usd == Decimal("9876.5")
    assert result.tick.holders == 321
    assert result.tick.raw_payload_json == {"price": "1.23"}
    assert result.capture.tick_id == result.tick.tick_id
    assert result.capture.tick_lag_ms == 100
    assert result.capture.capture_method == "tier3_inline"
    assert result.capture.capture_reason == "inline_quote"


def test_inline_dex_quote_preserves_gmgn_source_provider() -> None:
    quote = DexTokenQuote(
        chain_id="eip155:1",
        address="0xabc",
        observed_at_ms=EVENT_MS + 100,
        price_usd=1.23,
        market_cap_usd=123_000.0,
        raw={"source_provider": "gmgn_dex_quote"},
    )

    result = EventMarketCaptureService(
        providers=AssetMarketProviders(dex_quote_market=RecordingDexQuoteProvider([quote])),
        now_ms=lambda: NOW_MS,
    ).capture_backfill_quote(
        event_id="event-1",
        intent_id="intent-1",
        resolution_id="resolution-1",
        resolution={"target_type": "chain_token", "target_id": "eip155:1:0xabc"},
        event_ms=EVENT_MS,
    )

    assert result.tick is not None
    assert result.tick.source_provider == "gmgn_dex_quote"
    assert result.tick.tick_id == market_tick_id(
        target_type="chain_token",
        target_id="eip155:1:0xabc",
        source_provider="gmgn_dex_quote",
        observed_at_ms=EVENT_MS + 100,
    )


@pytest.mark.parametrize(
    ("target_id", "expected_chain", "expected_address"),
    [
        ("solana:ABC111", "solana", "ABC111"),
        ("eip155:1:0xabc", "eip155:1", "0xabc"),
    ],
)
def test_inline_dex_quote_parses_chain_and_address_from_target_id(
    target_id: str,
    expected_chain: str,
    expected_address: str,
) -> None:
    provider = RecordingDexQuoteProvider(
        [
            DexTokenQuote(
                chain_id=expected_chain,
                address=expected_address,
                observed_at_ms=EVENT_MS + 100,
                price_usd=1.23,
                raw={},
            )
        ]
    )

    result = EventMarketCaptureService(
        providers=AssetMarketProviders(dex_quote_market=provider),
        now_ms=lambda: NOW_MS,
    ).capture_backfill_quote(
        event_id="event-1",
        intent_id="intent-1",
        resolution_id="resolution-1",
        resolution={"target_type": "chain_token", "target_id": target_id},
        event_ms=EVENT_MS,
    )

    assert [(item.chain_id, item.address) for item in provider.calls[0]] == [(expected_chain, expected_address)]
    assert result.tick is not None
    assert result.tick.chain == expected_chain
    assert result.tick.token_address == expected_address


def test_inline_cex_ticker_returns_tier3_market_tick_and_capture() -> None:
    provider = RecordingCexMarketProvider(
        CexTicker(
            inst_id="BTCUSDT",
            inst_type="SPOT",
            last_price=70_000.25,
            volume_24h=1_250_000.5,
            open_interest=None,
            raw={"instId": "BTCUSDT", "ts": str(EVENT_MS + 50), "openInterestUsd": "9100000"},
        )
    )
    service = EventMarketCaptureService(
        providers=AssetMarketProviders(cex_market=provider),
        now_ms=lambda: NOW_MS,
    )

    result = service.capture_backfill_quote(
        event_id="event-2",
        intent_id="intent-2",
        resolution_id="resolution-2",
        resolution={
            "target_type": "cex_symbol",
            "target_id": "OKX:BTCUSDT",
            "exchange": "OKX",
            "instrument": "BTCUSDT",
        },
        event_ms=EVENT_MS,
    )

    assert provider.calls == ["BTCUSDT"]
    assert result.tick is not None
    assert result.tick.tick_id == market_tick_id(
        target_type="cex_symbol",
        target_id="OKX:BTCUSDT",
        source_provider="binance_cex_rest",
        observed_at_ms=EVENT_MS + 50,
    )
    assert result.tick.target_type == "cex_symbol"
    assert result.tick.target_id == "OKX:BTCUSDT"
    assert result.tick.chain is None
    assert result.tick.token_address is None
    assert result.tick.exchange == "OKX"
    assert result.tick.instrument == "BTCUSDT"
    assert result.tick.source_tier == "tier3_inline"
    assert result.tick.source_provider == "binance_cex_rest"
    assert result.tick.observed_at_ms == EVENT_MS + 50
    assert result.tick.received_at_ms == NOW_MS
    assert result.tick.price_usd == Decimal("70000.25")
    assert result.tick.volume_24h_usd == Decimal("1250000.5")
    assert result.tick.open_interest_usd == Decimal("9100000")
    assert result.tick.raw_payload_json == {
        "instId": "BTCUSDT",
        "ts": str(EVENT_MS + 50),
        "openInterestUsd": "9100000",
    }
    assert result.capture.capture_method == "tier3_inline"
    assert result.capture.capture_reason == "inline_ticker"
    assert result.capture.tick_lag_ms == 50


def test_inline_cex_ticker_parses_exchange_and_instrument_from_target_id() -> None:
    provider = RecordingCexMarketProvider(
        CexTicker(
            inst_id="PEPEUSDT",
            inst_type="SPOT",
            last_price=0.0000123,
            volume_24h=None,
            open_interest=None,
            raw={"ts": str(EVENT_MS + 25)},
        )
    )

    result = EventMarketCaptureService(
        providers=AssetMarketProviders(cex_market=provider),
        now_ms=lambda: NOW_MS,
    ).capture_backfill_quote(
        event_id="event-1",
        intent_id="intent-1",
        resolution_id="resolution-1",
        resolution={"target_type": "cex_symbol", "target_id": "binance:PEPEUSDT"},
        event_ms=EVENT_MS,
    )

    assert provider.calls == ["PEPEUSDT"]
    assert result.tick is not None
    assert result.tick.exchange == "binance"
    assert result.tick.instrument == "PEPEUSDT"


def test_inline_dex_no_quote_and_null_price_are_unavailable() -> None:
    no_quote_result = EventMarketCaptureService(
        providers=AssetMarketProviders(dex_quote_market=RecordingDexQuoteProvider([])),
        now_ms=lambda: NOW_MS,
    ).capture_backfill_quote(
        event_id="event-1",
        intent_id="intent-1",
        resolution_id="resolution-1",
        resolution={
            "target_type": "chain_token",
            "target_id": "solana:ABC111",
            "chain_id": "solana",
            "token_address": "ABC111",
        },
        event_ms=EVENT_MS,
    )
    null_price_result = EventMarketCaptureService(
        providers=AssetMarketProviders(
            dex_quote_market=RecordingDexQuoteProvider(
                [
                    DexTokenQuote(
                        chain_id="solana",
                        address="ABC111",
                        observed_at_ms=EVENT_MS,
                        price_usd=None,
                        raw={},
                    )
                ]
            )
        ),
        now_ms=lambda: NOW_MS,
    ).capture_backfill_quote(
        event_id="event-2",
        intent_id="intent-2",
        resolution_id="resolution-2",
        resolution={
            "target_type": "chain_token",
            "target_id": "solana:ABC111",
            "chain_id": "solana",
            "token_address": "ABC111",
        },
        event_ms=EVENT_MS,
    )

    assert no_quote_result.tick is None
    assert no_quote_result.capture.capture_method == "unavailable"
    assert no_quote_result.capture.capture_reason == "provider_no_quote"
    assert no_quote_result.capture.tick_id is None
    assert no_quote_result.capture.tick_lag_ms is None
    assert null_price_result.tick is None
    assert null_price_result.capture.capture_method == "unavailable"
    assert null_price_result.capture.capture_reason == "no_market_data"


@pytest.mark.parametrize("price_usd", [0.0, -1.0, float("nan"), float("inf"), "not-a-number"])
def test_inline_dex_invalid_price_is_unavailable(price_usd: Any) -> None:
    result = EventMarketCaptureService(
        providers=AssetMarketProviders(
            dex_quote_market=RecordingDexQuoteProvider(
                [
                    DexTokenQuote(
                        chain_id="solana",
                        address="ABC111",
                        observed_at_ms=EVENT_MS,
                        price_usd=price_usd,
                        raw={},
                    )
                ]
            )
        ),
        now_ms=lambda: NOW_MS,
    ).capture_backfill_quote(
        event_id="event-1",
        intent_id="intent-1",
        resolution_id="resolution-1",
        resolution={
            "target_type": "chain_token",
            "target_id": "solana:ABC111",
            "chain_id": "solana",
            "token_address": "ABC111",
        },
        event_ms=EVENT_MS,
    )

    assert result.tick is None
    assert result.capture.capture_method == "unavailable"
    assert result.capture.capture_reason == "no_market_data"


def test_inline_dex_invalid_optional_market_fields_do_not_block_tick() -> None:
    result = EventMarketCaptureService(
        providers=AssetMarketProviders(
            dex_quote_market=RecordingDexQuoteProvider(
                [
                    DexTokenQuote(
                        chain_id="solana",
                        address="ABC111",
                        observed_at_ms=EVENT_MS,
                        price_usd=1.23,
                        liquidity_usd="not-a-number",
                        volume_24h_usd=float("nan"),
                        market_cap_usd=float("inf"),
                        holders="not-a-number",
                        raw={},
                    )
                ]
            )
        ),
        now_ms=lambda: NOW_MS,
    ).capture_backfill_quote(
        event_id="event-1",
        intent_id="intent-1",
        resolution_id="resolution-1",
        resolution={
            "target_type": "chain_token",
            "target_id": "solana:ABC111",
            "chain_id": "solana",
            "token_address": "ABC111",
        },
        event_ms=EVENT_MS,
    )

    assert result.tick is not None
    assert result.tick.price_usd == Decimal("1.23")
    assert result.tick.liquidity_usd is None
    assert result.tick.volume_24h_usd is None
    assert result.tick.market_cap_usd is None
    assert result.tick.holders is None
    assert result.capture.capture_method == "tier3_inline"


@pytest.mark.parametrize("last_price", [0.0, -1.0, float("nan"), float("inf"), "not-a-number"])
def test_inline_cex_invalid_price_is_unavailable(last_price: Any) -> None:
    result = EventMarketCaptureService(
        providers=AssetMarketProviders(
            cex_market=RecordingCexMarketProvider(
                CexTicker(
                    inst_id="BTCUSDT",
                    inst_type="SPOT",
                    last_price=last_price,
                    volume_24h=None,
                    open_interest=None,
                    raw={},
                )
            )
        ),
        now_ms=lambda: NOW_MS,
    ).capture_backfill_quote(
        event_id="event-1",
        intent_id="intent-1",
        resolution_id="resolution-1",
        resolution={
            "target_type": "cex_symbol",
            "target_id": "OKX:BTCUSDT",
            "exchange": "OKX",
            "instrument": "BTCUSDT",
        },
        event_ms=EVENT_MS,
    )

    assert result.tick is None
    assert result.capture.capture_method == "unavailable"
    assert result.capture.capture_reason == "no_market_data"


def test_inline_cex_invalid_optional_volume_does_not_block_tick() -> None:
    result = EventMarketCaptureService(
        providers=AssetMarketProviders(
            cex_market=RecordingCexMarketProvider(
                CexTicker(
                    inst_id="BTCUSDT",
                    inst_type="SPOT",
                    last_price=70_000.25,
                    volume_24h="not-a-number",
                    open_interest=float("inf"),
                    raw={"ts": str(EVENT_MS + 50)},
                )
            )
        ),
        now_ms=lambda: NOW_MS,
    ).capture_backfill_quote(
        event_id="event-1",
        intent_id="intent-1",
        resolution_id="resolution-1",
        resolution={
            "target_type": "cex_symbol",
            "target_id": "OKX:BTCUSDT",
            "exchange": "OKX",
            "instrument": "BTCUSDT",
        },
        event_ms=EVENT_MS,
    )

    assert result.tick is not None
    assert result.tick.price_usd == Decimal("70000.25")
    assert result.tick.volume_24h_usd is None
    assert result.capture.capture_method == "tier3_inline"


def test_inline_dex_provider_timestamp_before_event_preserves_capture_with_absolute_lag() -> None:
    result = EventMarketCaptureService(
        providers=AssetMarketProviders(
            dex_quote_market=RecordingDexQuoteProvider(
                [
                    DexTokenQuote(
                        chain_id="solana",
                        address="ABC111",
                        observed_at_ms=EVENT_MS - 1_000,
                        price_usd=1.23,
                        raw={},
                    )
                ]
            )
        ),
        now_ms=lambda: NOW_MS,
    ).capture_backfill_quote(
        event_id="event-1",
        intent_id="intent-1",
        resolution_id="resolution-1",
        resolution={
            "target_type": "chain_token",
            "target_id": "solana:ABC111",
            "chain_id": "solana",
            "token_address": "ABC111",
        },
        event_ms=EVENT_MS,
    )

    assert result.tick is not None
    assert result.tick.observed_at_ms == EVENT_MS - 1_000
    assert result.capture.tick_lag_ms == 1_000


def test_provider_exception_maps_to_unavailable_without_raising() -> None:
    result = EventMarketCaptureService(
        providers=AssetMarketProviders(dex_quote_market=FailingDexQuoteProvider(TimeoutError("slow provider"))),
        now_ms=lambda: NOW_MS,
    ).capture_backfill_quote(
        event_id="event-1",
        intent_id="intent-1",
        resolution_id="resolution-1",
        resolution={
            "target_type": "chain_token",
            "target_id": "solana:ABC111",
            "chain_id": "solana",
            "token_address": "ABC111",
        },
        event_ms=EVENT_MS,
    )

    assert result.tick is None
    assert result.capture.capture_method == "unavailable"
    assert result.capture.capture_reason == "provider_timeout"
    assert result.capture.created_at_ms == NOW_MS


def test_event_market_capture_service_does_not_import_repositories() -> None:
    module = importlib.import_module("parallax.domains.asset_market.services.event_market_capture")

    assert "repositories" not in inspect.getsource(module)


class RecordingTickLookup:
    def __init__(self, *, row: dict[str, Any] | None) -> None:
        self.row = row
        self.calls: list[tuple[str, str, int, int]] = []

    def as_tick_lookup(self) -> TickLookup:
        return TickLookup(latest_at_or_before=self.latest_at_or_before)

    def latest_at_or_before(
        self,
        target_type: str,
        target_id: str,
        at_ms: int,
        max_lag_ms: int,
    ) -> dict[str, Any] | None:
        self.calls.append((target_type, target_id, at_ms, max_lag_ms))
        return self.row


class RecordingDexQuoteProvider:
    def __init__(self, quotes: list[DexTokenQuote]) -> None:
        self.quotes = quotes
        self.calls: list[Any] = []

    def token_quotes(self, tokens):
        self.calls.append(tokens)
        return self.quotes


class RaisingDexQuoteProvider:
    def __init__(self) -> None:
        self.calls: list[Any] = []

    def token_quotes(self, tokens):
        self.calls.append(tokens)
        raise AssertionError("provider should not be called")


class FailingDexQuoteProvider:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    def token_quotes(self, tokens):
        raise self.exc


class RecordingCexMarketProvider:
    def __init__(self, ticker: CexTicker | None) -> None:
        self._ticker = ticker
        self.calls: list[str] = []

    def ticker(self, *, inst_id: str) -> CexTicker | None:
        self.calls.append(inst_id)
        return self._ticker


class RaisingCexMarketProvider:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def ticker(self, *, inst_id: str) -> CexTicker | None:
        self.calls.append(inst_id)
        raise AssertionError("provider should not be called")


def _market_tick_row(*, observed_at_ms: int, source_tier: str) -> dict[str, Any]:
    return {
        "tick_id": "tick-existing",
        "target_type": "chain_token",
        "target_id": "solana:ABC111",
        "chain": "solana",
        "token_address": "ABC111",
        "exchange": None,
        "instrument": None,
        "pricefeed_id": None,
        "source_tier": source_tier,
        "source_provider": "binance_dex_ws",
        "observed_at_ms": observed_at_ms,
        "received_at_ms": observed_at_ms + 10,
        "price_usd": Decimal("1.11"),
        "liquidity_usd": Decimal("1000"),
        "volume_24h_usd": Decimal("2000"),
        "market_cap_usd": Decimal("3000"),
        "holders": 456,
        "created_at_ms": observed_at_ms + 20,
        "raw_payload_json": {"from": "ws"},
    }
