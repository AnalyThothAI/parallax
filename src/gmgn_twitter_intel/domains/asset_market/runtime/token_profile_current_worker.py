from __future__ import annotations

import asyncio
import time
from typing import Any, cast

from gmgn_twitter_intel.app.runtime.worker_base import WorkerBase
from gmgn_twitter_intel.app.runtime.worker_result import WorkerResult
from gmgn_twitter_intel.domains.asset_market.queries.token_profile_source_query import TokenProfileSourceQuery
from gmgn_twitter_intel.domains.asset_market.services.token_profile_current_projection import (
    project_token_profile_current,
)

DEFAULT_LEASE_MS = 60_000
DEFAULT_RETRY_MS = 30_000


class TokenProfileCurrentWorker(WorkerBase):
    async def run_once(self, *, now_ms: int | None = None) -> WorkerResult:
        observed_at_ms = int(now_ms if now_ms is not None else time.time() * 1000)
        result = await asyncio.to_thread(self._rebuild_once, observed_at_ms)
        return WorkerResult(
            processed=int(result.get("ready") or 0)
            + int(result.get("missing") or 0)
            + int(result.get("unsupported") or 0),
            failed=int(result.get("error") or 0),
            skipped=1 if int(result.get("claimed") or 0) == 0 else 0,
            notes={
                "claimed": int(result.get("claimed") or 0),
                "queue_depth": int(result.get("queue_depth") or 0),
                "source_rows_scanned": int(result.get("source_rows_scanned") or 0),
                "targets_loaded": int(result.get("targets_loaded") or 0),
                "rows_written": int(result.get("rows_written") or 0),
                "result": result,
            },
        )

    def _rebuild_once(self, now_ms: int) -> dict[str, Any]:
        with self.db.worker_session(
            self.name,
            statement_timeout_seconds=getattr(self.settings, "statement_timeout_seconds", None),
        ) as repos:
            return rebuild_token_profile_current_once(
                repos=repos,
                now_ms=now_ms,
                limit=max(1, int(getattr(self.settings, "batch_size", 500))),
                lease_owner=self.name,
                lease_ms=max(1, int(getattr(self.settings, "lease_ms", DEFAULT_LEASE_MS) or DEFAULT_LEASE_MS)),
                retry_ms=max(1, int(getattr(self.settings, "retry_ms", DEFAULT_RETRY_MS) or DEFAULT_RETRY_MS)),
            )


def rebuild_token_profile_current_once(
    *,
    repos: Any,
    now_ms: int,
    limit: int = 500,
    lease_owner: str = "token_profile_current",
    lease_ms: int = DEFAULT_LEASE_MS,
    retry_ms: int = DEFAULT_RETRY_MS,
) -> dict[str, Any]:
    result = _empty_result(now_ms=now_ms)
    claims = repos.token_profile_current_dirty_targets.claim_due(
        now_ms=now_ms,
        limit=limit,
        lease_owner=lease_owner,
        lease_ms=lease_ms,
        commit=True,
    )
    result["claimed"] = len(claims)
    result["selected"] = len(claims)
    result["queue_depth"] = repos.token_profile_current_dirty_targets.queue_depth(now_ms=now_ms)
    if not claims:
        result["reason"] = "no_due_token_profile_current_targets"
        return result

    try:
        with repos.transaction():
            _project_claimed_token_profiles(repos=repos, claims=claims, now_ms=now_ms, result=result)
            repos.token_profile_current_dirty_targets.mark_done(claims, now_ms=now_ms, commit=False)
    except Exception as exc:
        with repos.transaction():
            repos.token_profile_current_dirty_targets.mark_error(
                claims,
                error=_error_text(exc),
                now_ms=now_ms,
                retry_ms=retry_ms,
                commit=False,
            )
        result["error"] += len(claims)
        result["last_error"] = _error_text(exc)
    result["finished_at_ms"] = int(now_ms)
    return result


def _project_claimed_token_profiles(
    *,
    repos: Any,
    claims: list[dict[str, Any]],
    now_ms: int,
    result: dict[str, Any],
) -> None:
    query = getattr(repos, "source_query", None) or TokenProfileSourceQuery(repos.conn)
    targets = _dedupe_targets(claims)
    result["targets_loaded"] = len(targets)
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
        result["rows_written"] += 1
        _record_row(result, row)


def _dedupe_targets(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    targets: dict[tuple[str, str], dict[str, str]] = {}
    for row in rows:
        target_type = str(row.get("target_type") or "").strip()
        target_id = str(row.get("target_id") or "").strip()
        if target_type and target_id:
            targets[(target_type, target_id)] = {"target_type": target_type, "target_id": target_id}
    return list(targets.values())


def _ready_images_by_source_url(*, repos: Any, sources: list[dict[str, dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    source_urls = _candidate_logo_urls(sources)
    if not source_urls:
        return {}
    return cast(dict[str, dict[str, Any]], repos.token_image_assets.ready_by_source_urls(source_urls))


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
        "claimed": 0,
        "queue_depth": 0,
        "source_rows_scanned": 0,
        "targets_loaded": 0,
        "rows_written": 0,
        "ready": 0,
        "missing": 0,
        "unsupported": 0,
        "error": 0,
        "with_logo": 0,
        "source_provider": {},
        "started_at_ms": int(now_ms),
        "finished_at_ms": int(now_ms),
    }


def _error_text(exc: BaseException) -> str:
    text = str(exc).strip()
    return f"{type(exc).__name__}: {text}" if text else type(exc).__name__
