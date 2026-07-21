from __future__ import annotations

import asyncio
import threading
from dataclasses import asdict
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest

from parallax.app.runtime.provider_wiring.types import AssetMarketProviders
from parallax.domains.asset_market.providers import DexTokenQuote
from parallax.domains.asset_market.runtime.event_anchor_backfill_worker import (
    EventAnchorBackfillWorker,
    _attempt_count,
)
from parallax.domains.asset_market.services.event_market_capture import (
    EventMarketCaptureService,
)
from parallax.domains.asset_market.types import EnrichedEventCapture, MarketTick

NOW_MS = 1_777_800_000_000
EVENT_MS = NOW_MS - 5_000


def test_event_anchor_provider_not_called_without_claim() -> None:
    db = _FakeDB(pending_rows=[])
    worker = EventAnchorBackfillWorker(
        pool_bundle=db,
        capture_service=_StubCaptureService(),
        clock=lambda: NOW_MS,
        settings=_settings(),
    )

    result = asyncio.run(worker.run_once())

    assert result.processed == 0
    assert result.skipped == 0
    assert result.notes["pending_selected"] == 0
    assert "ready_jobs_reconciled" not in result.notes
    assert result.notes["ticks_inserted"] == 0
    assert result.notes["captures_attached"] == 0
    assert db.claim_calls == [
        {
            "limit": 10,
            "min_age_ms": 100,
            "now_ms": NOW_MS,
            "lease_owner": "event_anchor_backfill",
            "lease_ms": 60_000,
        }
    ]
    assert db.ready_job_calls == []
    assert db.inserted_ticks == []
    assert db.attached_captures == []


def test_event_anchor_worker_requires_formal_db_bundle_contract() -> None:
    with pytest.raises(RuntimeError, match="event_anchor_backfill_db_required"):
        EventAnchorBackfillWorker(
            settings=_settings(),
            capture_service=_StubCaptureService(),
        )


def test_event_anchor_worker_requires_provider_bundle_without_injected_capture_service() -> None:
    with pytest.raises(RuntimeError, match="event_anchor_backfill_providers_required"):
        EventAnchorBackfillWorker(
            settings=_settings(),
            pool_bundle=_FakeDB(pending_rows=[]),
        )


def test_run_once_expires_stale_jobs_before_provider_calls() -> None:
    row = _pending_row(event_id="evt-expired", target_type="chain_token", target_id="solana:OLD")
    row["active_until_ms"] = NOW_MS - 1
    db = _FakeDB(pending_rows=[], expired_rows=[row])
    worker = EventAnchorBackfillWorker(
        pool_bundle=db,
        capture_service=_StubCaptureService(),
        clock=lambda: NOW_MS,
        settings=_settings(),
    )

    result = asyncio.run(worker.run_once())

    assert result.processed == 0
    assert result.skipped == 0
    assert result.notes["expired_jobs"] == 1
    assert result.notes["terminal_failures"] == 1
    assert db.terminal_captures == [("evt-expired", "intent-evt-expired", "backfill_expired")]
    assert db.terminal_jobs == [("evt-expired", "intent-evt-expired", "expired", "backfill_expired")]
    assert db.provider_calls == 0


def test_run_once_requires_worker_session_transaction_before_expiring_stale_jobs() -> None:
    row = _pending_row(event_id="evt-expired", target_type="chain_token", target_id="solana:OLD")
    row["active_until_ms"] = NOW_MS - 1
    db = _FakeDB(pending_rows=[], expired_rows=[row], expose_transaction=False)
    worker = EventAnchorBackfillWorker(
        pool_bundle=db,
        capture_service=_StubCaptureService(),
        clock=lambda: NOW_MS,
        settings=_settings(),
    )

    with pytest.raises(AttributeError, match="transaction"):
        asyncio.run(worker.run_once())

    assert db.expire_stale_calls == []
    assert db.terminal_jobs == []
    assert db.terminal_captures == []
    assert db.claim_calls == []


