"""Async backfill worker for short-lived event-anchor jobs.

``enriched_events`` stores the event-anchor fact lifecycle. The separate
``event_anchor_backfill_jobs`` table stores retry, due-time, and expiry
control state. This worker consumes due jobs, attaches an event-adjacent
tick when one exists, and terminalizes jobs that can no longer produce a
semantically valid event anchor.
"""

from __future__ import annotations

import asyncio
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from decimal import Decimal
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

from parallax.app.runtime.worker_base import WorkerBase
from parallax.app.runtime.worker_result import WorkerResult
from parallax.domains.asset_market.services.event_market_capture import (
    EventMarketCaptureService,
)
from parallax.domains.asset_market.services.market_tick_persistence import MarketTickPersistenceService
from parallax.domains.asset_market.types import EnrichedEventCapture, MarketTick

if TYPE_CHECKING:
    from parallax.app.runtime.providers_wiring import AssetMarketProviders

DEFAULT_BATCH_SIZE = 50
DEFAULT_CONCURRENCY = 8
DEFAULT_MIN_AGE_MS = 250
DEFAULT_ACTIVE_WINDOW_MS = 300_000
DEFAULT_MAX_ANCHOR_LAG_MS = 60_000
DEFAULT_INTERVAL_SECONDS = 1.0
DEFAULT_LEASE_MS = 60_000
TEMPORARY_RETRY_BACKOFF_MS = 10_000
TEMPORARY_REASONS = frozenset({"provider_error", "provider_timeout", "rate_limited"})


@dataclass(frozen=True, slots=True)
class _AttachOutcome:
    row: dict[str, Any]
    tick: MarketTick
    capture: EnrichedEventCapture
    insert_tick: bool


@dataclass(frozen=True, slots=True)
class _TerminalOutcome:
    row: dict[str, Any]
    reason: str
    status: str


@dataclass(frozen=True, slots=True)
class _RescheduleOutcome:
    row: dict[str, Any]
    reason: str
    next_run_at_ms: int


_BackfillOutcome = _AttachOutcome | _TerminalOutcome | _RescheduleOutcome


class _AttachSkipped(Exception):
    pass


class _TerminalSkipped(Exception):
    pass


