from __future__ import annotations

import asyncio
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from gmgn_twitter_intel.app.runtime.providers_wiring import AssetMarketProviders
from gmgn_twitter_intel.domains.asset_market.providers import DexTokenQuote
from gmgn_twitter_intel.domains.asset_market.runtime.event_anchor_backfill_worker import (
    EventAnchorBackfillWorker,
)
from gmgn_twitter_intel.domains.asset_market.services.event_market_capture import (
    EventMarketCaptureService,
)
from gmgn_twitter_intel.domains.asset_market.types import EnrichedEventCapture, MarketTick

NOW_MS = 1_777_800_000_000
EVENT_MS = NOW_MS - 5_000


def test_run_once_no_pending_rows_emits_zero_counts() -> None:
    db = _FakeDB(pending_rows=[])
    wake = _RecordingWakeEmitter()
    worker = EventAnchorBackfillWorker(
        pool_bundle=db,
        capture_service=_StubCaptureService(),
        wake_emitter=wake,
        batch_size=10,
        concurrency=2,
        min_age_ms=100,
        clock=lambda: NOW_MS,
        settings=_settings(),
    )

    result = asyncio.run(worker.run_once())

    assert result.processed == 0
    assert result.skipped == 0
    assert result.notes["pending_selected"] == 0
    assert result.notes["ticks_inserted"] == 0
    assert result.notes["captures_attached"] == 0
    assert db.list_calls == [{"limit": 10, "min_age_ms": 100, "now_ms": NOW_MS}]
    assert db.inserted_ticks == []
    assert db.attached_captures == []
    assert wake.emitted == []


def test_run_once_dispatches_to_capture_service_under_semaphore_then_persists_and_wakes() -> None:
    rows = [_pending_row(event_id="event-1", target_type="chain_token", target_id="solana:AAA")]
    quote = DexTokenQuote(
        chain_id="solana",
        address="AAA",
        observed_at_ms=EVENT_MS + 100,
        price_usd=Decimal("1.25"),
        raw={"price": "1.25"},
    )
    provider = _RecordingDexQuoteProvider([quote])
    service = EventMarketCaptureService(
        providers=AssetMarketProviders(dex_quote_market=provider),
        now_ms=lambda: NOW_MS,
    )
    db = _FakeDB(pending_rows=rows)
    wake = _RecordingWakeEmitter()
    worker = EventAnchorBackfillWorker(
        pool_bundle=db,
        capture_service=service,
        wake_emitter=wake,
        batch_size=10,
        concurrency=4,
        min_age_ms=100,
        clock=lambda: NOW_MS,
        settings=_settings(),
    )

    result = asyncio.run(worker.run_once())

    assert provider.calls == [
        [(quote.chain_id, quote.address)],
    ]
    assert len(db.inserted_ticks) == 1
    tick = db.inserted_ticks[0]
    assert isinstance(tick, MarketTick)
    assert tick.target_type == "chain_token"
    assert tick.target_id == "solana:AAA"
    assert tick.source_tier == "tier3_inline"

    assert len(db.attached_captures) == 1
    capture = db.attached_captures[0]
    assert isinstance(capture, EnrichedEventCapture)
    assert capture.event_id == "event-1"
    assert capture.capture_method == "tier3_inline"
    assert capture.capture_reason == "async_backfill"
    assert capture.tick_id == tick.tick_id
    assert capture.tick_lag_ms is not None and capture.tick_lag_ms >= 0

    assert result.processed == 1
    assert result.skipped == 0
    assert result.notes["pending_selected"] == 1
    assert result.notes["ticks_inserted"] == 1
    assert result.notes["captures_attached"] == 1

    assert wake.emitted == [("chain_token", "solana:AAA")]


