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
    cex_token_ids = [str(row["target_id"]) for row in targets if str(row.get("target_type") or "") == "CexToken"]
    gmgn_openapi = query.gmgn_openapi_profiles(asset_ids)
    binance_web3 = query.binance_web3_profiles(asset_ids)
    gmgn_stream = query.gmgn_stream_profiles(asset_ids)
    okx_dex = query.okx_dex_profiles(asset_ids)
    cex_profiles = query.cex_token_profiles(cex_token_ids)
    ready_images_by_source_url = _ready_images_by_source_url(
        repos=repos,
        sources=[gmgn_openapi, binance_web3, gmgn_stream, okx_dex, cex_profiles],
    )
    result = _empty_result(now_ms=now_ms)
    result["selected"] = len(targets)

    for target in targets:
        target_id = str(target.get("target_id") or "")
        row = project_token_profile_current(
            target=target,
            gmgn_openapi=gmgn_openapi.get(target_id),
            binance_web3=binance_web3.get(target_id),
            gmgn_stream=gmgn_stream.get(target_id),
            okx_dex=okx_dex.get(target_id),
            cex_profile=cex_profiles.get(target_id),
            ready_images_by_source_url=ready_images_by_source_url,
            computed_at_ms=now_ms,
        )
        repos.token_profiles.upsert_current(row, commit=False)
        _record_row(result, row)
    repos.conn.commit()
    result["finished_at_ms"] = int(now_ms)
    return result


def _ready_images_by_source_url(*, repos: Any, sources: list[dict[str, dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    source_urls = _candidate_logo_urls(sources)
    if not source_urls:
        return {}
    return repos.token_image_assets.ready_by_source_urls(source_urls)


def _candidate_logo_urls(sources: list[dict[str, dict[str, Any]]]) -> list[str]:
    urls: list[str] = []
    for rows_by_target in sources:
        for row in rows_by_target.values():
            for value in _logo_url_values(row):
                url = _clean_absolute_http_url(value)
                if url:
                    urls.append(url)
    return list(dict.fromkeys(urls))


def _logo_url_values(row: dict[str, Any]) -> list[Any]:
    raw = row.get("raw_payload_json")
    raw_payload = dict(raw) if isinstance(raw, dict) else {}
    return [
        row.get("logo_url"),
        raw_payload.get("i"),
        raw_payload.get("tokenLogoUrl"),
    ]


def _clean_absolute_http_url(value: Any) -> str | None:
    text = str(value or "").strip()
    if text.startswith(("http://", "https://")):
        return text
    return None


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