def test_run_once_with_no_due_rows_does_not_scan_ready_anchor_facts() -> None:
    db = _FakeDB(pending_rows=[], ready_jobs=6)
    worker = EventAnchorBackfillWorker(
        pool_bundle=db,
        capture_service=_StubCaptureService(),
        clock=lambda: NOW_MS,
        settings=_settings(),
    )

    result = asyncio.run(worker.run_once())

    assert result.processed == 0
    assert result.skipped == 0
    assert "ready_jobs_reconciled" not in result.notes
    assert db.ready_job_calls == []
    assert db.provider_calls == 0


def test_run_once_reads_due_jobs_not_enriched_event_pending_rows() -> None:
    rows = [_pending_row(event_id="event-job", target_type="chain_token", target_id="solana:JOB")]
    db = _FakeDB(pending_rows=rows, forbid_enriched_event_queue_scan=True)
    worker = EventAnchorBackfillWorker(
        pool_bundle=db,
        capture_service=_UnavailableService("provider_no_quote"),
        clock=lambda: NOW_MS,
        settings=_settings(),
    )

    result = asyncio.run(worker.run_once())

    assert result.processed == 0
    assert result.notes["pending_selected"] == 1
    assert result.notes["terminal_failures"] == 1
    assert db.terminal_captures == [("event-job", "intent-event-job", "provider_no_quote")]
    assert db.terminal_jobs == [("event-job", "intent-event-job", "failed", "provider_no_quote")]
    assert db.terminal_job_guards == [
        {
            "event_id": "event-job",
            "intent_id": "intent-event-job",
            "lease_owner": "event_anchor_backfill",
            "attempt_count": 1,
        }
    ]
    assert db.rescheduled_jobs == []


def test_concurrent_captures_use_isolated_workerspace_session_depth() -> None:
    hold_started = threading.Event()
    release_hold = threading.Event()
    rows = [
        _pending_row(event_id="event-held-session", target_type="chain_token", target_id="solana:HOLD"),
        _pending_row(event_id="event-provider", target_type="chain_token", target_id="solana:PROVIDER"),
    ]
    db = _FakeDB(
        pending_rows=rows,
        nearest_hold_target_id="solana:HOLD",
        nearest_hold_started=hold_started,
        nearest_hold_release=release_hold,
    )
    worker = EventAnchorBackfillWorker(
        pool_bundle=db,
        capture_service=_ReleasingUnavailableService("provider_no_quote", release_hold),
        clock=lambda: NOW_MS,
        settings=_settings(concurrency=2),
    )

    result = asyncio.run(worker.run_once())

    assert hold_started.is_set()
    assert release_hold.is_set()
    assert result.processed == 0
    assert result.notes["pending_selected"] == 2
    assert result.notes["terminal_failures"] == 2
    assert sorted(event_id for event_id, _intent_id, _reason in db.terminal_captures) == [
        "event-held-session",
        "event-provider",
    ]


def test_run_once_reschedules_rate_limited_jobs_inside_active_window() -> None:
    row = _pending_row(event_id="evt-rate", target_type="chain_token", target_id="solana:RATE")
    row["attempt_count"] = 0
    row["active_until_ms"] = NOW_MS + 60_000
    db = _FakeDB(pending_rows=[row])
    worker = EventAnchorBackfillWorker(
        pool_bundle=db,
        capture_service=_UnavailableService("rate_limited"),
        clock=lambda: NOW_MS,
        settings=_settings(max_attempts=3),
    )

    result = asyncio.run(worker.run_once())

    assert result.processed == 0
    assert result.notes["rescheduled_jobs"] == 1
    assert db.rescheduled_jobs == [("evt-rate", "intent-evt-rate", "rate_limited")]
    assert db.reschedule_job_guards == [
        {
            "event_id": "evt-rate",
            "intent_id": "intent-evt-rate",
            "lease_owner": "event_anchor_backfill",
            "attempt_count": 1,
        }
    ]
    assert db.terminal_captures == []
    assert db.terminal_jobs == []


