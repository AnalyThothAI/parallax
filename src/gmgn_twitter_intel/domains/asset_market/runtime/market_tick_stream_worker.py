from __future__ import annotations

import asyncio
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace
from typing import Any

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.domains.asset_market.providers import (
    DexMarketFactUpdate,
    DexMarketStreamProvider,
    DexMarketStreamTarget,
)
from gmgn_twitter_intel.domains.asset_market.services.market_tick_persistence import MarketTickPersistenceService
from gmgn_twitter_intel.domains.asset_market.types import (
    MarketTick,
    MarketTickSourceProvider,
    MarketTickSourceTier,
    market_tick_id,
)

SOURCE_TIER: MarketTickSourceTier = "tier1_ws"
SOURCE_PROVIDER: MarketTickSourceProvider = "okx_dex_ws"
DEFAULT_SUBSCRIPTION_LIMIT = 50
DEFAULT_STREAM_CYCLE_SECONDS = 30.0


class MarketTickStreamWorker(WorkerBase):
    worker_name = "market_tick_stream"

    def __init__(
        self,
        *,
        pool_bundle: Any | None = None,
        stream_dex_market: DexMarketStreamProvider | None = None,
        wake_emitter: Any | None = None,
        wake_bus: Any | None = None,
        subscription_limit: int = DEFAULT_SUBSCRIPTION_LIMIT,
        interval_seconds: float | None = None,
        stream_cycle_seconds: float | None = None,
        clock: Any | None = None,
        name: str = "market_tick_stream",
        settings: Any | None = None,
        db: Any | None = None,
        telemetry: Any | None = None,
    ) -> None:
        resolved_settings = _settings(
            settings,
            interval_seconds=interval_seconds,
            subscription_limit=subscription_limit,
            stream_cycle_seconds=stream_cycle_seconds,
        )
        super().__init__(
            name=name,
            settings=resolved_settings,
            db=pool_bundle or db,
            telemetry=telemetry or object(),
        )
        self.stream_dex_market = stream_dex_market
        self.wake_emitter = wake_emitter or wake_bus
        self.subscription_limit = max(
            0,
            int(getattr(resolved_settings, "subscription_limit", subscription_limit)),
        )
        self.stream_cycle_seconds = _stream_cycle_seconds(
            resolved_settings,
            fallback_interval_seconds=self.interval_seconds,
        )
        self.clock = clock or _now_ms

    async def run_once(self) -> WorkerResult:
        rows = self._list_tier1_rows()
        targets, skipped_targets = _stream_targets(rows, limit=self.subscription_limit)
        if self.stream_dex_market is None:
            return WorkerResult(
                skipped=len(targets) + skipped_targets,
                notes={
                    "reason": "stream_provider_unavailable",
                    "targets_selected": len(rows),
                    "stream_targets": len(targets),
                },
            )
        if not targets:
            return WorkerResult(
                skipped=skipped_targets,
                notes={"targets_selected": len(rows), "stream_targets": 0},
            )

        stream_dex_market = self.stream_dex_market
        stream_result = await self._stream_and_persist_ticks(targets, stream_dex_market=stream_dex_market)
        notes = {
            "targets_selected": len(rows),
            "stream_targets": len(targets),
            "ticks_attempted": stream_result.attempted,
            "ticks_inserted": stream_result.inserted,
            "invalid_frames": stream_result.skipped,
        }
        if stream_result.degraded:
            provider_state = stream_result.provider_state or {}
            notes.update(
                {
                    "degraded": True,
                    "provider_state": provider_state.get("state"),
                    "provider_state_payload": provider_state,
                    "failure_category": stream_result.failure_category,
                }
            )

        return WorkerResult(
            processed=stream_result.inserted,
            skipped=skipped_targets + stream_result.skipped,
            notes=notes,
        )

    def _list_tier1_rows(self) -> list[dict[str, Any]]:
        with self.db.worker_session(self.name) as repos:
            rows = repos.token_capture_tiers.list_by_tier(1, limit=self.subscription_limit)
        return [dict(row) for row in rows]

    async def _stream_and_persist_ticks(
        self,
        targets: list[DexMarketStreamTarget],
        *,
        stream_dex_market: DexMarketStreamProvider,
    ) -> _StreamPersistResult:
        target_by_key = {_target_key(target.chain_id, target.address): target for target in targets}
        ticks: list[MarketTick] = []
        skipped = 0
        inserted: int | None = None
        degraded_result: _StreamPersistResult | None = None
        try:
            await asyncio.wait_for(
                stream_dex_market.replace_subscriptions(targets),
                timeout=max(0.001, self.stream_cycle_seconds),
            )
            iterator = stream_dex_market.iter_price_info().__aiter__()
            deadline = time.monotonic() + self.stream_cycle_seconds
            try:
                while True:
                    remaining_seconds = deadline - time.monotonic()
                    if remaining_seconds <= 0:
                        break
                    try:
                        update = await asyncio.wait_for(iterator.__anext__(), timeout=remaining_seconds)
                    except (TimeoutError, StopAsyncIteration):
                        break
                    target = target_by_key.get(_target_key(update.chain_id, update.address))
                    if target is None:
                        skipped += 1
                        continue
                    tick = _tick_from_update(update, target=target, received_at_ms=int(self.clock()))
                    if tick is None:
                        skipped += 1
                        continue
                    ticks.append(tick)
            except Exception as exc:
                inserted = self._persist_ticks(ticks)
                degraded_result = _degraded_stream_result(
                    inserted=inserted,
                    attempted=len(ticks),
                    skipped=skipped,
                    stream_dex_market=stream_dex_market,
                    exc=exc,
                )
            finally:
                close = getattr(iterator, "aclose", None)
                if close is not None:
                    await close()
            if degraded_result is not None:
                return degraded_result
        except Exception as exc:
            if inserted is None:
                inserted = self._persist_ticks(ticks)
            return _degraded_stream_result(
                inserted=inserted,
                attempted=len(ticks),
                skipped=skipped,
                stream_dex_market=stream_dex_market,
                exc=exc,
            )
        inserted = self._persist_ticks(ticks)
        return _StreamPersistResult(inserted=inserted, attempted=len(ticks), skipped=skipped)

    def _persist_ticks(self, ticks: Iterable[MarketTick]) -> int:
        materialized = list(ticks)
        if not materialized:
            return 0
        with self.db.worker_transaction(self.name) as repos:
            result = MarketTickPersistenceService(repos).insert_ticks_and_enqueue_current_dirty(
                materialized,
                reason="market_tick_written",
                now_ms=int(self.clock()),
            )
        for target_type, target_id in result.changed_targets:
            _emit_wake(self.wake_emitter, target_type=target_type, target_id=target_id)
        return result.inserted


