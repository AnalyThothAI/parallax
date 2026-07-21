from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from parallax.platform.config.settings import LivePriceGatewayWorkerSettings
from parallax.platform.runtime.worker_base import WorkerBase
from parallax.platform.runtime.worker_result import WorkerResult


@dataclass(frozen=True, slots=True)
class LiveMarketSnapshot:
    target_type: str
    target_id: str
    status: str
    price_usd: float | None
    price_quote: float | None
    quote_symbol: str | None
    price_basis: str
    market_cap_usd: float | None
    liquidity_usd: float | None
    holders: int | None
    volume_24h_usd: float | None
    open_interest_usd: float | None
    observed_at_ms: int | None
    received_at_ms: int | None
    provider: str | None

    def to_payload(self, *, now_ms: int, stale_after_ms: int) -> dict[str, Any]:
        status = self.status
        if status == "live" and self.received_at_ms is not None:
            age_ms = max(0, int(now_ms) - int(self.received_at_ms))
            if age_ms > int(stale_after_ms):
                status = "stale"
        else:
            age_ms = None
        return {
            "status": status,
            "price_usd": self.price_usd,
            "price_quote": self.price_quote,
            "quote_symbol": self.quote_symbol,
            "price_basis": self.price_basis,
            "market_cap_usd": self.market_cap_usd,
            "liquidity_usd": self.liquidity_usd,
            "holders": self.holders,
            "volume_24h_usd": self.volume_24h_usd,
            "open_interest_usd": self.open_interest_usd,
            "observed_at_ms": self.observed_at_ms,
            "received_at_ms": self.received_at_ms,
            "age_ms": age_ms,
            "provider": self.provider,
        }


@dataclass(frozen=True, slots=True)
class LiveMarketEmit:
    payload: dict[str, Any]


class LivePriceGateway(WorkerBase):
    def __init__(
        self,
        *,
        settings: LivePriceGatewayWorkerSettings,
        pool_bundle: Any,
        projection_version: str,
        on_live_market_update: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
        clock: Callable[[], int] | None = None,
        name: str = "live_price_gateway",
        telemetry: Any | None = None,
    ) -> None:
        if pool_bundle is None:
            raise RuntimeError("live_price_gateway_db_required")
        super().__init__(name=name, settings=settings, db=pool_bundle, telemetry=telemetry or object())
        self.projection_version = projection_version
        self.target_limit = settings.target_limit
        self.target_ttl_seconds = settings.target_ttl_seconds
        self.live_stale_after_ms = int(self.target_ttl_seconds * 1000)
        self.on_live_market_update = on_live_market_update
        self.clock = clock or _now_ms
        self._cache: dict[tuple[str, str], LiveMarketSnapshot] = {}

    async def run_once(self, *, now_ms: int | None = None) -> WorkerResult:
        result = await self._run_cycle(now_ms=now_ms)
        return WorkerResult(
            processed=int(result.get("live_market_updates_published") or 0),
            notes={
                "claimed": int(result.get("claimed") or 0),
                "queue_depth": int(result.get("queue_depth") or 0),
                "source_rows_scanned": int(result.get("source_rows_scanned") or 0),
                "targets_loaded": int(result.get("targets_loaded") or 0),
                "rows_written": int(result.get("rows_written") or 0),
                "result": result,
            },
        )

    async def _run_cycle(self, *, now_ms: int | None = None) -> dict[str, Any]:
        received_at_ms = int(now_ms if now_ms is not None else self.clock())
        result = {
            "claimed": 0,
            "queue_depth": 0,
            "source_rows_scanned": 0,
            "targets_loaded": 0,
            "rows_written": 0,
            "targets_selected": 0,
            "live_market_updates_published": 0,
        }
        active_targets = await asyncio.to_thread(self._active_targets, now_ms=received_at_ms)
        result["targets_selected"] = len(active_targets)
        result["targets_loaded"] = len(active_targets)
        market_targets: list[dict[str, Any]] = []
        for row in active_targets:
            target = _market_target_from_row(row)
            if target is not None:
                market_targets.append(target)
        if not market_targets:
            return result
        latest_by_target = await asyncio.to_thread(
            self._latest_market_ticks,
            targets=market_targets,
            now_ms=received_at_ms,
        )
        for target in market_targets:
            key = (target["target_type"], target["target_id"])
            tick = latest_by_target.get(key)
            if tick is None:
                continue
            payload = self._payload_from_tick(tick, target=target, received_at_ms=received_at_ms).payload
            await self._publish(payload)
            result["live_market_updates_published"] += 1
            if self._stop_event.is_set():
                break
        return result

    def snapshot(self, *, target_type: str, target_id: str, now_ms: int | None = None) -> dict[str, Any]:
        observed_now_ms = int(now_ms if now_ms is not None else self.clock())
        key = (str(target_type), str(target_id))
        snapshot = self._cache.get(key)
        if snapshot is None:
            return {
                "target_type": key[0],
                "target_id": key[1],
                "status": "missing",
                "price_usd": None,
                "price_quote": None,
                "quote_symbol": None,
                "price_basis": "unavailable",
                "market_cap_usd": None,
                "liquidity_usd": None,
                "holders": None,
                "volume_24h_usd": None,
                "observed_at_ms": None,
                "received_at_ms": None,
                "age_ms": None,
                "provider": None,
            }
        return {
            "target_type": snapshot.target_type,
            "target_id": snapshot.target_id,
            **snapshot.to_payload(now_ms=observed_now_ms, stale_after_ms=self.live_stale_after_ms),
        }

    def _active_targets(self, *, now_ms: int) -> list[dict[str, Any]]:
        with self.db.worker_session(self.name) as repos:
            targets: Sequence[Mapping[str, Any]] = repos.token_capture_tiers.live_target_rows(limit=self.target_limit)
        return [dict(target) for target in targets]

    def _latest_market_ticks(
        self,
        *,
        targets: list[dict[str, Any]],
        now_ms: int,
    ) -> dict[tuple[str, str], dict[str, Any]]:
        if not targets:
            return {}
        request = [{"target_type": target["target_type"], "target_id": target["target_id"]} for target in targets]
        with self.db.worker_session(self.name) as repos:
            latest_rows = repos.market_ticks.latest_for_targets(
                targets=request,
                max_age_ms=int(self.target_ttl_seconds * 1000),
                now_ms=int(now_ms),
            )
        return {(str(target_type), str(target_id)): dict(row) for (target_type, target_id), row in latest_rows.items()}

    def _payload_from_tick(
        self,
        tick: Mapping[str, Any],
        *,
        target: dict[str, Any],
        received_at_ms: int,
    ) -> LiveMarketEmit:
        source_provider = str(tick.get("source_provider") or "") or None
        price_usd = _float(tick.get("price_usd"))
        quote_symbol = target.get("quote_symbol")
        price_basis = "usd" if price_usd is not None else "unavailable"
        if target["target_type"] == "cex_symbol" and quote_symbol:
            price_basis = "quote_as_usd" if str(quote_symbol).upper() in {"USD", "USDT", "USDC"} else "quote"
        snapshot = LiveMarketSnapshot(
            target_type=str(target["target_type"]),
            target_id=str(target["target_id"]),
            status="live",
            price_usd=price_usd,
            price_quote=price_usd if price_basis in {"quote", "quote_as_usd"} else None,
            quote_symbol=str(quote_symbol).upper() if quote_symbol else None,
            price_basis=price_basis,
            market_cap_usd=_float(tick.get("market_cap_usd")),
            liquidity_usd=_float(tick.get("liquidity_usd")),
            holders=_int(tick.get("holders")),
            volume_24h_usd=_float(tick.get("volume_24h_usd")),
            open_interest_usd=_float(tick.get("open_interest_usd")),
            observed_at_ms=_int(tick.get("observed_at_ms")),
            received_at_ms=_int(tick.get("received_at_ms")) or received_at_ms,
            provider=source_provider,
        )
        return self._store_payload(
            snapshot,
            pricefeed_id=str(tick.get("pricefeed_id") or "") or str(target.get("pricefeed_id") or "") or None,
        )

    def _store_payload(
        self,
        snapshot: LiveMarketSnapshot,
        *,
        pricefeed_id: str | None,
    ) -> LiveMarketEmit:
        self._cache[(snapshot.target_type, snapshot.target_id)] = snapshot
        return LiveMarketEmit(
            payload={
                "type": "live_market_update",
                "provider": snapshot.provider,
                "target_type": snapshot.target_type,
                "target_id": snapshot.target_id,
                "observed_at_ms": snapshot.observed_at_ms,
                "market": {"decision_latest": _decision_latest_payload(snapshot, pricefeed_id=pricefeed_id)},
            },
        )

    async def _publish(self, payload: dict[str, Any]) -> None:
        if self.on_live_market_update is None:
            return
        await self.on_live_market_update(payload)