def test_run_once_stale_reschedule_lease_has_no_other_side_effects() -> None:
    row = _pending_row(event_id="evt-stale-rate", target_type="chain_token", target_id="solana:RATE")
    row["attempt_count"] = 0
    row["active_until_ms"] = NOW_MS + 60_000
    db = _FakeDB(pending_rows=[row], reschedule_results=[False])
    worker = EventAnchorBackfillWorker(
        pool_bundle=db,
        capture_service=_UnavailableService("rate_limited"),
        clock=lambda: NOW_MS,
        settings=_settings(max_attempts=3),
    )

    result = asyncio.run(worker.run_once())

    assert result.processed == 0
    assert result.notes["rescheduled_jobs"] == 0
    assert db.reschedule_mark_attempts == [
        {
            "event_id": "evt-stale-rate",
            "intent_id": "intent-evt-stale-rate",
            "lease_owner": "event_anchor_backfill",
            "attempt_count": 1,
        }
    ]
    assert db.rescheduled_jobs == []
    assert db.terminal_captures == []
    assert db.terminal_jobs == []
    assert db.attached_captures == []
    assert db.inserted_ticks == []


def test_event_anchor_claim_attempt_helpers_require_claim_attempt_field_without_default() -> None:
    row = _pending_row(event_id="evt-missing-attempt", target_type="chain_token", target_id="solana:MISS")
    row.pop("attempt_count")

    with pytest.raises(ValueError, match="event_anchor_backfill_claim_attempt_count_required") as exc_info:
        _attempt_count(row)

    assert isinstance(exc_info.value.__cause__, KeyError)


def test_temporary_reschedule_requires_claim_attempt_field_without_default() -> None:
    row = _pending_row(event_id="evt-rate-missing-attempt", target_type="chain_token", target_id="solana:RATE")
    row.pop("attempt_count")
    worker = EventAnchorBackfillWorker(
        pool_bundle=_FakeDB(pending_rows=[]),
        capture_service=_StubCaptureService(),
        clock=lambda: NOW_MS,
        settings=_settings(max_attempts=3),
    )

    with pytest.raises(ValueError, match="event_anchor_backfill_claim_attempt_count_required") as exc_info:
        worker._should_reschedule(row=row, reason="rate_limited", now_ms=NOW_MS)

    assert isinstance(exc_info.value.__cause__, KeyError)


def test_run_once_dispatches_to_capture_service_then_persists_fact_and_current() -> None:
    rows = [_pending_row(event_id="event-1", target_type="chain_token", target_id="solana:AAA")]
    quote = DexTokenQuote(
        chain_id="solana",
        address="AAA",
        observed_at_ms=EVENT_MS + 100,
        price_usd=Decimal("1.25"),
        raw={"price": "1.25"},
    )
    db = _FakeDB(pending_rows=rows)
    provider = _RecordingDexQuoteProvider([quote], db=db)
    service = EventMarketCaptureService(
        providers=AssetMarketProviders(dex_quote_market=provider),
        now_ms=lambda: NOW_MS,
    )
    worker = EventAnchorBackfillWorker(
        pool_bundle=db,
        capture_service=service,
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
    assert db.done_job_guards == [
        {
            "event_id": "event-1",
            "intent_id": "intent-event-1",
            "lease_owner": "event_anchor_backfill",
            "attempt_count": 1,
        }
    ]

    assert db.dirty_target_enqueues == [
        {
            "rows": [("Asset", "asset:solana:AAA")],
            "reason": "market_tick_current_changed",
            "now_ms": NOW_MS,
        }
    ]


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
                source_provider="binance_cex_rest",
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
                tick_observed_at_ms=tick.observed_at_ms,
                tick_id=tick.tick_id,
                tick_lag_ms=25,
                capture_method="tier3_inline",
                capture_reason="inline_ticker",
                created_at_ms=NOW_MS,
            )
            from parallax.domains.asset_market.services.event_market_capture import CaptureResult

            return CaptureResult(tick=tick, capture=capture)

    db = _FakeDB(pending_rows=rows)
    worker = EventAnchorBackfillWorker(
        pool_bundle=db,
        capture_service=_Service(),
        clock=lambda: NOW_MS,
        settings=_settings(batch_size=5, concurrency=2, min_age_ms=0),
    )

    result = asyncio.run(worker.run_once())

    assert len(captured_calls) == 1
    call = captured_calls[0]
    assert call["resolution"] == {"target_type": "cex_symbol", "target_id": "OKX:BTC-USDT"}

    assert result.processed == 1
    assert db.attached_captures[0].capture_reason == "async_backfill"