def test_run_once_cex_target_dispatches_to_message_cex_provider() -> None:
    rows = [_pending_row(event_id="evt-cex", target_type="cex_symbol", target_id="OKX:BTC-USDT")]

    captured_calls: list[dict[str, Any]] = []

    class _Service:
        def capture_backfill_quote(self, **kwargs: Any):
            captured_calls.append(kwargs)
            tick = MarketTick(
                tick_id="tick-1",
                target_type="cex_symbol",
                target_id="OKX:BTC-USDT",
                chain=None,
                token_address=None,
                exchange="OKX",
                instrument="BTC-USDT",
                pricefeed_id=None,
                source_tier="tier3_inline",
                source_provider="okx_cex_rest",
                observed_at_ms=EVENT_MS + 25,
                received_at_ms=NOW_MS,
                price_usd=Decimal("70000"),
                liquidity_usd=None,
                volume_24h_usd=None,
                market_cap_usd=None,
                holders=None,
                created_at_ms=NOW_MS,
                raw_payload_json={},
            )
            capture = EnrichedEventCapture(
                event_id=kwargs["event_id"],
                intent_id=kwargs["intent_id"],
                resolution_id=kwargs["resolution_id"],
                target_type="cex_symbol",
                target_id="OKX:BTC-USDT",
                t_event_ms=int(kwargs["event_ms"]),
                tick_id=tick.tick_id,
                tick_lag_ms=25,
                capture_method="tier3_inline",
                capture_reason="inline_ticker",
                created_at_ms=NOW_MS,
            )
            from gmgn_twitter_intel.domains.asset_market.services.event_market_capture import CaptureResult

            return CaptureResult(tick=tick, capture=capture)

    db = _FakeDB(pending_rows=rows)
    wake = _RecordingWakeEmitter()
    worker = EventAnchorBackfillWorker(
        pool_bundle=db,
        capture_service=_Service(),
        wake_emitter=wake,
        batch_size=5,
        concurrency=2,
        min_age_ms=0,
        clock=lambda: NOW_MS,
        settings=_settings(),
    )

    result = asyncio.run(worker.run_once())

    assert len(captured_calls) == 1
    call = captured_calls[0]
    assert call["resolution"]["target_type"] == "cex_symbol"
    assert call["resolution"]["target_id"] == "OKX:BTC-USDT"
    assert call["resolution"]["exchange"] == "OKX"
    assert call["resolution"]["instrument"] == "BTC-USDT"

    assert result.processed == 1
    assert db.attached_captures[0].capture_reason == "async_backfill"
    assert wake.emitted == [("cex_symbol", "OKX:BTC-USDT")]


def test_run_once_unavailable_capture_is_skipped_and_not_wake_emitted() -> None:
    rows = [_pending_row(event_id="evt-unavailable", target_type="chain_token", target_id="solana:NOPE")]

    class _Service:
        def capture_backfill_quote(self, **kwargs: Any):
            from gmgn_twitter_intel.domains.asset_market.services.event_market_capture import CaptureResult

            capture = EnrichedEventCapture(
                event_id=kwargs["event_id"],
                intent_id=kwargs["intent_id"],
                resolution_id=kwargs["resolution_id"],
                target_type="chain_token",
                target_id="solana:NOPE",
                t_event_ms=int(kwargs["event_ms"]),
                tick_id=None,
                tick_lag_ms=None,
                capture_method="unavailable",
                capture_reason="provider_no_quote",
                created_at_ms=NOW_MS,
            )
            return CaptureResult(tick=None, capture=capture)

    db = _FakeDB(pending_rows=rows)
    wake = _RecordingWakeEmitter()
    worker = EventAnchorBackfillWorker(
        pool_bundle=db,
        capture_service=_Service(),
        wake_emitter=wake,
        batch_size=5,
        concurrency=2,
        min_age_ms=0,
        clock=lambda: NOW_MS,
        settings=_settings(),
    )

    result = asyncio.run(worker.run_once())

    assert result.processed == 0
    assert result.skipped == 1
    assert result.notes["pending_selected"] == 1
    assert result.notes["ticks_inserted"] == 0
    assert result.notes["captures_attached"] == 0
    assert result.notes["skipped_reasons"] == {"provider_no_quote": 1}
    assert db.inserted_ticks == []
    assert db.attached_captures == []
    assert wake.emitted == []