def _market_target_from_row(row: Mapping[str, Any]) -> dict[str, Any] | None:
    target_type = str(row.get("target_type") or "").strip()
    target_id = str(row.get("target_id") or "").strip()
    if not target_type or not target_id:
        return None
    if target_type in {"chain_token", "cex_symbol"}:
        return {
            "target_type": target_type,
            "target_id": target_id,
            "chain_id": row.get("chain_id"),
            "address": row.get("address"),
            "provider": row.get("provider"),
            "native_market_id": row.get("native_market_id"),
            "quote_symbol": row.get("quote_symbol"),
            "pricefeed_id": row.get("pricefeed_id"),
        }
    return None


def _float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        try:
            return float(value)
        except (OverflowError, ValueError):
            return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _now_ms() -> int:
    return int(time.time() * 1000)


def _decision_latest_payload(
    snapshot: LiveMarketSnapshot,
    *,
    pricefeed_id: str | None,
) -> dict[str, Any]:
    observed_at_ms = int(snapshot.observed_at_ms if snapshot.observed_at_ms is not None else _now_ms())
    return {
        "target_type": snapshot.target_type,
        "target_id": snapshot.target_id,
        "observed_at_ms": observed_at_ms,
        "received_at_ms": snapshot.received_at_ms,
        "source": "decision_latest",
        "provider": snapshot.provider,
        "pricefeed_id": pricefeed_id,
        "price_usd": snapshot.price_usd,
        "price_quote": snapshot.price_quote,
        "quote_symbol": snapshot.quote_symbol,
        "price_basis": snapshot.price_basis,
        "market_cap_usd": snapshot.market_cap_usd,
        "liquidity_usd": snapshot.liquidity_usd,
        "holders": snapshot.holders,
        "volume_24h_usd": snapshot.volume_24h_usd,
        "open_interest_usd": snapshot.open_interest_usd,
        "raw_payload_hash": None,
    }