def test_run_once_provider_no_quote_terminalizes_job_without_market_write() -> None:
    rows = [_pending_row(event_id="evt-unavailable", target_type="chain_token", target_id="solana:NOPE")]

    class _Service:
        def capture_backfill_quote(self, **kwargs: Any):
            from parallax.domains.asset_market.services.event_market_capture import CaptureResult

            capture = EnrichedEventCapture(
                event_id=kwargs["event_id"],
                intent_id=kwargs["intent_id"],
                resolution_id=kwargs["resolution_id"],
                target_type="chain_token",
                target_id="solana:NOPE",
                t_event_ms=int(kwargs["event_ms"]),
                tick_observed_at_ms=None,
                tick_id=None,
                tick_lag_ms=None,
                capture_method="unavailable",
                capture_reason="provider_no_quote",
                created_at_ms=NOW_MS,
            )
            return CaptureResult(tick=None, capture=capture)

    db = _FakeDB(pending_rows=rows)
    worker = EventAnchorBackfillWorker(
        pool_bundle=db,
        capture_service=_Service(),
        clock=lambda: NOW_MS,
        settings=_settings(batch_size=5, concurrency=2, min_age_ms=0),
    )

    result = asyncio.run(worker.run_once())

    assert result.processed == 0
    assert result.skipped == 0
    assert result.notes["pending_selected"] == 1
    assert result.notes["ticks_inserted"] == 0
    assert result.notes["captures_attached"] == 0
    assert result.notes["terminal_failures"] == 1
    assert result.notes["skipped_reasons"] == {"provider_no_quote": 1}
    assert db.inserted_ticks == []
    assert db.attached_captures == []
    assert db.terminal_captures == [("evt-unavailable", "intent-evt-unavailable", "provider_no_quote")]
    assert db.terminal_jobs == [("evt-unavailable", "intent-evt-unavailable", "failed", "provider_no_quote")]
    assert db.terminal_job_guards == [
        {
            "event_id": "evt-unavailable",
            "intent_id": "intent-evt-unavailable",
            "lease_owner": "event_anchor_backfill",
            "attempt_count": 1,
        }
    ]


def test_run_once_stale_terminal_lease_does_not_mark_enriched_event_terminal() -> None:
    rows = [_pending_row(event_id="evt-stale", target_type="chain_token", target_id="solana:STALE")]
    db = _FakeDB(pending_rows=rows, terminal_results=[False])
    worker = EventAnchorBackfillWorker(
        pool_bundle=db,
        capture_service=_UnavailableService("provider_no_quote"),
        clock=lambda: NOW_MS,
        settings=_settings(batch_size=5, concurrency=2, min_age_ms=0),
    )

    result = asyncio.run(worker.run_once())

    assert result.processed == 0
    assert result.notes["terminal_failures"] == 0
    assert db.terminal_mark_attempts == [
        {
            "event_id": "evt-stale",
            "intent_id": "intent-evt-stale",
            "lease_owner": "event_anchor_backfill",
            "attempt_count": 1,
        }
    ]
    assert db.terminal_jobs == []
    assert db.terminal_captures == []