class EventAnchorBackfillWorker(WorkerBase):
    """Catch up unavailable/pending_backfill enriched events asynchronously."""

    worker_name = "event_anchor_backfill"

    def __init__(
        self,
        *,
        pool_bundle: Any | None = None,
        capture_service: EventMarketCaptureService | None = None,
        providers: Any | None = None,
        dex_quote_market: Any | None = None,
        cex_market: Any | None = None,
        wake_emitter: Any | None = None,
        wake_bus: Any | None = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
        concurrency: int = DEFAULT_CONCURRENCY,
        min_age_ms: int = DEFAULT_MIN_AGE_MS,
        active_window_ms: int = DEFAULT_ACTIVE_WINDOW_MS,
        max_anchor_lag_ms: int = DEFAULT_MAX_ANCHOR_LAG_MS,
        interval_seconds: float | None = None,
        clock: Any | None = None,
        name: str = "event_anchor_backfill",
        settings: Any | None = None,
        db: Any | None = None,
        telemetry: Any | None = None,
        worker_space_contract: Any | None = None,
    ) -> None:
        resolved_settings = _settings(
            settings,
            interval_seconds=interval_seconds,
            batch_size=batch_size,
            concurrency=concurrency,
            min_age_ms=min_age_ms,
            active_window_ms=active_window_ms,
            max_anchor_lag_ms=max_anchor_lag_ms,
        )
        super().__init__(
            name=name,
            settings=resolved_settings,
            db=pool_bundle or db,
            telemetry=telemetry or object(),
            worker_space_contract=worker_space_contract,
        )
        self.clock = clock or _now_ms
        if capture_service is None:
            resolved_providers = providers or SimpleNamespace(
                dex_quote_market=dex_quote_market,
                cex_market=cex_market,
            )
            capture_service = EventMarketCaptureService(
                providers=cast("AssetMarketProviders", resolved_providers),
                now_ms=lambda: int(self.clock()),
            )
        self._capture_service = capture_service
        self.wake_emitter = wake_emitter or wake_bus
        self.batch_size = max(1, int(getattr(resolved_settings, "batch_size", batch_size)))
        self.concurrency = max(1, int(getattr(resolved_settings, "concurrency", concurrency)))
        self.max_attempts = max(1, int(getattr(resolved_settings, "max_attempts", 3)))
        self.min_age_ms = max(0, int(getattr(resolved_settings, "min_age_ms", min_age_ms)))
        self.lease_ms = max(1, int(getattr(resolved_settings, "lease_ms", DEFAULT_LEASE_MS)))
        self.active_window_ms = max(1, int(getattr(resolved_settings, "active_window_ms", active_window_ms)))
        self.max_anchor_lag_ms = max(1, int(getattr(resolved_settings, "max_anchor_lag_ms", max_anchor_lag_ms)))

    async def run_once(self) -> WorkerResult:
        now_ms = int(self.clock())
        runtime_context = self._runtime_context()
        stale_jobs = await asyncio.to_thread(self._expire_stale_jobs, now_ms=now_ms, runtime_context=runtime_context)
        stale_terminal = int(stale_jobs["expired"]) + int(stale_jobs["failed"])
        stale_rescheduled = int(stale_jobs["rescheduled"])
        rows = await asyncio.to_thread(self._claim_due_jobs, now_ms=now_ms, runtime_context=runtime_context)
        runtime_context.mark_claimed(count=len(rows))
        if not rows:
            return WorkerResult(
                processed=0,
                skipped=0,
                notes={
                    "pending_selected": 0,
                    "claimed": 0,
                    "expired_jobs": int(stale_jobs["expired"]),
                    "ticks_inserted": 0,
                    "captures_attached": 0,
                    "terminal_failures": stale_terminal,
                    "rescheduled_jobs": stale_rescheduled,
                },
            )

        semaphore = asyncio.Semaphore(self.concurrency)
        outcomes = await asyncio.gather(*(self._capture_one(row, semaphore, now_ms=now_ms) for row in rows))

        attaches: list[_AttachOutcome] = []
        terminals: list[_TerminalOutcome] = []
        reschedules: list[_RescheduleOutcome] = []
        skipped_reasons: Counter[str] = Counter()
        for outcome in outcomes:
            if isinstance(outcome, _AttachOutcome):
                attaches.append(outcome)
                continue
            if isinstance(outcome, _RescheduleOutcome):
                reschedules.append(outcome)
                skipped_reasons[outcome.reason] += 1
                continue
            terminals.append(outcome)
            skipped_reasons[outcome.reason] += 1

        inserted, attached_ticks, terminal_count, rescheduled_count = await asyncio.to_thread(
            self._persist,
            attaches=attaches,
            terminals=terminals,
            reschedules=reschedules,
            now_ms=now_ms,
            runtime_context=runtime_context,
        )
        for tick in attached_ticks:
            _emit_wake(self.wake_emitter, target_type=tick.target_type, target_id=tick.target_id)
        attached = len(attached_ticks)
        return WorkerResult(
            processed=attached,
            skipped=len(rows) - attached - rescheduled_count - terminal_count,
            notes={
                "pending_selected": len(rows),
                "claimed": len(rows),
                "expired_jobs": int(stale_jobs["expired"]),
                "ticks_inserted": inserted,
                "captures_attached": attached,
                "terminal_failures": stale_terminal + terminal_count,
                "rescheduled_jobs": stale_rescheduled + rescheduled_count,
                "skipped_reasons": dict(sorted(skipped_reasons.items())),
            },
        )

    async def _capture_one(
        self,
        row: Mapping[str, Any],
        semaphore: asyncio.Semaphore,
        *,
        now_ms: int,
    ) -> _BackfillOutcome:
        context = self._runtime_context()
        context.mark_claimed(count=1)
        resolution = _resolution_from_row(row)
        async with semaphore:
            existing = await asyncio.to_thread(
                self._capture_existing_tick,
                row=row,
                now_ms=now_ms,
                runtime_context=context,
            )
            if existing is not None:
                return existing
            if abs(now_ms - int(row["t_event_ms"])) > self.max_anchor_lag_ms:
                return _TerminalOutcome(row=dict(row), reason="backfill_expired", status="expired")
            return await asyncio.to_thread(
                self._capture_provider_quote,
                row,
                resolution,
                now_ms,
                context,
            )

    def _capture_provider_quote(
        self,
        row: Mapping[str, Any],
        resolution: Mapping[str, Any],
        now_ms: int,
        runtime_context: Any | None = None,
    ) -> _BackfillOutcome:
        context = runtime_context or self._runtime_context()
        with context.provider_io():
            result = self._capture_service.capture_backfill_quote(
                event_id=str(row["event_id"]),
                intent_id=str(row["intent_id"]),
                resolution_id=str(row["resolution_id"]),
                resolution=resolution,
                event_ms=int(row["t_event_ms"]),
            )
        if result.tick is not None:
            capture = replace(
                result.capture,
                capture_method="tier3_inline",
                capture_reason="async_backfill",
                event_id=str(row["event_id"]),
                intent_id=str(row["intent_id"]),
                resolution_id=str(row["resolution_id"]),
            )
            if capture.tick_lag_ms is not None and capture.tick_lag_ms <= self.max_anchor_lag_ms:
                return _AttachOutcome(row=dict(row), tick=result.tick, capture=capture, insert_tick=True)
            return _TerminalOutcome(row=dict(row), reason="backfill_expired", status="expired")

        reason = result.capture.capture_reason or "unknown"
        if self._should_reschedule(row=row, reason=reason, now_ms=now_ms):
            return _RescheduleOutcome(
                row=dict(row),
                reason=reason,
                next_run_at_ms=min(int(row["active_until_ms"]), now_ms + TEMPORARY_RETRY_BACKOFF_MS),
            )
        return _TerminalOutcome(row=dict(row), reason=reason, status="failed")

    def _capture_existing_tick(
        self,
        *,
        row: Mapping[str, Any],
        now_ms: int,
        runtime_context: Any | None = None,
    ) -> _AttachOutcome | None:
        context = runtime_context or self._runtime_context()
        with context.payload_session() as repos:
            tick_row = repos.market_ticks.nearest_around(
                target_type=str(row["target_type"]),
                target_id=str(row["target_id"]),
                at_ms=int(row["t_event_ms"]),
                max_lag_ms=self.max_anchor_lag_ms,
            )
        if tick_row is None:
            return None
        tick = _market_tick_from_row(tick_row)
        capture = EnrichedEventCapture(
            event_id=str(row["event_id"]),
            intent_id=str(row["intent_id"]),
            resolution_id=str(row["resolution_id"]),
            target_type=cast(Any, str(row["target_type"])),
            target_id=str(row["target_id"]),
            t_event_ms=int(row["t_event_ms"]),
            tick_observed_at_ms=tick.observed_at_ms,
            tick_id=tick.tick_id,
            tick_lag_ms=abs(tick.observed_at_ms - int(row["t_event_ms"])),
            capture_method=tick.source_tier,
            capture_reason="async_backfill",
            created_at_ms=now_ms,
        )
        return _AttachOutcome(row=dict(row), tick=tick, capture=capture, insert_tick=False)

    def _should_reschedule(self, *, row: Mapping[str, Any], reason: str, now_ms: int) -> bool:
        if reason not in TEMPORARY_REASONS:
            return False
        if int(row.get("attempt_count") or 0) >= self.max_attempts:
            return False
        if int(row["active_until_ms"]) <= now_ms:
            return False
        return abs(now_ms - int(row["t_event_ms"])) <= self.max_anchor_lag_ms

    def _expire_stale_jobs(self, *, now_ms: int, runtime_context: Any | None = None) -> dict[str, int]:
        context = runtime_context or self._runtime_context()
        with context.claim_session() as repos:
            summary = repos.event_anchor_jobs.expire_stale(
                limit=self.batch_size,
                now_ms=now_ms,
                max_attempts=self.max_attempts,
                retry_backoff_ms=TEMPORARY_RETRY_BACKOFF_MS,
            )
            terminal_rows = [dict(row) for row in summary.get("terminal_rows") or ()]
            for row in terminal_rows:
                repos.enriched_events.mark_backfill_terminal(
                    event_id=str(row["event_id"]),
                    intent_id=str(row["intent_id"]),
                    reason=_terminal_reason(row),
                )
            expired = int(summary.get("expired") or 0)
            failed = int(summary.get("failed") or 0)
            rescheduled = int(summary.get("rescheduled") or 0)
            if terminal_rows or rescheduled:
                _commit_if_supported(repos)
            return {"expired": expired, "failed": failed, "rescheduled": rescheduled}

    def _claim_due_jobs(self, *, now_ms: int, runtime_context: Any | None = None) -> list[dict[str, Any]]:
        context = runtime_context or self._runtime_context()
        with context.claim_session() as repos:
            rows = repos.event_anchor_jobs.claim_due(
                limit=self.batch_size,
                now_ms=now_ms,
                min_age_ms=self.min_age_ms,
                lease_owner=self.name,
                lease_ms=self.lease_ms,
            )
        return [dict(row) for row in rows]

    def _persist(
        self,
        *,
        attaches: Sequence[_AttachOutcome],
        terminals: Sequence[_TerminalOutcome],
        reschedules: Sequence[_RescheduleOutcome],
        now_ms: int,
        runtime_context: Any | None = None,
    ) -> tuple[int, list[MarketTick], int, int]:
        if not attaches and not terminals and not reschedules:
            return 0, [], 0, 0
        context = runtime_context or self._runtime_context()
        with context.transaction_session() as repos:
            persistence = MarketTickPersistenceService(repos)
            inserted = 0
            attached_ticks: list[MarketTick] = []
            for attach in attaches:
                try:
                    with repos.transaction():
                        tick_inserted = 0
                        if attach.insert_tick:
                            tick_result = persistence.insert_ticks_and_enqueue_current_dirty(
                                [attach.tick],
                                reason="event_anchor_backfill_attached",
                                now_ms=now_ms,
                            )
                            tick_inserted = tick_result.inserted
                        if not repos.enriched_events.attach_backfill_capture(attach.capture):
                            raise _AttachSkipped
                        marked_done = repos.event_anchor_jobs.mark_done(
                            event_id=str(attach.row["event_id"]),
                            intent_id=str(attach.row["intent_id"]),
                            now_ms=now_ms,
                            lease_owner=_lease_owner(attach.row),
                            attempt_count=_attempt_count(attach.row),
                        )
                        if not marked_done:
                            raise _AttachSkipped
                except _AttachSkipped:
                    continue
                inserted += tick_inserted
                attached_ticks.append(attach.tick)
            terminal_count = 0
            for terminal in terminals:
                try:
                    with repos.transaction():
                        if not repos.event_anchor_jobs.mark_terminal(
                            event_id=str(terminal.row["event_id"]),
                            intent_id=str(terminal.row["intent_id"]),
                            status=terminal.status,
                            reason=terminal.reason,
                            now_ms=now_ms,
                            lease_owner=_lease_owner(terminal.row),
                            attempt_count=_attempt_count(terminal.row),
                        ):
                            raise _TerminalSkipped
                        repos.enriched_events.mark_backfill_terminal(
                            event_id=str(terminal.row["event_id"]),
                            intent_id=str(terminal.row["intent_id"]),
                            reason=terminal.reason,
                        )
                except _TerminalSkipped:
                    continue
                terminal_count += 1
            rescheduled_count = 0
            for reschedule in reschedules:
                if repos.event_anchor_jobs.reschedule(
                    event_id=str(reschedule.row["event_id"]),
                    intent_id=str(reschedule.row["intent_id"]),
                    reason=reschedule.reason,
                    now_ms=now_ms,
                    next_run_at_ms=reschedule.next_run_at_ms,
                    lease_owner=_lease_owner(reschedule.row),
                    attempt_count=_attempt_count(reschedule.row),
                ):
                    rescheduled_count += 1
        return inserted, attached_ticks, terminal_count, rescheduled_count


