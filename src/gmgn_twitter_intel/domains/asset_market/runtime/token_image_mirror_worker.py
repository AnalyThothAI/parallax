from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.domains.asset_market.queries.token_image_source_query import TokenImageSourceQuery
from gmgn_twitter_intel.domains.asset_market.services.token_image_mirror import TokenImageMirrorService


class TokenImageMirrorWorker(WorkerBase):
    def __init__(
        self,
        *,
        name: str,
        settings: Any,
        db: Any,
        telemetry: Any,
        app_home: str | Path,
    ) -> None:
        super().__init__(name=name, settings=settings, db=db, telemetry=telemetry)
        self.app_home = Path(app_home)

    async def run_once(self, *, now_ms: int | None = None) -> WorkerResult:
        observed_at_ms = int(now_ms if now_ms is not None else time.time() * 1000)
        result = await asyncio.to_thread(self._mirror_once, observed_at_ms)
        return WorkerResult(
            processed=int(result.get("claimed") or 0),
            failed=int(result.get("error") or 0),
            notes={"result": result},
        )

    def _mirror_once(self, now_ms: int) -> dict[str, Any]:
        result = _empty_result(now_ms=now_ms)
        with self.db.worker_session(
            self.name,
            statement_timeout_seconds=float(getattr(self.settings, "statement_timeout_seconds", 120.0)),
        ) as repos:
            query = getattr(repos, "token_image_source_query", None) or TokenImageSourceQuery(repos.conn)
            source_rows = query.candidate_sources(
                now_ms=now_ms,
                source_limit=max(0, int(getattr(self.settings, "source_limit", 5000))),
            )
            source_urls = [str(row.get("source_url") or "") for row in source_rows if row.get("source_url")]
            result["selected"] = len(source_rows)
            result["pending_upserted"] = repos.token_image_assets.upsert_pending_sources(source_rows, now_ms=now_ms)
            result["ready_existing"] = len(repos.token_image_assets.ready_by_source_urls(source_urls))
            claimed = repos.token_image_assets.claim_due_sources(
                now_ms=now_ms,
                limit=max(1, int(getattr(self.settings, "batch_size", 100))),
            )
            result["claimed"] = len(claimed)

        mirror_service = TokenImageMirrorService(
            repository=_TokenImageAssetSessionRepository(self.db, self.name, self.settings),
            app_home=self.app_home,
        )
        for row in claimed:
            mirror_result = mirror_service.mirror_source(row, now_ms=now_ms)
            _record_mirror_result(result, mirror_result)

        result["finished_at_ms"] = int(now_ms)
        return result


class _TokenImageAssetSessionRepository:
    def __init__(self, db: Any, worker_name: str, settings: Any) -> None:
        self.db = db
        self.worker_name = worker_name
        self.settings = settings

    def mark_ready(
        self,
        source_url: str,
        media_type: str,
        file_extension: str,
        content_sha256: str,
        byte_size: int,
        storage_path: str,
        now_ms: int,
        commit: bool = True,
    ) -> dict[str, Any]:
        with self.db.worker_session(
            self.worker_name,
            statement_timeout_seconds=float(getattr(self.settings, "statement_timeout_seconds", 120.0)),
        ) as repos:
            return repos.token_image_assets.mark_ready(
                source_url=source_url,
                media_type=media_type,
                file_extension=file_extension,
                content_sha256=content_sha256,
                byte_size=byte_size,
                storage_path=storage_path,
                now_ms=now_ms,
                commit=commit,
            )

    def mark_error(
        self,
        source_url: str,
        error: str,
        now_ms: int,
        retry_ms: int,
        commit: bool = True,
    ) -> None:
        with self.db.worker_session(
            self.worker_name,
            statement_timeout_seconds=float(getattr(self.settings, "statement_timeout_seconds", 120.0)),
        ) as repos:
            repos.token_image_assets.mark_error(
                source_url=source_url,
                error=error,
                now_ms=now_ms,
                retry_ms=retry_ms,
                commit=commit,
            )


def _record_mirror_result(result: dict[str, Any], mirror_result: dict[str, Any]) -> None:
    status = str(mirror_result.get("status") or "")
    error = str(mirror_result.get("error") or "")
    if status == "ready":
        result["mirrored"] += 1
    elif status == "unsupported" or error.startswith("unsupported_"):
        result["unsupported"] += 1
    else:
        result["error"] += 1


def _empty_result(*, now_ms: int) -> dict[str, Any]:
    return {
        "selected": 0,
        "pending_upserted": 0,
        "ready_existing": 0,
        "claimed": 0,
        "mirrored": 0,
        "error": 0,
        "unsupported": 0,
        "started_at_ms": int(now_ms),
        "finished_at_ms": int(now_ms),
    }