def test_run_once_persists_only_targets_that_were_attached() -> None:
    rows = [
        _pending_row(event_id="evt-first", target_type="chain_token", target_id="solana:FIRST"),
        _pending_row(event_id="evt-second", target_type="chain_token", target_id="solana:SECOND"),
    ]

    class _Service:
        def capture_backfill_quote(self, **kwargs: Any):
            from parallax.domains.asset_market.services.event_market_capture import CaptureResult

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
                tick_observed_at_ms=tick.observed_at_ms,
                tick_id=tick.tick_id,
                tick_lag_ms=25,
                capture_method="tier3_inline",
                capture_reason="inline_quote",
                created_at_ms=NOW_MS,
            )
            return CaptureResult(tick=tick, capture=capture)

    db = _FakeDB(pending_rows=rows, attach_results=[False, True])
    worker = EventAnchorBackfillWorker(
        pool_bundle=db,
        capture_service=_Service(),
        clock=lambda: NOW_MS,
        settings=_settings(batch_size=5, concurrency=2, min_age_ms=0),
    )

    result = asyncio.run(worker.run_once())

    assert result.processed == 1
    assert len(db.inserted_ticks) == 1
    assert db.inserted_ticks[0].target_id == "solana:SECOND"
    assert [capture.target_id for capture in db.attached_captures] == ["solana:SECOND"]
    assert db.dirty_target_enqueues == [
        {
            "rows": [("Asset", "asset:solana:SECOND")],
            "reason": "market_tick_current_changed",
            "now_ms": NOW_MS,
        }
    ]


def _settings(
    *,
    batch_size: int = 10,
    concurrency: int = 4,
    max_attempts: int = 3,
    min_age_ms: int = 100,
    lease_ms: int = 60_000,
    active_window_ms: int = 300_000,
    max_anchor_lag_ms: int = 60_000,
) -> Any:
    return SimpleNamespace(
        enabled=True,
        interval_seconds=1.0,
        timeout_seconds=120.0,
        batch_size=batch_size,
        concurrency=concurrency,
        max_attempts=max_attempts,
        lease_ms=lease_ms,
        min_age_ms=min_age_ms,
        active_window_ms=active_window_ms,
        max_anchor_lag_ms=max_anchor_lag_ms,
        statement_timeout_seconds=30.0,
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
        "next_run_at_ms": NOW_MS - 100,
        "active_until_ms": NOW_MS + 60_000,
        "attempt_count": 0,
        "lease_owner": None,
        "leased_until_ms": None,
    }


class _RecordingDexQuoteProvider:
    def __init__(self, quotes: list[DexTokenQuote], *, db: _FakeDB | None = None) -> None:
        self.quotes = quotes
        self.db = db
        self.calls: list[list[tuple[str, str]]] = []

    def token_quotes(self, tokens: Any) -> list[DexTokenQuote]:
        if self.db is not None:
            assert self.db.open_sessions == 0
        self.calls.append([(item.chain_id, item.address) for item in tokens])
        return self.quotes


class _StubCaptureService:
    def capture_backfill_quote(self, **_: Any):
        raise AssertionError("capture_service should not be called when no pending rows")


class _UnavailableService:
    def __init__(self, reason: str) -> None:
        self.reason = reason

    def capture_backfill_quote(self, **kwargs: Any):
        from parallax.domains.asset_market.services.event_market_capture import CaptureResult

        capture = EnrichedEventCapture(
            event_id=kwargs["event_id"],
            intent_id=kwargs["intent_id"],
            resolution_id=kwargs["resolution_id"],
            target_type=kwargs["resolution"]["target_type"],
            target_id=kwargs["resolution"]["target_id"],
            t_event_ms=int(kwargs["event_ms"]),
            tick_observed_at_ms=None,
            tick_id=None,
            tick_lag_ms=None,
            capture_method="unavailable",
            capture_reason=self.reason,
            created_at_ms=NOW_MS,
        )
        return CaptureResult(tick=None, capture=capture)


