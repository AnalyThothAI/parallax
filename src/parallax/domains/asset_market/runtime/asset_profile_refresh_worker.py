from __future__ import annotations

import asyncio
import time
from typing import Any

from parallax.app.runtime.worker_base import WorkerBase
from parallax.app.runtime.worker_result import WorkerResult
from parallax.domains.asset_market.providers import (
    DexProfileSource,
    DexProviderTemporarilyUnavailable,
    DexTokenProfile,
)
from parallax.domains.asset_market.services.asset_profile_refresh import (
    fetch_asset_profile,
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
            notes={
                "claimed": int(result.get("claimed") or 0),
                "queue_depth": int(result.get("queue_depth") or 0),
                "source_rows_scanned": int(result.get("source_rows_scanned") or 0),
                "targets_loaded": int(result.get("targets_loaded") or 0),
                "rows_written": int(result.get("rows_written") or 0),
                "result": result,
            },
        )

    def _refresh_once(self, now_ms: int) -> dict[str, Any]:
        result: dict[str, Any] = {
            "providers": [source.provider for source in self.dex_profile_sources],
            "selected": 0,
            "claimed": 0,
            "queue_depth": 0,
            "source_rows_scanned": 0,
            "targets_loaded": 0,
            "rows_written": 0,
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
            for key in (
                "selected",
                "claimed",
                "queue_depth",
                "source_rows_scanned",
                "targets_loaded",
                "rows_written",
                "ready",
                "missing",
                "error",
                "provider_blocked",
                "skipped",
            ):
                result[key] += int(source_result.get(key) or 0)
        return result

    def _refresh_source_once(self, *, profile_source: DexProfileSource, now_ms: int) -> dict[str, Any]:
        source_result: dict[str, Any] = {
            "provider": profile_source.provider,
            "selected": 0,
            "claimed": 0,
            "queue_depth": 0,
            "source_rows_scanned": 0,
            "targets_loaded": 0,
            "rows_written": 0,
            "ready": 0,
            "missing": 0,
            "error": 0,
            "provider_blocked": 0,
            "skipped": 0,
            "started_at_ms": int(now_ms),
            "finished_at_ms": int(now_ms),
        }
        with self.db.worker_session(
            self.name,
            statement_timeout_seconds=self.settings.statement_timeout_seconds,
        ) as repos:
            rows = repos.asset_profile_refresh_targets.claim_due(
                provider=profile_source.provider,
                now_ms=now_ms,
                limit=max(1, int(self.settings.batch_size)),
                lease_owner=self.name,
                lease_ms=max(1, int(self.settings.lease_ms)),
                commit=True,
            )
            source_result["queue_depth"] = repos.asset_profile_refresh_targets.queue_depth(
                provider=profile_source.provider,
                now_ms=now_ms,
            )
        source_result["selected"] = len(rows)
        source_result["claimed"] = len(rows)
        source_result["targets_loaded"] = len(rows)
        if not rows:
            source_result["skipped"] = 1
            source_result["reason"] = "no_due_asset_profile_refresh_targets"
            return source_result
        ready_refresh_ms = max(1, int(self.settings.ready_refresh_ms))
        missing_refresh_ms = max(1, int(self.settings.missing_refresh_ms))
        error_refresh_ms = max(1, int(self.settings.error_refresh_ms))
        for row in rows:
            try:
                profile = fetch_asset_profile(profile_source=profile_source, row=row)
            except DexProviderTemporarilyUnavailable as exc:
                source_result["provider_blocked"] = 1
                source_result["last_error"] = str(exc)[:500]
                self._reschedule_claims(
                    [item for item in rows if int(item.get("due_at_ms") or 0) <= int(now_ms)],
                    due_at_ms=now_ms + self._provider_retry_ms(),
                    now_ms=now_ms,
                    reason="provider_blocked",
                )
                break
            except Exception as exc:
                next_refresh_at_ms = now_ms + error_refresh_ms
                with (
                    self.db.worker_session(
                        self.name,
                        statement_timeout_seconds=self.settings.statement_timeout_seconds,
                    ) as repos,
                    repos.transaction(),
                ):
                    write_error_asset_profile(
                        repos=repos,
                        provider=profile_source.provider,
                        row=row,
                        exc=exc,
                        now_ms=now_ms,
                        next_refresh_at_ms=next_refresh_at_ms,
                    )
                    repos.asset_profile_refresh_targets.reschedule(
                        [row],
                        due_at_ms=next_refresh_at_ms,
                        now_ms=now_ms,
                        reason="profile_error_written",
                        commit=False,
                    )
                    _enqueue_profile_current(repos=repos, row=row, now_ms=now_ms)
                source_result["rows_written"] += 1
                source_result["error"] += 1
                continue
            with (
                self.db.worker_session(
                    self.name,
                    statement_timeout_seconds=self.settings.statement_timeout_seconds,
                ) as repos,
                repos.transaction(),
            ):
                if isinstance(profile, DexTokenProfile):
                    next_refresh_at_ms = now_ms + ready_refresh_ms
                    write_ready_asset_profile(
                        repos=repos,
                        provider=profile_source.provider,
                        row=row,
                        profile=profile,
                        now_ms=now_ms,
                        next_refresh_at_ms=next_refresh_at_ms,
                    )
                    repos.asset_profile_refresh_targets.reschedule(
                        [row],
                        due_at_ms=next_refresh_at_ms,
                        now_ms=now_ms,
                        reason="profile_ready_written",
                        commit=False,
                    )
                    source_result["ready"] += 1
                else:
                    next_refresh_at_ms = now_ms + missing_refresh_ms
                    write_missing_asset_profile(
                        repos=repos,
                        provider=profile_source.provider,
                        row=row,
                        now_ms=now_ms,
                        next_refresh_at_ms=next_refresh_at_ms,
                    )
                    repos.asset_profile_refresh_targets.reschedule(
                        [row],
                        due_at_ms=next_refresh_at_ms,
                        now_ms=now_ms,
                        reason="profile_missing_written",
                        commit=False,
                    )
                    source_result["missing"] += 1
                _enqueue_profile_current(repos=repos, row=row, now_ms=now_ms)
                source_result["rows_written"] += 1
        return source_result

    def _reschedule_claims(self, claims: list[dict[str, Any]], *, due_at_ms: int, now_ms: int, reason: str) -> None:
        if not claims:
            return
        with (
            self.db.worker_session(
                self.name,
                statement_timeout_seconds=self.settings.statement_timeout_seconds,
            ) as repos,
            repos.transaction(),
        ):
            repos.asset_profile_refresh_targets.reschedule(
                claims,
                due_at_ms=due_at_ms,
                now_ms=now_ms,
                reason=reason,
                commit=False,
            )

    def _provider_retry_ms(self) -> int:
        return max(1, int(self.settings.provider_retry_ms))


def _enqueue_profile_current(*, repos: Any, row: dict[str, Any], now_ms: int) -> None:
    repos.token_profile_current_dirty_targets.enqueue_targets(
        [
            {
                "target_type": "Asset",
                "target_id": str(row.get("asset_id") or row.get("target_id") or ""),
                "source_watermark_ms": int(row.get("source_watermark_ms") or now_ms),
                "priority": 40,
            }
        ],
        reason="asset_profile_refresh_changed",
        now_ms=now_ms,
        commit=False,
    )