@dataclass(frozen=True, slots=True)
class _TargetParts:
    chain_id: str
    address: str


@dataclass(frozen=True, slots=True)
class _StreamPersistResult:
    inserted: int
    attempted: int
    skipped: int
    degraded: bool = False
    provider_state: dict[str, Any] | None = None
    failure_category: str | None = None


def _degraded_stream_result(
    *,
    inserted: int,
    attempted: int,
    skipped: int,
    stream_dex_market: DexMarketStreamProvider,
    exc: BaseException,
) -> _StreamPersistResult:
    provider_state = _provider_connection_state_payload(stream_dex_market)
    return _StreamPersistResult(
        inserted=inserted,
        attempted=attempted,
        skipped=skipped,
        degraded=True,
        provider_state=provider_state,
        failure_category=_provider_failure_category(provider_state, exc),
    )


def _provider_connection_state_payload(provider: Any) -> dict[str, Any]:
    payload = getattr(provider, "connection_state_payload", None)
    if not callable(payload):
        return {}
    try:
        value = payload()
    except Exception as exc:
        return {"state": "unknown", "last_error_category": type(exc).__name__}
    return value if isinstance(value, dict) else {}


def _provider_failure_category(provider_state: Mapping[str, Any], exc: BaseException) -> str:
    category = provider_state.get("last_error_category") if isinstance(provider_state, Mapping) else None
    if category:
        return str(category)
    if isinstance(exc, TimeoutError):
        return "timeout"
    return type(exc).__name__


def _stream_targets(rows: Sequence[Mapping[str, Any]], *, limit: int) -> tuple[list[DexMarketStreamTarget], int]:
    targets: list[DexMarketStreamTarget] = []
    skipped = 0
    for row in rows[: max(0, int(limit))]:
        target_type = str(row.get("target_type") or "").strip()
        if target_type != "chain_token":
            skipped += 1
            continue
        target_id = str(row.get("target_id") or "").strip()
        parts = _chain_token_parts(row, target_id=target_id)
        if parts is None:
            skipped += 1
            continue
        targets.append(
            DexMarketStreamTarget(
                chain_id=parts.chain_id,
                address=parts.address,
                subject_type="chain_token",
                subject_id=target_id,
                pricefeed_id=str(row.get("pricefeed_id") or "") or None,
            )
        )
    return targets, skipped