class _ReleasingUnavailableService(_UnavailableService):
    def __init__(self, reason: str, release_event: threading.Event) -> None:
        super().__init__(reason)
        self.release_event = release_event

    def capture_backfill_quote(self, **kwargs: Any):
        self.release_event.set()
        return super().capture_backfill_quote(**kwargs)


class _FakeDB:
    def __init__(
        self,
        *,
        pending_rows: list[dict[str, Any]],
        expired_rows: list[dict[str, Any]] | None = None,
        ready_jobs: int = 0,
        attach_results: list[bool] | None = None,
        terminal_results: list[bool] | None = None,
        reschedule_results: list[bool] | None = None,
        forbid_enriched_event_queue_scan: bool = False,
        nearest_hold_target_id: str | None = None,
        nearest_hold_started: threading.Event | None = None,
        nearest_hold_release: threading.Event | None = None,
        expose_transaction: bool = True,
    ) -> None:
        self._pending_rows = pending_rows
        self._expired_rows = list(expired_rows or [])
        self._ready_jobs = ready_jobs
        self._attach_results = list(attach_results) if attach_results is not None else None
        self._terminal_results = list(terminal_results) if terminal_results is not None else None
        self._reschedule_results = list(reschedule_results) if reschedule_results is not None else None
        self.forbid_enriched_event_queue_scan = forbid_enriched_event_queue_scan
        self.claim_calls: list[dict[str, Any]] = []
        self.expire_stale_calls: list[dict[str, Any]] = []
        self.ready_job_calls: list[dict[str, Any]] = []
        self.inserted_ticks: list[MarketTick] = []
        self.attached_captures: list[EnrichedEventCapture] = []
        self.terminal_captures: list[tuple[str, str, str]] = []
        self.terminal_jobs: list[tuple[str, str, str, str]] = []
        self.rescheduled_jobs: list[tuple[str, str, str]] = []
        self.done_jobs: list[tuple[str, str]] = []
        self.terminal_job_guards: list[dict[str, Any]] = []
        self.reschedule_job_guards: list[dict[str, Any]] = []
        self.done_job_guards: list[dict[str, Any]] = []
        self.terminal_mark_attempts: list[dict[str, Any]] = []
        self.reschedule_mark_attempts: list[dict[str, Any]] = []
        self.provider_calls = 0
        self.dirty_target_enqueues: list[dict[str, Any]] = []
        self.open_sessions = 0
        self.nearest_hold_target_id = nearest_hold_target_id
        self.nearest_hold_started = nearest_hold_started
        self.nearest_hold_release = nearest_hold_release
        self.expose_transaction = expose_transaction

    def worker_session(self, name: str, statement_timeout_seconds: float | None = None):
        return _FakeWorkerSession(self)


class _FakeWorkerSession:
    def __init__(self, db: _FakeDB) -> None:
        self._db = db
        self._snapshot: dict[str, int] = {}

    def __enter__(self) -> _FakeRepos:
        self._db.open_sessions += 1
        self._snapshot = {
            "inserted_ticks": len(self._db.inserted_ticks),
            "attached_captures": len(self._db.attached_captures),
            "terminal_captures": len(self._db.terminal_captures),
            "terminal_jobs": len(self._db.terminal_jobs),
            "rescheduled_jobs": len(self._db.rescheduled_jobs),
            "done_jobs": len(self._db.done_jobs),
            "dirty_target_enqueues": len(self._db.dirty_target_enqueues),
            "terminal_job_guards": len(self._db.terminal_job_guards),
            "reschedule_job_guards": len(self._db.reschedule_job_guards),
            "done_job_guards": len(self._db.done_job_guards),
        }
        if self._db.expose_transaction:
            return _FakeRepos(self._db)
        return _FakeReposWithoutTransaction(self._db)

    def __exit__(self, exc_type, exc, tb) -> None:
        self._db.open_sessions -= 1
        if exc_type is not None:
            for name, size in self._snapshot.items():
                del getattr(self._db, name)[size:]


