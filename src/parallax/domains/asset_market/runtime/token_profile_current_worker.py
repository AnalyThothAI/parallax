from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
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
                limit=_required_positive_int(
                    self.settings.batch_size,
                    error_code="token_profile_current_batch_size_required",
                ),
                lease_owner=self.name,
                lease_ms=_required_positive_int(
                    self.settings.lease_ms,
                    error_code="token_profile_current_lease_ms_required",
                ),
                retry_ms=_required_positive_int(
                    self.settings.retry_ms,
                    error_code="token_profile_current_retry_ms_required",
                ),
                max_attempts=_required_positive_int(
                    self.settings.max_attempts,
                    error_code="token_profile_current_max_attempts_required",
                ),
            )


def rebuild_token_profile_current_once(
    *,
    repos: Any,
    now_ms: int,
    limit: int,
    lease_owner: str,
    lease_ms: int,
    retry_ms: int,
    max_attempts: int,
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

    valid_claims: list[tuple[dict[str, Any], dict[str, str]]] = []
    for claim in claims:
        try:
            target = _required_claim(claim, lease_owner=lease_owner)
        except Exception as exc:
            result["error"] += 1
            result["last_error"] = _mark_claim_error(
                repos=repos,
                claim=claim,
                exc=exc,
                now_ms=now_ms,
                retry_ms=retry_ms,
                max_attempts=max_attempts,
                lease_owner=lease_owner,
            )
        else:
            valid_claims.append((claim, target))

    shared_sources: _ClaimedTokenProfileSources | None = None
    if valid_claims:
        try:
            with repos.transaction():
                shared_sources = _load_claimed_token_profile_sources(
                    repos=repos,
                    claims=[claim for claim, _target in valid_claims],
                    result=result,
                )
        except Exception:
            # A batch decoder can fail because of one persisted source row. Fall
            # back to exact target loads so that row cannot poison valid peers.
            shared_sources = None

    for claim, target in valid_claims:
        try:
            with repos.transaction():
                sources = shared_sources or _load_claimed_token_profile_sources(
                    repos=repos,
                    claims=[claim],
                    result=result,
                )
                admission = admit_token_image_sources(
                    repos=repos,
                    candidates=_image_source_candidates_for_targets(
                        targets=[target],
                        gmgn_openapi=sources.gmgn_openapi,
                        binance_web3=sources.binance_web3,
                        gmgn_stream=sources.gmgn_stream,
                        okx_dex=sources.okx_dex,
                        cex_profiles=sources.cex_profiles,
                    ),
                    now_ms=now_ms,
                )
                row = _project_claimed_token_profile(
                    target=target,
                    sources=sources,
                    image_states_by_source_key=admission.image_states_by_source_key,
                    now_ms=now_ms,
                )
                changed = repos.token_profiles.upsert_current(row, commit=False)
                done = repos.token_profile_current_dirty_targets.mark_done([claim], now_ms=now_ms, commit=False)
                if done != 1:
                    raise RuntimeError("token_profile_current_dirty_target_stale_completion")
            result["rows_written"] += int(bool(changed))
            _record_image_admission(result, admission.counts)
            _record_row(result, row)
        except Exception as exc:
            error = _mark_claim_error(
                repos=repos,
                claim=claim,
                exc=exc,
                now_ms=now_ms,
                retry_ms=retry_ms,
                max_attempts=max_attempts,
                lease_owner=lease_owner,
            )
            result["error"] += 1
            result["last_error"] = error
    result["finished_at_ms"] = int(now_ms)
    return result


@dataclass(frozen=True, slots=True)
class _ClaimedTokenProfileSources:
    gmgn_openapi: dict[str, dict[str, Any]]
    binance_web3: dict[str, dict[str, Any]]
    gmgn_stream: dict[str, dict[str, Any]]
    okx_dex: dict[str, dict[str, Any]]
    cex_profiles: dict[str, dict[str, Any]]


def _load_claimed_token_profile_sources(
    *,
    repos: Any,
    claims: list[dict[str, Any]],
    result: dict[str, Any],
) -> _ClaimedTokenProfileSources:
    query = repos.source_query
    targets = _dedupe_targets(claims)
    asset_ids = [str(row["target_id"]) for row in targets if str(row.get("target_type") or "") == "Asset"]
    cex_token_ids = [str(row["target_id"]) for row in targets if str(row.get("target_type") or "") == "CexToken"]
    gmgn_openapi = query.gmgn_openapi_profiles(asset_ids)
    binance_web3 = query.binance_web3_profiles(asset_ids)
    gmgn_stream = query.gmgn_stream_profiles(asset_ids)
    okx_dex = query.okx_dex_profiles(asset_ids)
    cex_profiles = query.cex_token_profiles(cex_token_ids)
    result["targets_loaded"] += len(targets)
    return _ClaimedTokenProfileSources(
        gmgn_openapi=gmgn_openapi,
        binance_web3=binance_web3,
        gmgn_stream=gmgn_stream,
        okx_dex=okx_dex,
        cex_profiles=cex_profiles,
    )


def _project_claimed_token_profile(
    *,
    target: dict[str, str],
    sources: _ClaimedTokenProfileSources,
    image_states_by_source_key: dict[tuple[str, str, str], dict[str, Any]],
    now_ms: int,
) -> dict[str, Any]:
    target_id = target["target_id"]
    return project_token_profile_current(
        target=target,
        gmgn_openapi=sources.gmgn_openapi.get(target_id),
        binance_web3=sources.binance_web3.get(target_id),
        gmgn_stream=sources.gmgn_stream.get(target_id),
        okx_dex=sources.okx_dex.get(target_id),
        cex_profile=sources.cex_profiles.get(target_id),
        image_states_by_source_key=image_states_by_source_key,
        computed_at_ms=now_ms,
    )


def _dedupe_targets(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    targets: dict[tuple[str, str], dict[str, str]] = {}
    for row in rows:
        target = _required_target(row)
        targets[(target["target_type"], target["target_id"])] = target
    return list(targets.values())


def _required_target(row: dict[str, Any]) -> dict[str, str]:
    target_type = str(row.get("target_type") or "").strip()
    target_id = str(row.get("target_id") or "").strip()
    if not target_type or not target_id:
        raise ValueError("token_profile_current_dirty_target_identity_required")
    return {"target_type": target_type, "target_id": target_id}


def _required_claim(row: dict[str, Any], *, lease_owner: str) -> dict[str, str]:
    target = _required_target(row)
    if not str(row.get("payload_hash") or "").strip():
        raise ValueError("token_profile_current_dirty_target_payload_hash_required")
    claimed_owner = str(row.get("lease_owner") or "").strip()
    if not claimed_owner or claimed_owner != str(lease_owner):
        raise ValueError("token_profile_current_dirty_target_lease_owner_required")
    attempt_count = row.get("attempt_count")
    if isinstance(attempt_count, bool) or not isinstance(attempt_count, int) or attempt_count <= 0:
        raise ValueError("token_profile_current_dirty_target_attempt_count_required")
    return target


def _mark_claim_error(
    *,
    repos: Any,
    claim: dict[str, Any],
    exc: BaseException,
    now_ms: int,
    retry_ms: int,
    max_attempts: int,
    lease_owner: str,
) -> str:
    error = _error_text(exc)
    try:
        with repos.transaction():
            changed = repos.token_profile_current_dirty_targets.mark_error(
                [claim],
                error=error,
                now_ms=now_ms,
                retry_ms=retry_ms,
                max_attempts=max_attempts,
                worker_name=lease_owner,
                commit=False,
            )
            if changed != 1:
                raise RuntimeError("token_profile_current_dirty_target_stale_error_completion")
    except Exception as completion_exc:
        return f"{error}; mark_error_failed={_error_text(completion_exc)}"
    return error


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
    result["image_terminal_existing"] += int(counts.get("terminal_existing") or 0)


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
        "image_terminal_existing": 0,
        "source_provider": {},
        "started_at_ms": int(now_ms),
        "finished_at_ms": int(now_ms),
    }


def _required_positive_int(value: Any, *, error_code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(error_code)
    return int(value)


def _error_text(exc: BaseException) -> str:
    text = str(exc).strip()
    return f"{type(exc).__name__}: {text}" if text else type(exc).__name__