def _resolution_from_row(row: Mapping[str, Any]) -> dict[str, Any]:
    target_type = str(row["target_type"])
    target_id = str(row["target_id"])
    resolution: dict[str, Any] = {"target_type": target_type, "target_id": target_id}
    if target_type == "chain_token":
        chain_id, _, token_address = target_id.rpartition(":")
        if chain_id:
            resolution["chain_id"] = chain_id.strip()
            resolution["token_address"] = token_address.strip()
    elif target_type == "cex_symbol":
        exchange, _, instrument = target_id.partition(":")
        if exchange:
            resolution["exchange"] = exchange.strip()
            resolution["instrument"] = instrument.strip()
    return resolution


def _emit_wake(wake_emitter: Any, *, target_type: str, target_id: str) -> None:
    if wake_emitter is None:
        return
    notify = getattr(wake_emitter, "notify_market_tick_written", None)
    if notify is None:
        return
    notify(target_type=target_type, target_id=target_id)


def _market_tick_from_row(row: Mapping[str, Any]) -> MarketTick:
    return MarketTick(
        tick_id=str(row["tick_id"]),
        target_type=cast(Any, str(row["target_type"])),
        target_id=str(row["target_id"]),
        chain=_str_or_none(row.get("chain")),
        token_address=_str_or_none(row.get("token_address")),
        exchange=_str_or_none(row.get("exchange")),
        instrument=_str_or_none(row.get("instrument")),
        pricefeed_id=_str_or_none(row.get("pricefeed_id")),
        source_tier=cast(Any, str(row["source_tier"])),
        source_provider=cast(Any, str(row["source_provider"])),
        observed_at_ms=int(row["observed_at_ms"]),
        received_at_ms=int(row["received_at_ms"]),
        price_usd=_decimal(row["price_usd"]),
        liquidity_usd=_decimal_or_none(row.get("liquidity_usd")),
        volume_24h_usd=_decimal_or_none(row.get("volume_24h_usd")),
        market_cap_usd=_decimal_or_none(row.get("market_cap_usd")),
        holders=_int_or_none(row.get("holders")),
        created_at_ms=int(row["created_at_ms"]),
        open_interest_usd=_decimal_or_none(row.get("open_interest_usd")),
        raw_payload_json=dict(row.get("raw_payload_json") or {}),
    )


