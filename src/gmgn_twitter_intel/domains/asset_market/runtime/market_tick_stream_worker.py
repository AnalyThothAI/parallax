from __future__ import annotations

import inspect
import time
from collections.abc import AsyncIterator, Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace
from typing import Any

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.domains.asset_market.providers import DexMarketFactUpdate, DexMarketStreamTarget
from gmgn_twitter_intel.domains.asset_market.types import MarketTick, market_tick_id

SOURCE_TIER = "tier1_ws"
SOURCE_PROVIDER = "okx_dex_ws"
DEFAULT_SUBSCRIPTION_LIMIT = 50


class MarketTickStreamWorker(WorkerBase):
    worker_name = "market_tick_stream"

    def __init__(
        self,
        *,
        pool_bundle: Any | None = None,
        stream_dex_market: Any | None = None,
        wake_emitter: Any | None = None,
        wake_bus: Any | None = None,
        subscription_limit: int = DEFAULT_SUBSCRIPTION_LIMIT,
        interval_seconds: float | None = None,
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

        ticks, skipped_frames = await self._collect_ticks(targets)
        inserted = 0
        if ticks:
            inserted = self._insert_ticks(ticks)
            for tick in ticks:
                _emit_wake(self.wake_emitter, target_type=tick.target_type, target_id=tick.target_id)

        return WorkerResult(
            processed=inserted,
            skipped=skipped_targets + skipped_frames,
            notes={
                "targets_selected": len(rows),
                "stream_targets": len(targets),
                "ticks_attempted": len(ticks),
                "ticks_inserted": inserted,
                "invalid_frames": skipped_frames,
            },
        )

    def _list_tier1_rows(self) -> list[dict[str, Any]]:
        with self.db.worker_session(self.name) as repos:
            rows = repos.token_capture_tiers.list_by_tier(1, limit=self.subscription_limit)
        return [dict(row) for row in rows]

    async def _collect_ticks(self, targets: list[DexMarketStreamTarget]) -> tuple[list[MarketTick], int]:
        target_by_key = {_target_key(target.chain_id, target.address): target for target in targets}
        ticks: list[MarketTick] = []
        skipped = 0
        async for update in _stream_price_info(self.stream_dex_market, targets):
            target = target_by_key.get(_target_key(update.chain_id, update.address))
            if target is None:
                skipped += 1
                continue
            tick = _tick_from_update(update, target=target, received_at_ms=int(self.clock()))
            if tick is None:
                skipped += 1
                continue
            ticks.append(tick)
        return ticks, skipped

    def _insert_ticks(self, ticks: Iterable[MarketTick]) -> int:
        materialized = list(ticks)
        with self.db.worker_session(self.name) as repos:
            inserted = int(repos.market_ticks.insert_ticks(materialized))
            _commit_if_supported(repos)
        return inserted


@dataclass(frozen=True, slots=True)
class _TargetParts:
    chain_id: str
    address: str


def _stream_targets(rows: list[Mapping[str, Any]], *, limit: int) -> tuple[list[DexMarketStreamTarget], int]:
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
    parsed_chain_id, parsed_address = target_id.split(":", 1)
    parsed_chain_id = parsed_chain_id.strip()
    parsed_address = parsed_address.strip()
    if not parsed_chain_id or not parsed_address:
        return None
    return _TargetParts(chain_id=parsed_chain_id, address=parsed_address)


async def _stream_price_info(
    stream_dex_market: Any,
    targets: list[DexMarketStreamTarget],
) -> AsyncIterator[DexMarketFactUpdate]:
    stream = stream_dex_market.stream_price_info(targets)
    if inspect.isawaitable(stream):
        stream = await stream
    async for update in stream:
        yield update


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
        created_at_ms=received_at_ms,
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
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _target_key(chain_id: str, address: str) -> tuple[str, str]:
    return (str(chain_id).strip(), str(address).strip().lower())


def _emit_wake(wake_emitter: Any, *, target_type: str, target_id: str) -> None:
    if wake_emitter is None:
        return
    notify_market_observation_written = getattr(wake_emitter, "notify_market_observation_written", None)
    if callable(notify_market_observation_written):
        notify_market_observation_written(target_type=target_type, target_id=target_id)
        return
    notify = getattr(wake_emitter, "notify", None)
    if callable(notify):
        notify("market_tick_written")
        return
    emit = getattr(wake_emitter, "emit", None)
    if callable(emit):
        emit("market_tick_written")


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
    subscription_limit: int,
) -> Any:
    if settings is None:
        return SimpleNamespace(
            enabled=True,
            interval_seconds=interval_seconds if interval_seconds is not None else 5.0,
            timeout_seconds=120.0,
            subscription_limit=subscription_limit,
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