def test_run_once_wakes_only_targets_that_were_attached() -> None:
    rows = [
        _pending_row(event_id="evt-first", target_type="chain_token", target_id="solana:FIRST"),
        _pending_row(event_id="evt-second", target_type="chain_token", target_id="solana:SECOND"),
    ]

    class _Service:
        def capture_backfill_quote(self, **kwargs: Any):
            from gmgn_twitter_intel.domains.asset_market.services.event_market_capture import CaptureResult

            target_id = kwargs["resolution"]["target_id"]
            tick = MarketTick(
                tick_id=f"tick-{target_id}",
                target_type="chain_token",
                target_id=target_id,
                chain="solana",
                token_address=target_id.rsplit(":", 1)[-1],
                exchange=None,
                instrument=None,
                pricefeed_id=None,
                source_tier="tier3_inline",
                source_provider="gmgn_dex_quote",
                observed_at_ms=EVENT_MS + 25,
                received_at_ms=NOW_MS,
                price_usd=Decimal("1"),
                liquidity_usd=None,
                volume_24h_usd=None,
                market_cap_usd=None,
                holders=None,
                created_at_ms=NOW_MS,
                raw_payload_json={},
            )
            capture = EnrichedEventCapture(
                event_id=kwargs["event_id"],
                intent_id=kwargs["intent_id"],
                resolution_id=kwargs["resolution_id"],
                target_type="chain_token",
                target_id=target_id,
                t_event_ms=int(kwargs["event_ms"]),
                tick_id=tick.tick_id,
                tick_lag_ms=25,
                capture_method="tier3_inline",
                capture_reason="inline_quote",
                created_at_ms=NOW_MS,
            )
            return CaptureResult(tick=tick, capture=capture)

    db = _FakeDB(pending_rows=rows, attach_results=[False, True])
    wake = _RecordingWakeEmitter()
    worker = EventAnchorBackfillWorker(
        pool_bundle=db,
        capture_service=_Service(),
        wake_emitter=wake,
        batch_size=5,
        concurrency=2,
        min_age_ms=0,
        clock=lambda: NOW_MS,
        settings=_settings(),
    )

    result = asyncio.run(worker.run_once())

    assert result.processed == 1
    assert len(db.inserted_ticks) == 2
    assert [capture.target_id for capture in db.attached_captures] == [
        "solana:FIRST",
        "solana:SECOND",
    ]
    assert wake.emitted == [("chain_token", "solana:SECOND")]


def _settings() -> Any:
    return SimpleNamespace(
        enabled=True,
        interval_seconds=1.0,
        timeout_seconds=120.0,
        batch_size=10,
        concurrency=4,
        min_age_ms=100,
    )


def _pending_row(*, event_id: str, target_type: str, target_id: str) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "intent_id": f"intent-{event_id}",
        "resolution_id": f"resolution-{event_id}",
        "target_type": target_type,
        "target_id": target_id,
        "t_event_ms": EVENT_MS,
        "tick_id": None,
        "tick_lag_ms": None,
        "capture_method": "unavailable",
        "capture_reason": "pending_backfill",
        "created_at_ms": NOW_MS - 500,
    }


class _RecordingDexQuoteProvider:
    def __init__(self, quotes: list[DexTokenQuote]) -> None:
        self.quotes = quotes
        self.calls: list[list[tuple[str, str]]] = []

    def token_quotes(self, tokens: Any) -> list[DexTokenQuote]:
        self.calls.append([(item.chain_id, item.address) for item in tokens])
        return self.quotes


class _StubCaptureService:
    def capture_backfill_quote(self, **_: Any):
        raise AssertionError("capture_service should not be called when no pending rows")


class _RecordingWakeEmitter:
    def __init__(self) -> None:
        self.emitted: list[tuple[str, str]] = []

    def notify_market_tick_written(self, *, target_type: str, target_id: str) -> None:
        self.emitted.append((target_type, target_id))


class _FakeDB:
    def __init__(
        self,
        *,
        pending_rows: list[dict[str, Any]],
        attach_results: list[bool] | None = None,
    ) -> None:
        self._pending_rows = pending_rows
        self._attach_results = list(attach_results) if attach_results is not None else None
        self.list_calls: list[dict[str, Any]] = []
        self.inserted_ticks: list[MarketTick] = []
        self.attached_captures: list[EnrichedEventCapture] = []

    def worker_session(self, name: str, statement_timeout_seconds: float | None = None):
        return _FakeWorkerSession(self)


class _FakeWorkerSession:
    def __init__(self, db: _FakeDB) -> None:
        self._db = db

    def __enter__(self) -> _FakeRepos:
        return _FakeRepos(self._db)

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class _FakeRepos:
    def __init__(self, db: _FakeDB) -> None:
        self._db = db
        self.enriched_events = _FakeEnrichedEventRepo(db)
        self.market_ticks = _FakeMarketTickRepo(db)
        self.conn = SimpleNamespace(commit=lambda: None)


class _FakeEnrichedEventRepo:
    def __init__(self, db: _FakeDB) -> None:
        self._db = db

    def list_pending_backfill(self, *, limit: int, now_ms: int, min_age_ms: int) -> list[dict[str, Any]]:
        self._db.list_calls.append({"limit": limit, "now_ms": now_ms, "min_age_ms": min_age_ms})
        return list(self._db._pending_rows)

    def attach_backfill_capture(self, capture: EnrichedEventCapture) -> bool:
        self._db.attached_captures.append(capture)
        if self._db._attach_results is None:
            return True
        return self._db._attach_results.pop(0)


class _FakeMarketTickRepo:
    def __init__(self, db: _FakeDB) -> None:
        self._db = db

    def insert_ticks(self, ticks: Any) -> int:
        materialized = list(ticks)
        self._db.inserted_ticks.extend(materialized)
        return len(materialized)