def _terminal_reason(row: Mapping[str, Any]) -> str:
    reason = str(row.get("last_reason") or "").strip()
    if reason:
        return reason
    if str(row.get("status") or "") == "failed":
        return "lease_expired_max_attempts"
    return "backfill_expired"


def _lease_owner(row: Mapping[str, Any]) -> str:
    lease_owner = str(row.get("lease_owner") or "").strip()
    if not lease_owner:
        raise ValueError("event_anchor_backfill_claim_lease_owner_required")
    return lease_owner


def _attempt_count(row: Mapping[str, Any]) -> int:
    return int(row.get("attempt_count") or 0)


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _decimal(value: Any) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    return _decimal(value)


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _commit_if_supported(repos: Any) -> None:
    conn = getattr(repos, "conn", None)
    commit = getattr(conn, "commit", None)
    if callable(commit):
        commit()
        return
    commit = getattr(repos, "commit", None)
    if callable(commit):
        commit()


def _settings(
    settings: Any | None,
    *,
    interval_seconds: float | None,
    batch_size: int,
    concurrency: int,
    min_age_ms: int,
    active_window_ms: int,
    max_anchor_lag_ms: int,
) -> Any:
    if settings is None:
        return SimpleNamespace(
            enabled=True,
            interval_seconds=interval_seconds if interval_seconds is not None else DEFAULT_INTERVAL_SECONDS,
            soft_timeout_seconds=120.0,
            hard_timeout_seconds=180.0,
            batch_size=batch_size,
            concurrency=concurrency,
            lease_ms=DEFAULT_LEASE_MS,
            min_age_ms=min_age_ms,
            active_window_ms=active_window_ms,
            max_anchor_lag_ms=max_anchor_lag_ms,
        )
    if interval_seconds is None:
        return settings
    try:
        settings.interval_seconds = interval_seconds
        return settings
    except Exception:
        values = dict(getattr(settings, "__dict__", {}))
        values["interval_seconds"] = interval_seconds
        return SimpleNamespace(**values)


def _now_ms() -> int:
    return int(time.time() * 1000)


__all__ = ["EventAnchorBackfillWorker"]