def _chain_token_parts(row: Mapping[str, Any], *, target_id: str) -> _TargetParts | None:
    chain_id = str(row.get("chain_id") or "").strip()
    address = str(row.get("address") or "").strip()
    if chain_id and address:
        return _TargetParts(chain_id=chain_id, address=address)
    if ":" not in target_id:
        return None
    parsed_chain_id, parsed_address = target_id.rsplit(":", 1)
    parsed_chain_id = parsed_chain_id.strip()
    parsed_address = parsed_address.strip()
    if not parsed_chain_id or not parsed_address:
        return None
    return _TargetParts(chain_id=parsed_chain_id, address=parsed_address)


def _tick_from_update(
    update: DexMarketFactUpdate,
    *,
    target: DexMarketStreamTarget,
    received_at_ms: int,
) -> MarketTick | None:
    price_usd = _positive_decimal(update.price_usd)
    if price_usd is None:
        return None
    observed_at_ms = int(update.observed_at_ms)
    return MarketTick(
        tick_id=market_tick_id(
            target_type=target.subject_type,
            target_id=target.subject_id,
            source_provider=SOURCE_PROVIDER,
            observed_at_ms=observed_at_ms,
        ),
        target_type="chain_token",
        target_id=target.subject_id,
        chain=target.chain_id,
        token_address=target.address,
        exchange=None,
        instrument=None,
        pricefeed_id=target.pricefeed_id,
        source_tier=SOURCE_TIER,
        source_provider=SOURCE_PROVIDER,
        observed_at_ms=observed_at_ms,
        received_at_ms=received_at_ms,
        price_usd=price_usd,
        liquidity_usd=_decimal_or_none(update.liquidity_usd),
        volume_24h_usd=_decimal_or_none(update.volume_24h_usd),
        market_cap_usd=_decimal_or_none(update.market_cap_usd),
        holders=_int_or_none(update.holders),
        created_at_ms=received_at_ms,
        open_interest_usd=_decimal_or_none(update.open_interest_usd),
        raw_payload_json=update.raw or {},
    )


def _positive_decimal(value: Any) -> Decimal | None:
    result = _decimal_or_none(value)
    if result is None or result <= 0:
        return None
    return result


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not result.is_finite():
        return None
    return result


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _target_key(chain_id: str, address: str) -> tuple[str, str]:
    return (str(chain_id).strip(), str(address).strip().lower())


def _emit_wake(wake_emitter: Any, *, target_type: str, target_id: str) -> None:
    if wake_emitter is None:
        return
    wake_emitter.notify_market_tick_written(target_type=target_type, target_id=target_id)


def _settings(
    settings: Any | None,
    *,
    interval_seconds: float | None,
    subscription_limit: int,
    stream_cycle_seconds: float | None,
) -> Any:
    if settings is None:
        return SimpleNamespace(
            enabled=True,
            interval_seconds=interval_seconds if interval_seconds is not None else 5.0,
            soft_timeout_seconds=120.0,
            hard_timeout_seconds=180.0,
            subscription_limit=subscription_limit,
            stream_cycle_seconds=stream_cycle_seconds,
        )
    if interval_seconds is None and stream_cycle_seconds is None:
        return settings
    try:
        if interval_seconds is not None:
            settings.interval_seconds = interval_seconds
        if stream_cycle_seconds is not None:
            settings.stream_cycle_seconds = stream_cycle_seconds
        return settings
    except Exception:
        values = dict(getattr(settings, "__dict__", {}))
        if interval_seconds is not None:
            values["interval_seconds"] = interval_seconds
        if stream_cycle_seconds is not None:
            values["stream_cycle_seconds"] = stream_cycle_seconds
        return SimpleNamespace(**values)


def _stream_cycle_seconds(settings: Any, *, fallback_interval_seconds: float) -> float:
    configured = getattr(settings, "stream_cycle_seconds", None)
    if configured is not None:
        return max(0.001, float(configured))
    return max(0.001, min(float(fallback_interval_seconds), DEFAULT_STREAM_CYCLE_SECONDS))


def _now_ms() -> int:
    return int(time.time() * 1000)
