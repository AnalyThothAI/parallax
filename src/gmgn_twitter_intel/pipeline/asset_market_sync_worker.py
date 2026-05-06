from __future__ import annotations

import asyncio
import time
from typing import Any

from loguru import logger

from .asset_market_sync import sync_okx_cex_universe, sync_okx_dex_prices

DEX_PRICE_STALE_MS = 5 * 60 * 1000
DEX_PRICE_REFRESH_LIMIT = 80


class AssetMarketSyncWorker:
    def __init__(
        self,
        *,
        repository_session,
        client=None,
        dex_client=None,
        inst_types: tuple[str, ...],
        interval_seconds: float = 300.0,
    ) -> None:
        self.client = client
        self.dex_client = dex_client
        self.repository_session = repository_session
        self.inst_types = tuple(str(item).strip().upper() for item in inst_types if str(item).strip())
        self.interval_seconds = interval_seconds
        self._stopped = False
        self._cex_task: asyncio.Task | None = None
        self._dex_task: asyncio.Task | None = None
        self.provider_states: dict[str, dict[str, Any]] = {
            "cex": _provider_state(),
            "dex": _provider_state(),
        }
        self.last_started_at_ms: int | None = None
        self.last_run_at_ms: int | None = None
        self.last_result: dict[str, Any] | None = None
        self.last_error: str | None = None

    async def run(self) -> None:
        while not self._stopped:
            now_ms = _now_ms()
            if self.dex_client is not None:
                self._dex_task = self._start_provider_task("dex", self._dex_task, self._sync_dex_once, now_ms=now_ms)
            if self.client is not None and self.inst_types:
                self._cex_task = self._start_provider_task("cex", self._cex_task, self._sync_cex_once, now_ms=now_ms)
            await asyncio.sleep(max(1.0, float(self.interval_seconds)))

    def sync_once(self, *, now_ms: int | None = None) -> dict[str, Any]:
        observed_at_ms = int(now_ms or _now_ms())
        result: dict[str, Any] = {}
        ran_cex = self.client is not None and bool(self.inst_types)
        ran_dex = self.dex_client is not None
        errors: dict[str, str] = {}
        if self.dex_client is not None:
            try:
                with self.repository_session() as repos:
                    result["dex"] = sync_okx_dex_prices(
                        assets=repos.assets,
                        client=self.dex_client,
                        observed_at_ms=observed_at_ms,
                        stale_after_ms=DEX_PRICE_STALE_MS,
                        limit=DEX_PRICE_REFRESH_LIMIT,
                    )
            except Exception as exc:
                errors["dex"] = str(exc)
                logger.exception(f"OKX DEX market price sync failed: {exc}")
        if self.client is not None and self.inst_types:
            try:
                with self.repository_session() as repos:
                    result["cex"] = sync_okx_cex_universe(
                        assets=repos.assets,
                        client=self.client,
                        inst_types=self.inst_types,
                        observed_at_ms=observed_at_ms,
                    )
            except Exception as exc:
                errors["cex"] = str(exc)
                logger.exception(f"OKX CEX market sync failed: {exc}")
        if errors:
            result["errors"] = errors
        if ran_cex and not ran_dex and not errors:
            return result["cex"]
        if ran_dex and not ran_cex and not errors:
            return result["dex"]
        return result

    def _sync_dex_once(self, *, now_ms: int) -> dict[str, Any]:
        with self.repository_session() as repos:
            return sync_okx_dex_prices(
                assets=repos.assets,
                client=self.dex_client,
                observed_at_ms=now_ms,
                stale_after_ms=DEX_PRICE_STALE_MS,
                limit=DEX_PRICE_REFRESH_LIMIT,
            )

    def _sync_cex_once(self, *, now_ms: int) -> dict[str, Any]:
        with self.repository_session() as repos:
            return sync_okx_cex_universe(
                assets=repos.assets,
                client=self.client,
                inst_types=self.inst_types,
                observed_at_ms=now_ms,
            )

    def _start_provider_task(self, name: str, task: asyncio.Task | None, func, *, now_ms: int) -> asyncio.Task:
        if task is not None and not task.done():
            return task
        return asyncio.create_task(self._run_provider(name, func, now_ms=now_ms))

    async def _run_provider(self, name: str, func, *, now_ms: int) -> None:
        state = self.provider_states[name]
        state["running"] = True
        state["last_started_at_ms"] = now_ms
        state["last_error"] = None
        self._refresh_status()
        try:
            state["last_result"] = await asyncio.to_thread(func, now_ms=now_ms)
            state["last_run_at_ms"] = _now_ms()
        except Exception as exc:  # pragma: no cover - watchdog path
            state["last_error"] = str(exc)
            logger.exception(f"OKX {name.upper()} market sync failed: {exc}")
        finally:
            state["running"] = False
            self._refresh_status()

    def _refresh_status(self) -> None:
        started = [
            state["last_started_at_ms"]
            for state in self.provider_states.values()
            if state["last_started_at_ms"]
        ]
        runs = [state["last_run_at_ms"] for state in self.provider_states.values() if state["last_run_at_ms"]]
        errors = [
            f"{name}:{state['last_error']}"
            for name, state in self.provider_states.items()
            if state.get("last_error")
        ]
        self.last_started_at_ms = max(started) if started else None
        self.last_run_at_ms = max(runs) if runs else None
        self.last_error = "; ".join(errors) if errors else None
        self.last_result = {
            name: state["last_result"]
            for name, state in self.provider_states.items()
            if state.get("last_result") is not None
        } or None

    def stop(self) -> None:
        self._stopped = True

    def close(self) -> None:
        for client in (self.client, self.dex_client):
            close = getattr(client, "close", None)
            if close:
                close()


def _now_ms() -> int:
    return int(time.time() * 1000)


def _provider_state() -> dict[str, Any]:
    return {
        "running": False,
        "last_started_at_ms": None,
        "last_run_at_ms": None,
        "last_result": None,
        "last_error": None,
    }
