from __future__ import annotations

import asyncio
import time
from typing import Any

from parallax.app.runtime.worker_base import WorkerBase
from parallax.app.runtime.worker_result import WorkerResult
from parallax.domains.asset_market.services.token_image_source_admission import (
    admit_token_image_sources,
    image_source_candidates_for_target,
)
from parallax.domains.asset_market.services.token_profile_current_projection import (
    project_token_profile_current,
)

SINGLE_WRITER_KEY = 2026051702


class TokenProfileCurrentWorker(WorkerBase):
    SINGLE_WRITER_KEY = SINGLE_WRITER_KEY

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
            statement_timeout_seconds=self.settings.statement_timeout_seconds,
        ) as repos:
            return rebuild_token_profile_current_once(
                repos=repos,
                now_ms=now_ms,
                limit=max(1, int(self.settings.batch_size)),
                lease_owner=self.name,
                lease_ms=max(1, int(self.settings.lease_ms)),
                retry_ms=max(1, int(self.settings.retry_ms)),
            )


def rebuild_token_profile_current_once(
    *,
    repos: Any,
    now_ms: int,
    limit: int,
    lease_owner: str,
    lease_ms: int,
    retry_ms: int,
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
    query = repos.source_query
    targets = _dedupe_targets(claims)
    result["targets_loaded"] = len(targets)
    asset_ids = [str(row["target_id"]) for row in targets if str(row.get("target_type") or "") == "Asset"]
    cex_token_ids = [str(row["target_id"]) for row in targets if str(row.get("target_type") or "") == "CexToken"]
    gmgn_openapi = query.gmgn_openapi_profiles(asset_ids)
    binance_web3 = query.binance_web3_profiles(asset_ids)
    gmgn_stream = query.gmgn_stream_profiles(asset_ids)
    okx_dex = query.okx_dex_profiles(asset_ids)
    cex_profiles = query.cex_token_profiles(cex_token_ids)
    image_candidates = _image_source_candidates_for_targets(
        targets=targets,
        gmgn_openapi=gmgn_openapi,
        binance_web3=binance_web3,
        gmgn_stream=gmgn_stream,
        okx_dex=okx_dex,
        cex_profiles=cex_profiles,
    )
    admission = admit_token_image_sources(repos=repos, candidates=image_candidates, now_ms=now_ms)
    _record_image_admission(result, admission.counts)
    for target in targets:
        target_id = str(target.get("target_id") or "")
        row = project_token_profile_current(
            target=target,
            gmgn_openapi=gmgn_openapi.get(target_id),
            binance_web3=binance_web3.get(target_id),
            gmgn_stream=gmgn_stream.get(target_id),
            okx_dex=okx_dex.get(target_id),
            cex_profile=cex_profiles.get(target_id),
            image_states_by_source_key=admission.image_states_by_source_key,
            computed_at_ms=now_ms,
        )
        if repos.token_profiles.upsert_current(row, commit=False):
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


def _image_source_candidates_for_targets(
    *,
    targets: list[dict[str, str]],
    gmgn_openapi: dict[str, dict[str, Any]],
    binance_web3: dict[str, dict[str, Any]],
    gmgn_stream: dict[str, dict[str, Any]],
    okx_dex: dict[str, dict[str, Any]],
    cex_profiles: dict[str, dict[str, Any]],
) -> list[Any]:
    candidates: list[Any] = []
    for target in targets:
        target_id = str(target.get("target_id") or "")
        candidates.extend(
            image_source_candidates_for_target(
                target=target,
                gmgn_openapi=gmgn_openapi.get(target_id),
                binance_web3=binance_web3.get(target_id),
                gmgn_stream=gmgn_stream.get(target_id),
                okx_dex=okx_dex.get(target_id),
                cex_profile=cex_profiles.get(target_id),
            )
        )
    return candidates


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


def _record_image_admission(result: dict[str, Any], counts: dict[str, int]) -> None:
    result["image_candidates"] += int(counts.get("candidates") or 0)
    result["image_sources_admitted"] += int(counts.get("admitted") or 0)
    result["image_ready_existing"] += int(counts.get("ready_existing") or 0)
    result["image_pending_existing"] += int(counts.get("pending_existing") or 0)
    result["image_error_existing"] += int(counts.get("error_existing") or 0)
    result["image_unsupported_existing"] += int(counts.get("unsupported_existing") or 0)
    result["image_dirty_existing"] += int(counts.get("dirty_existing") or 0)


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
        "image_candidates": 0,
        "image_sources_admitted": 0,
        "image_ready_existing": 0,
        "image_pending_existing": 0,
        "image_error_existing": 0,
        "image_unsupported_existing": 0,
        "image_dirty_existing": 0,
        "source_provider": {},
        "started_at_ms": int(now_ms),
        "finished_at_ms": int(now_ms),
    }


def _error_text(exc: BaseException) -> str:
    text = str(exc).strip()
    return f"{type(exc).__name__}: {text}" if text else type(exc).__name__
