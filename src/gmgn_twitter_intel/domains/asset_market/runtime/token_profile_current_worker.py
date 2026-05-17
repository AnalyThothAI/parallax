from __future__ import annotations

import asyncio
import time
from typing import Any

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.domains.asset_market.queries.token_profile_source_query import TokenProfileSourceQuery
from gmgn_twitter_intel.domains.asset_market.services.token_profile_current_projection import (
    project_token_profile_current,
)


class TokenProfileCurrentWorker(WorkerBase):
    async def run_once(self, *, now_ms: int | None = None) -> WorkerResult:
        observed_at_ms = int(now_ms if now_ms is not None else time.time() * 1000)
        result = await asyncio.to_thread(self._rebuild_once, observed_at_ms)
        return WorkerResult(
            processed=int(result.get("ready") or 0)
            + int(result.get("missing") or 0)
            + int(result.get("unsupported") or 0),
            failed=int(result.get("error") or 0),
            notes={"result": result},
        )

    def _rebuild_once(self, now_ms: int) -> dict[str, Any]:
        with self.db.worker_session(self.name) as repos:
            return rebuild_token_profile_current_once(
                repos=repos,
                now_ms=now_ms,
                limit=max(1, int(getattr(self.settings, "batch_size", 500))),
            )


def rebuild_token_profile_current_once(*, repos: Any, now_ms: int, limit: int = 500) -> dict[str, Any]:
    query = getattr(repos, "source_query", None) or TokenProfileSourceQuery(repos.conn)
    targets = query.recent_profile_targets(now_ms=now_ms, limit=limit)
    asset_ids = [str(row["target_id"]) for row in targets if str(row.get("target_type") or "") == "Asset"]
    gmgn_openapi = query.gmgn_openapi_profiles(asset_ids)
    gmgn_stream = query.gmgn_stream_profiles(asset_ids)
    okx_dex = query.okx_dex_profiles(asset_ids)
    result = _empty_result(now_ms=now_ms)
    result["selected"] = len(targets)

    for target in targets:
        target_id = str(target.get("target_id") or "")
        row = project_token_profile_current(
            target=target,
            gmgn_openapi=gmgn_openapi.get(target_id),
            gmgn_stream=gmgn_stream.get(target_id),
            okx_dex=okx_dex.get(target_id),
            computed_at_ms=now_ms,
        )
        repos.token_profiles.upsert_current(row, commit=False)
        _record_row(result, row)
    repos.conn.commit()
    result["finished_at_ms"] = int(now_ms)
    return result


def _record_row(result: dict[str, Any], row: dict[str, Any]) -> None:
    status = str(row.get("status") or "error")
    if status not in {"ready", "missing", "unsupported", "error"}:
        status = "error"
    result[status] += 1
    if row.get("logo_url"):
        result["with_logo"] += 1
    provider = row.get("profile_provider")
    if provider:
        counts = result["source_provider"]
        counts[str(provider)] = int(counts.get(str(provider)) or 0) + 1


def _empty_result(*, now_ms: int) -> dict[str, Any]:
    return {
        "selected": 0,
        "ready": 0,
        "missing": 0,
        "unsupported": 0,
        "error": 0,
        "with_logo": 0,
        "source_provider": {},
        "started_at_ms": int(now_ms),
        "finished_at_ms": int(now_ms),
    }
