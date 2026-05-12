from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any

from loguru import logger

from gmgn_twitter_intel.domains.asset_market.market_field_facts import PROVIDER_OKX_DEX_WS_PRICE_INFO
from gmgn_twitter_intel.domains.asset_market.providers import CexTicker, DexMarketFactUpdate, DexMarketStreamTarget


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
            "observed_at_ms": self.observed_at_ms,
            "received_at_ms": self.received_at_ms,
            "age_ms": age_ms,
            "provider": self.provider,
        }


class LivePriceGateway:
    def __init__(
        self,
        *,
        repository_session: Callable[[], AbstractContextManager[Any]],
        projection_version: str,
        subscription_limit: int,
        hot_target_ttl_seconds: float,
        stream_provider: Any | None = None,
        cex_market: Any | None = None,
        cex_poll_interval_seconds: float = 30.0,
        reconnect_delay_seconds: float = 3.0,
        on_live_market_update: Callable[[dict[str, Any]], Any] | None = None,
    ) -> None:
        self.stream_provider = stream_provider
        self.cex_market = cex_market
        self.repository_session = repository_session
        self.projection_version = projection_version
        self.subscription_limit = max(1, int(subscription_limit))
        self.hot_target_ttl_seconds = max(1.0, float(hot_target_ttl_seconds))
        self.live_stale_after_ms = int(self.hot_target_ttl_seconds * 1000)
        self.cex_poll_interval_seconds = max(1.0, float(cex_poll_interval_seconds))
        self.reconnect_delay_seconds = max(0.1, float(reconnect_delay_seconds))
        self.on_live_market_update = on_live_market_update
        self.last_started_at_ms: int | None = None
        self.last_run_at_ms: int | None = None
        self.last_result: dict[str, Any] | None = None
        self.last_error: str | None = None
        self._cache: dict[tuple[str, str], LiveMarketSnapshot] = {}
        self._stopped = False

    async def run(self) -> None:
        while not self._stopped:
            try:
                result = await self.run_once()
            except Exception as exc:  # pragma: no cover - watchdog path
                self.last_error = str(exc)
                logger.exception(f"live price gateway failed: {exc}")
                await asyncio.sleep(self.reconnect_delay_seconds)
                continue
            if self._stopped:
                break
            delay_seconds = (
                self.reconnect_delay_seconds
                if self.stream_provider is not None and int(result.get("dex_targets_selected") or 0) > 0
                else self.cex_poll_interval_seconds
            )
            await self._sleep(delay_seconds)

    async def run_once(self, *, now_ms: int | None = None) -> dict[str, Any]:
        received_at_ms = int(now_ms if now_ms is not None else _now_ms())
        self.last_started_at_ms = received_at_ms
        self.last_error = None
        result = {
            "targets_selected": 0,
            "dex_targets_selected": 0,
            "cex_targets_selected": 0,
            "updates_received": 0,
            "cex_quotes_received": 0,
            "observations_written": 0,
            "live_market_updates_published": 0,
        }
        targets = await asyncio.to_thread(self._active_targets, now_ms=received_at_ms)
        result["targets_selected"] = len(targets)
        dex_targets = [target for target in targets if _is_dex_target(target)]
        cex_targets = [target for target in targets if _is_cex_target(target)]
        result["dex_targets_selected"] = len(dex_targets)
        result["cex_targets_selected"] = len(cex_targets)
        cex_payloads = await asyncio.to_thread(self._poll_cex, cex_targets, received_at_ms=received_at_ms)
        for payload in cex_payloads:
            result["cex_quotes_received"] += 1
            await self._publish(payload)
            result["live_market_updates_published"] += 1
        async for payload in self._stream_dex(dex_targets, received_at_ms=received_at_ms):
            result["updates_received"] += 1
            await self._publish(payload)
            result["live_market_updates_published"] += 1
            self.last_result = result
            if self._stopped:
                break
        self.last_run_at_ms = _now_ms()
        self.last_result = result
        return result

    def snapshot(self, *, target_type: str, target_id: str, now_ms: int | None = None) -> dict[str, Any]:
        observed_now_ms = int(now_ms if now_ms is not None else _now_ms())
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

    def stop(self) -> None:
        self._stopped = True

    async def _sleep(self, delay_seconds: float) -> None:
        remaining = max(0.0, float(delay_seconds))
        while remaining > 0 and not self._stopped:
            step = min(0.1, remaining)
            await asyncio.sleep(step)
            remaining -= step

    def close(self) -> None:
        for provider in (self.stream_provider, self.cex_market):
            close = getattr(provider, "close", None)
            if close:
                close()

    def _active_targets(self, *, now_ms: int) -> list[dict[str, Any]]:
        since_ms = int(now_ms) - int(self.hot_target_ttl_seconds * 1000)
        with self.repository_session() as repos:
            targets: Sequence[Mapping[str, Any]] = repos.registry.active_live_market_targets(
                projection_version=self.projection_version,
                since_ms=since_ms,
                limit=self.subscription_limit,
            )
        return [dict(target) for target in targets]

    def _poll_cex(self, targets: list[dict[str, Any]], *, received_at_ms: int) -> list[dict[str, Any]]:
        if self.cex_market is None:
            return []
        payloads: list[dict[str, Any]] = []
        for target in targets:
            inst_id = str(target.get("native_market_id") or "").strip().upper()
            if not inst_id:
                continue
            ticker = self.cex_market.ticker(inst_id=inst_id)
            if ticker is None:
                continue
            payloads.append(self._payload_from_cex(ticker, target=target, received_at_ms=received_at_ms))
        return payloads

    async def _stream_dex(
        self,
        targets: list[dict[str, Any]],
        *,
        received_at_ms: int,
    ) -> AsyncIterator[dict[str, Any]]:
        if self.stream_provider is None or not targets:
            return
        stream_targets = [
            DexMarketStreamTarget(
                chain_id=str(target["chain_id"]),
                address=str(target["address"]),
                subject_type=str(target["target_type"]),
                subject_id=str(target["target_id"]),
            )
            for target in targets
            if target.get("chain_id") and target.get("address") and target.get("target_id")
        ]
        target_by_key = {_target_key(target.chain_id, target.address): target for target in stream_targets}
        async for update in self.stream_provider.stream_price_info(stream_targets):
            target = target_by_key.get(_target_key(update.chain_id, update.address))
            if target is None:
                continue
            yield self._payload_from_dex(update, target=target, received_at_ms=received_at_ms)

    def _payload_from_dex(
        self,
        update: DexMarketFactUpdate,
        *,
        target: DexMarketStreamTarget,
        received_at_ms: int,
    ) -> dict[str, Any]:
        snapshot = LiveMarketSnapshot(
            target_type=target.subject_type,
            target_id=target.subject_id,
            status="live",
            price_usd=update.price_usd,
            price_quote=None,
            quote_symbol="USD",
            price_basis="usd" if update.price_usd is not None else "unavailable",
            market_cap_usd=update.market_cap_usd,
            liquidity_usd=update.liquidity_usd,
            holders=update.holders,
            volume_24h_usd=update.volume_24h_usd,
            observed_at_ms=update.observed_at_ms,
            received_at_ms=received_at_ms,
            provider=PROVIDER_OKX_DEX_WS_PRICE_INFO,
        )
        return self._store_payload(snapshot, observed_now_ms=received_at_ms)

    def _payload_from_cex(self, ticker: CexTicker, *, target: dict[str, Any], received_at_ms: int) -> dict[str, Any]:
        quote_symbol = target.get("quote_symbol") or _quote_from_inst_id(ticker.inst_id)
        price_basis = "quote_as_usd" if str(quote_symbol or "").upper() in {"USD", "USDT", "USDC"} else "quote"
        snapshot = LiveMarketSnapshot(
            target_type=str(target["target_type"]),
            target_id=str(target["target_id"]),
            status="live",
            price_usd=ticker.last_price if price_basis == "quote_as_usd" else None,
            price_quote=ticker.last_price,
            quote_symbol=str(quote_symbol).upper() if quote_symbol else None,
            price_basis=price_basis,
            market_cap_usd=None,
            liquidity_usd=None,
            holders=None,
            volume_24h_usd=ticker.volume_24h,
            observed_at_ms=received_at_ms,
            received_at_ms=received_at_ms,
            provider="okx_cex",
        )
        return self._store_payload(snapshot, observed_now_ms=received_at_ms)

    def _store_payload(self, snapshot: LiveMarketSnapshot, *, observed_now_ms: int) -> dict[str, Any]:
        self._cache[(snapshot.target_type, snapshot.target_id)] = snapshot
        return {
            "type": "live_market_update",
            "provider": snapshot.provider,
            "target_type": snapshot.target_type,
            "target_id": snapshot.target_id,
            "observed_at_ms": snapshot.observed_at_ms,
            "live_market": snapshot.to_payload(now_ms=observed_now_ms, stale_after_ms=self.live_stale_after_ms),
        }

    async def _publish(self, payload: dict[str, Any]) -> None:
        if self.on_live_market_update is None:
            return
        result = self.on_live_market_update(payload)
        if inspect.isawaitable(result):
            await result


def _is_dex_target(target: dict[str, Any]) -> bool:
    return str(target.get("target_type") or "") == "Asset" and bool(target.get("chain_id") and target.get("address"))


def _is_cex_target(target: dict[str, Any]) -> bool:
    return str(target.get("target_type") or "") == "CexToken" and bool(target.get("native_market_id"))


def _target_key(chain_id: Any, address: Any) -> tuple[str, str]:
    return (str(chain_id or "").strip().lower(), _normalize_address(address))


def _normalize_address(address: Any) -> str:
    text = str(address or "").strip()
    return text.lower() if text.startswith(("0x", "0X")) else text


def _quote_from_inst_id(inst_id: str) -> str | None:
    parts = [part.strip().upper() for part in str(inst_id).split("-") if part.strip()]
    if len(parts) < 2:
        return None
    return parts[1]


def _now_ms() -> int:
    return int(time.time() * 1000)