class _FakeRepos:
    def __init__(self, db: _FakeDB) -> None:
        self._db = db
        self.enriched_events = _FakeEnrichedEventRepo(db)
        self.event_anchor_jobs = _FakeEventAnchorJobRepo(db)
        self.registry = _FakeRegistry()
        self.market_ticks = _FakeMarketTickRepo(db)
        self.market_tick_current = _FakeMarketTickCurrent()
        self.token_radar_dirty_targets = _FakeRadarDirtyTargets(db)

    def transaction(self):
        return _FakeWorkerSession(self._db)

    def require_transaction(self, *, operation: str) -> None:
        return None


class _FakeReposWithoutTransaction:
    def __init__(self, db: _FakeDB) -> None:
        self._db = db
        self.enriched_events = _FakeEnrichedEventRepo(db)
        self.event_anchor_jobs = _FakeEventAnchorJobRepo(db)
        self.registry = _FakeRegistry()
        self.market_ticks = _FakeMarketTickRepo(db)
        self.market_tick_current = _FakeMarketTickCurrent()
        self.token_radar_dirty_targets = _FakeRadarDirtyTargets(db)

    def require_transaction(self, *, operation: str) -> None:
        return None


class _FakeEnrichedEventRepo:
    def __init__(self, db: _FakeDB) -> None:
        self._db = db

    def list_pending_backfill(self, *, limit: int, now_ms: int, min_age_ms: int) -> list[dict[str, Any]]:
        if self._db.forbid_enriched_event_queue_scan:
            raise AssertionError("worker must read event_anchor_backfill_jobs, not enriched_events pending rows")
        raise AssertionError("worker must not read enriched_events pending rows at runtime")

    def attach_backfill_capture(self, capture: EnrichedEventCapture) -> bool:
        self._db.attached_captures.append(capture)
        if self._db._attach_results is None:
            return True
        return self._db._attach_results.pop(0)

    def mark_backfill_terminal(self, *, event_id: str, intent_id: str, reason: str) -> bool:
        self._db.terminal_captures.append((event_id, intent_id, reason))
        return True


