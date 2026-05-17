from __future__ import annotations

import asyncio
import time
from typing import Any

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.domains.asset_market.providers import (
    DexProfileSource,
    DexProviderTemporarilyUnavailable,
    DexTokenProfile,
)
from gmgn_twitter_intel.domains.asset_market.services.asset_profile_refresh import (
    fetch_asset_profile,
    select_due_asset_profile_rows,
    write_error_asset_profile,
    write_missing_asset_profile,
    write_ready_asset_profile,
)


class AssetProfileRefreshWorker(WorkerBase):
    def __init__(
        self,
        *,
        name: str,
        settings: Any,
        db: Any,
        telemetry: Any,
        dex_profile_sources: tuple[DexProfileSource, ...] = (),
    ) -> None:
        super().__init__(name=name, settings=settings, db=db, telemetry=telemetry)
        self.dex_profile_sources = tuple(dex_profile_sources)

    async def run_once(self, *, now_ms: int | None = None) -> WorkerResult:
        observed_at_ms = int(now_ms if now_ms is not None else time.time() * 1000)
        result = await asyncio.to_thread(self._refresh_once, observed_at_ms)
        return WorkerResult(
            processed=int(result.get("ready") or 0) + int(result.get("missing") or 0),
            failed=int(result.get("error") or 0) + int(result.get("provider_blocked") or 0),
            skipped=int(result.get("skipped") or 0),
            notes={"result": result},
        )

    def _refresh_once(self, now_ms: int) -> dict[str, Any]:
        result: dict[str, Any] = {
            "providers": [source.provider for source in self.dex_profile_sources],
            "selected": 0,
            "ready": 0,
            "missing": 0,
            "error": 0,
            "provider_blocked": 0,
            "skipped": 0,
            "sources": {},
            "started_at_ms": int(now_ms),
            "finished_at_ms": int(now_ms),
        }
        if not self.dex_profile_sources:
            result["skipped"] = 1
            return result
        for profile_source in self.dex_profile_sources:
            source_result = self._refresh_source_once(profile_source=profile_source, now_ms=now_ms)
            result["sources"][profile_source.provider] = source_result
            for key in ("selected", "ready", "missing", "error", "provider_blocked", "skipped"):
                result[key] += int(source_result.get(key) or 0)
        return result

    def _refresh_source_once(self, *, profile_source: DexProfileSource, now_ms: int) -> dict[str, Any]:
        source_result: dict[str, Any] = {
            "provider": profile_source.provider,
            "selected": 0,
            "ready": 0,
            "missing": 0,
            "error": 0,
            "provider_blocked": 0,
            "skipped": 0,
            "started_at_ms": int(now_ms),
            "finished_at_ms": int(now_ms),
        }
        with self.db.worker_session(self.name) as repos:
            rows = select_due_asset_profile_rows(
                repos=repos,
                provider=profile_source.provider,
                now_ms=now_ms,
                limit=max(1, int(getattr(self.settings, "batch_size", 50))),
            )
        source_result["selected"] = len(rows)
        for row in rows:
            try:
                profile = fetch_asset_profile(profile_source=profile_source, row=row)
            except DexProviderTemporarilyUnavailable as exc:
                source_result["provider_blocked"] = 1
                source_result["last_error"] = str(exc)[:500]
                break
            except Exception as exc:
                with self.db.worker_session(self.name) as repos:
                    write_error_asset_profile(
                        repos=repos,
                        provider=profile_source.provider,
                        row=row,
                        exc=exc,
                        now_ms=now_ms,
                    )
                source_result["error"] += 1
                continue
            with self.db.worker_session(self.name) as repos:
                if isinstance(profile, DexTokenProfile):
                    write_ready_asset_profile(
                        repos=repos,
                        provider=profile_source.provider,
                        row=row,
                        profile=profile,
                        now_ms=now_ms,
                    )
                    source_result["ready"] += 1
                else:
                    write_missing_asset_profile(
                        repos=repos,
                        provider=profile_source.provider,
                        row=row,
                        now_ms=now_ms,
                    )
                    source_result["missing"] += 1
        return source_result
