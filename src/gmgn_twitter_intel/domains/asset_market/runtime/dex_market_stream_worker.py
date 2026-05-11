from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any

from loguru import logger

from gmgn_twitter_intel.domains.asset_market.market_field_facts import PROVIDER_OKX_DEX_WS_PRICE_INFO
from gmgn_twitter_intel.domains.asset_market.providers import DexMarketFactUpdate, DexMarketStreamTarget


class DexMarketStreamWorker:
    def __init__(
        self,
        *,
        stream_provider: Any,
        repository_session: Callable[[], AbstractContextManager[Any]],
        projection_version: str,
        subscription_limit: int,
        hot_target_ttl_seconds: float,
        reconnect_delay_seconds: float = 3.0,
        on_market_update: Callable[[dict[str, Any]], Any] | None = None,
    ) -> None:
        self.stream_provider = stream_provider
        self.repository_session = repository_session
        self.projection_version = projection_version
        self.subscription_limit = max(1, int(subscription_limit))
        self.hot_target_ttl_seconds = max(1.0, float(hot_target_ttl_seconds))
        self.reconnect_delay_seconds = max(0.1, float(reconnect_delay_seconds))
        self.on_market_update = on_market_update
        self.last_started_at_ms: int | None = None
        self.last_run_at_ms: int | None = None
        self.last_result: dict[str, Any] | None = None
        self.last_error: str | None = None
        self._stopped = False

    async def run(self) -> None:
        while not self._stopped:
            try:
                await self.run_once()
            except Exception as exc:  # pragma: no cover - watchdog path
                self.last_error = str(exc)
                logger.exception(f"OKX DEX websocket market stream failed: {exc}")
                await asyncio.sleep(self.reconnect_delay_seconds)

    async def run_once(self, *, now_ms: int | None = None) -> dict[str, Any]:
        observed_now_ms = int(now_ms if now_ms is not None else _now_ms())
        self.last_started_at_ms = observed_now_ms
        self.last_error = None
        result = {
            "targets_selected": 0,
            "updates_received": 0,
            "observations_written": 0,
            "market_updates_published": 0,
        }
        targets = self._active_targets(now_ms=observed_now_ms)
        result["targets_selected"] = len(targets)
        target_by_key = {_target_key(target.chain_id, target.address): target for target in targets}
        async for update in self.stream_provider.stream_price_info(targets):
            result["updates_received"] += 1
            target = target_by_key.get(_target_key(update.chain_id, update.address))
            if target is None:
                continue
            payload = self._write_update(update, target=target, now_ms=observed_now_ms)
            result["observations_written"] += 1
            if payload is not None:
                await self._publish(payload)
                result["market_updates_published"] += 1
            self.last_result = result
            if self._stopped:
                break
        self.last_run_at_ms = _now_ms()
        self.last_result = result
        return result

    def stop(self) -> None:
        self._stopped = True

    def close(self) -> None:
        close = getattr(self.stream_provider, "close", None)
        if close:
            close()

    def _active_targets(self, *, now_ms: int) -> list[DexMarketStreamTarget]:
        since_ms = int(now_ms) - int(self.hot_target_ttl_seconds * 1000)
        with self.repository_session() as repos:
            rows = repos.registry.active_dex_market_stream_targets(
                projection_version=self.projection_version,
                since_ms=since_ms,
                limit=self.subscription_limit,
            )
        return [
            DexMarketStreamTarget(
                chain_id=str(row.get("chain_id") or ""),
                address=str(row.get("address") or ""),
                subject_type="Asset",
                subject_id=str(row.get("asset_id") or ""),
                pricefeed_id=row.get("pricefeed_id"),
            )
            for row in rows
            if row.get("chain_id") and row.get("address") and row.get("asset_id")
        ]

    def _write_update(
        self,
        update: DexMarketFactUpdate,
        *,
        target: DexMarketStreamTarget,
        now_ms: int,
    ) -> dict[str, Any] | None:
        with self.repository_session() as repos:
            pricefeed = repos.registry.upsert_pricefeed(
                feed_type="dex_token",
                provider=PROVIDER_OKX_DEX_WS_PRICE_INFO,
                subject_type=target.subject_type,
                subject_id=target.subject_id,
                observed_at_ms=update.observed_at_ms,
                chain_id=target.chain_id,
                address=target.address,
                base_asset_id=target.subject_id,
                commit=False,
            )
            pricefeed_id = str(pricefeed.get("pricefeed_id") or target.pricefeed_id or "")
            repos.price_observations.insert_observation(
                provider=PROVIDER_OKX_DEX_WS_PRICE_INFO,
                pricefeed_id=pricefeed_id or None,
                observed_at_ms=update.observed_at_ms,
                subject_type=target.subject_type,
                subject_id=target.subject_id,
                price_usd=update.price_usd,
                price_basis="usd" if update.price_usd is not None else "unavailable",
                market_cap_usd=update.market_cap_usd,
                liquidity_usd=update.liquidity_usd,
                volume_24h_usd=update.volume_24h_usd,
                open_interest_usd=update.open_interest_usd,
                holders=update.holders,
                raw_payload=update.raw or {},
                commit=False,
            )
            repos.conn.commit()
            snapshots = repos.current_market.current_for_subjects(
                [{"target_type": target.subject_type, "target_id": target.subject_id}],
                now_ms=now_ms,
            )
            current_market = snapshots.get((target.subject_type, target.subject_id))
        if current_market is None:
            return None
        return {
            "type": "market_update",
            "provider": PROVIDER_OKX_DEX_WS_PRICE_INFO,
            "target_type": target.subject_type,
            "target_id": target.subject_id,
            "observed_at_ms": update.observed_at_ms,
            "current_market": current_market,
        }

    async def _publish(self, payload: dict[str, Any]) -> None:
        if self.on_market_update is None:
            return
        result = self.on_market_update(payload)
        if inspect.isawaitable(result):
            await result


def _target_key(chain_id: Any, address: Any) -> tuple[str, str]:
    return (str(chain_id or "").strip().lower(), _normalize_address(address))


def _normalize_address(address: Any) -> str:
    text = str(address or "").strip()
    return text.lower() if text.startswith(("0x", "0X")) else text


def _now_ms() -> int:
    return int(time.time() * 1000)