class _FakeEventAnchorJobRepo:
    def __init__(self, db: _FakeDB) -> None:
        self._db = db

    def claim_due(
        self,
        *,
        limit: int,
        now_ms: int,
        min_age_ms: int,
        lease_owner: str,
        lease_ms: int,
    ) -> list[dict[str, Any]]:
        self._db.claim_calls.append(
            {
                "limit": limit,
                "now_ms": now_ms,
                "min_age_ms": min_age_ms,
                "lease_owner": lease_owner,
                "lease_ms": lease_ms,
            }
        )
        claimed: list[dict[str, Any]] = []
        for row in self._db._pending_rows:
            copied = dict(row)
            copied["status"] = "running"
            copied["lease_owner"] = lease_owner
            copied["leased_until_ms"] = now_ms + lease_ms
            copied["attempt_count"] = int(copied.get("attempt_count") or 0) + 1
            claimed.append(copied)
        return claimed

    def list_due(self, **_: Any) -> list[dict[str, Any]]:
        raise AssertionError("runtime event-anchor worker must claim jobs before provider work")

    def list_expired(self, **_: Any) -> list[dict[str, Any]]:
        raise AssertionError("runtime event-anchor worker must expire stale jobs through the repository lease path")

    def expire_stale(
        self,
        *,
        limit: int,
        now_ms: int,
        max_attempts: int,
        retry_backoff_ms: int,
    ) -> dict[str, Any]:
        self._db.expire_stale_calls.append(
            {
                "limit": limit,
                "now_ms": now_ms,
                "max_attempts": max_attempts,
                "retry_backoff_ms": retry_backoff_ms,
            }
        )
        terminal_rows = [dict(row) for row in self._db._expired_rows]
        for row in terminal_rows:
            self._db.terminal_jobs.append((str(row["event_id"]), str(row["intent_id"]), "expired", "backfill_expired"))
        return {
            "expired": len(terminal_rows),
            "failed": 0,
            "rescheduled": 0,
            "terminal_rows": terminal_rows,
        }

    def mark_ready_jobs_done(self, *, limit: int, now_ms: int) -> int:
        raise AssertionError("runtime event-anchor worker must not reconcile ready jobs by scanning facts")

    def mark_done(self, *, event_id: str, intent_id: str, now_ms: int, lease_owner: str, attempt_count: int) -> bool:
        self._db.done_jobs.append((event_id, intent_id))
        self._db.done_job_guards.append(
            {
                "event_id": event_id,
                "intent_id": intent_id,
                "lease_owner": lease_owner,
                "attempt_count": attempt_count,
            }
        )
        return True

    def mark_terminal(
        self,
        *,
        event_id: str,
        intent_id: str,
        status: str,
        reason: str,
        now_ms: int,
        lease_owner: str,
        attempt_count: int,
    ) -> bool:
        terminal_result = True if self._db._terminal_results is None else self._db._terminal_results.pop(0)
        attempt = {
            "event_id": event_id,
            "intent_id": intent_id,
            "lease_owner": lease_owner,
            "attempt_count": attempt_count,
        }
        self._db.terminal_mark_attempts.append(attempt)
        self._db.terminal_job_guards.append(attempt)
        if terminal_result:
            self._db.terminal_jobs.append((event_id, intent_id, status, reason))
        return terminal_result

    def reschedule(
        self,
        *,
        event_id: str,
        intent_id: str,
        reason: str,
        now_ms: int,
        next_run_at_ms: int,
        lease_owner: str,
        attempt_count: int,
    ) -> bool:
        reschedule_result = True if self._db._reschedule_results is None else self._db._reschedule_results.pop(0)
        attempt = {
            "event_id": event_id,
            "intent_id": intent_id,
            "lease_owner": lease_owner,
            "attempt_count": attempt_count,
        }
        self._db.reschedule_mark_attempts.append(attempt)
        self._db.reschedule_job_guards.append(attempt)
        if reschedule_result:
            self._db.rescheduled_jobs.append((event_id, intent_id, reason))
        return reschedule_result


class _FakeMarketTickRepo:
    def __init__(self, db: _FakeDB) -> None:
        self._db = db

    def nearest_around(self, **kwargs: Any) -> dict[str, Any] | None:
        target_id = str(kwargs.get("target_id") or "")
        if target_id == self._db.nearest_hold_target_id:
            assert self._db.nearest_hold_started is not None
            assert self._db.nearest_hold_release is not None
            self._db.nearest_hold_started.set()
            self._db.nearest_hold_release.wait(timeout=1.0)
            return None
        if self._db.nearest_hold_started is not None:
            assert self._db.nearest_hold_started.wait(timeout=1.0)
        return None

    def insert_ticks_returning_rows(self, ticks: Any) -> list[dict[str, Any]]:
        materialized = list(ticks)
        self._db.inserted_ticks.extend(materialized)
        return [asdict(tick) for tick in materialized]


class _FakeRegistry:
    def product_targets_for_market_targets(
        self,
        targets: list[tuple[str, str]],
    ) -> dict[tuple[str, str], tuple[str, str]]:
        return {target: ("Asset", f"asset:{target[1]}") for target in targets if target[0] == "chain_token"}


class _FakeMarketTickCurrent:
    def upsert_current_from_tick(self, tick_row: dict[str, Any]) -> bool:
        return True


class _FakeRadarDirtyTargets:
    def __init__(self, db: _FakeDB) -> None:
        self._db = db

    def enqueue_market_product_targets(self, rows: Any, *, reason: str, now_ms: int) -> int:
        materialized = list(rows)
        self._db.dirty_target_enqueues.append(
            {
                "rows": materialized,
                "reason": reason,
                "now_ms": now_ms,
            }
        )
        return len(materialized)
