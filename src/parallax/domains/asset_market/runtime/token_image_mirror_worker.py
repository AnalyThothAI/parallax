from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any, cast

from parallax.app.runtime.worker_base import WorkerBase
from parallax.app.runtime.worker_result import WorkerResult
from parallax.domains.asset_market.services.token_image_mirror import TokenImageMirrorService


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

    def _mirror_once(self, now_ms: int) -> dict[str, Any]:
        result = _empty_result(now_ms=now_ms)
        with self.db.worker_session(
            self.name,
            statement_timeout_seconds=float(self.settings.statement_timeout_seconds),
        ) as repos:
            claimed = repos.token_image_source_dirty_targets.claim_due(
                now_ms=now_ms,
                limit=max(1, int(self.settings.batch_size)),
                lease_owner=self.name,
                lease_ms=max(1, int(self.settings.lease_ms)),
                commit=True,
            )
            result["claimed"] = len(claimed)
            result["selected"] = len(claimed)
            result["targets_loaded"] = len(claimed)
            result["queue_depth"] = repos.token_image_source_dirty_targets.queue_depth(now_ms=now_ms)
            if not claimed:
                result["reason"] = "no_due_token_image_source_targets"
                result["finished_at_ms"] = int(now_ms)
                return result

            terminal = repos.token_image_assets.terminal_by_source_urls(_source_urls(claimed))
            terminal_claims = [claim for claim in claimed if str(claim.get("source_url") or "") in terminal]
            pending_claims = [claim for claim in claimed if str(claim.get("source_url") or "") not in terminal]
            result["ready_existing"] = sum(
                1
                for claim in terminal_claims
                if str(terminal[str(claim.get("source_url") or "")].get("status")) == "ready"
            )
            result["unsupported_existing"] = len(terminal_claims) - int(result["ready_existing"])
            with repos.transaction():
                if pending_claims:
                    result["pending_upserted"] = repos.token_image_assets.upsert_pending_sources(
                        _source_rows_from_claims(pending_claims),
                        now_ms=now_ms,
                        commit=False,
                    )
                    result["rows_written"] += int(result["pending_upserted"])
                if terminal_claims:
                    repos.token_image_source_dirty_targets.mark_done(terminal_claims, now_ms=now_ms, commit=False)
                    _enqueue_profile_current_for_claims(repos=repos, claims=terminal_claims, now_ms=now_ms)

        mirror_service = TokenImageMirrorService(
            repository=_TokenImageAssetSessionRepository(self.db, self.name, self.settings),
            app_home=self.app_home,
            retry_ms=max(1, int(self.settings.retry_ms)),
        )
        for source_url, source_claims in _claims_by_source_url(pending_claims).items():
            source_row = _source_row_from_claim(source_claims[0])
            try:
                mirror_result = mirror_service.mirror_source(source_row, now_ms=now_ms)
            except Exception as exc:
                mirror_result = {"status": "error", "error": _error_text(exc), "source_url": source_url}
            _record_mirror_result(result, mirror_result)
            if _mirror_result_is_complete(mirror_result):
                self._mark_source_claims_done(source_claims, now_ms=now_ms)
            else:
                self._mark_source_claims_error(
                    source_claims,
                    error=str(mirror_result.get("error") or "token_image_mirror_failed"),
                    now_ms=now_ms,
                )

        result["finished_at_ms"] = int(now_ms)
        return result

    def _mark_source_claims_done(self, claims: list[dict[str, Any]], *, now_ms: int) -> None:
        with (
            self.db.worker_session(
                self.name,
                statement_timeout_seconds=float(self.settings.statement_timeout_seconds),
            ) as repos,
            repos.transaction(),
        ):
            repos.token_image_source_dirty_targets.mark_done(claims, now_ms=now_ms, commit=False)
            _enqueue_profile_current_for_claims(repos=repos, claims=claims, now_ms=now_ms)

    def _mark_source_claims_error(self, claims: list[dict[str, Any]], *, error: str, now_ms: int) -> None:
        with (
            self.db.worker_session(
                self.name,
                statement_timeout_seconds=float(self.settings.statement_timeout_seconds),
            ) as repos,
            repos.transaction(),
        ):
            repos.token_image_source_dirty_targets.mark_error(
                claims,
                error=error,
                retry_ms=max(1, int(self.settings.retry_ms)),
                max_attempts=int(self.settings.max_attempts),
                worker_name=self.name,
                now_ms=now_ms,
                commit=False,
            )


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
    ) -> dict[str, Any]:
        with (
            self.db.worker_session(
                self.worker_name,
                statement_timeout_seconds=float(self.settings.statement_timeout_seconds),
            ) as repos,
            repos.transaction(),
        ):
            return cast(
                dict[str, Any],
                repos.token_image_assets.mark_ready(
                    source_url=source_url,
                    media_type=media_type,
                    file_extension=file_extension,
                    content_sha256=content_sha256,
                    byte_size=byte_size,
                    storage_path=storage_path,
                    now_ms=now_ms,
                    commit=False,
                ),
            )

    def mark_error(
        self,
        source_url: str,
        error: str,
        now_ms: int,
        retry_ms: int,
    ) -> None:
        with (
            self.db.worker_session(
                self.worker_name,
                statement_timeout_seconds=float(self.settings.statement_timeout_seconds),
            ) as repos,
            repos.transaction(),
        ):
            repos.token_image_assets.mark_error(
                source_url=source_url,
                error=error,
                now_ms=now_ms,
                retry_ms=retry_ms,
                commit=False,
            )

    def mark_unsupported(
        self,
        source_url: str,
        error: str,
        now_ms: int,
    ) -> None:
        with (
            self.db.worker_session(
                self.worker_name,
                statement_timeout_seconds=float(self.settings.statement_timeout_seconds),
            ) as repos,
            repos.transaction(),
        ):
            repos.token_image_assets.mark_unsupported(
                source_url=source_url,
                error=error,
                now_ms=now_ms,
                commit=False,
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


def _mirror_result_is_complete(mirror_result: dict[str, Any]) -> bool:
    status = str(mirror_result.get("status") or "")
    error = str(mirror_result.get("error") or "")
    return status in {"ready", "unsupported"} or error.startswith("unsupported_")


def _source_urls(claims: list[dict[str, Any]]) -> list[str]:
    return list(dict.fromkeys(str(claim.get("source_url") or "") for claim in claims if claim.get("source_url")))


def _claims_by_source_url(claims: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for claim in claims:
        source_url = str(claim.get("source_url") or "")
        if source_url:
            grouped.setdefault(source_url, []).append(claim)
    return grouped


def _source_rows_from_claims(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows_by_url: dict[str, dict[str, Any]] = {}
    for claim in claims:
        row = _source_row_from_claim(claim)
        rows_by_url[row["source_url"]] = row
    return list(rows_by_url.values())


def _source_row_from_claim(claim: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_url": str(claim.get("source_url") or ""),
        "source_provider": str(claim.get("source_provider") or ""),
        "source_kind": str(claim.get("source_kind") or ""),
        "raw_ref_json": claim.get("raw_ref_json") or {},
    }


def _enqueue_profile_current_for_claims(*, repos: Any, claims: list[dict[str, Any]], now_ms: int) -> None:
    targets = [
        {
            "target_type": str(claim.get("target_type") or ""),
            "target_id": str(claim.get("target_id") or ""),
            "source_watermark_ms": int(claim.get("source_watermark_ms") or now_ms),
            "priority": 30,
        }
        for claim in claims
        if claim.get("target_type") and claim.get("target_id")
    ]
    if targets:
        repos.token_profile_current_dirty_targets.enqueue_targets(
            targets,
            reason="token_image_source_completed",
            now_ms=now_ms,
            commit=False,
        )


def _error_text(exc: BaseException) -> str:
    text = str(exc).strip()
    return f"{type(exc).__name__}: {text}" if text else type(exc).__name__


def _empty_result(*, now_ms: int) -> dict[str, Any]:
    return {
        "selected": 0,
        "pending_upserted": 0,
        "ready_existing": 0,
        "unsupported_existing": 0,
        "claimed": 0,
        "queue_depth": 0,
        "source_rows_scanned": 0,
        "targets_loaded": 0,
        "rows_written": 0,
        "mirrored": 0,
        "error": 0,
        "unsupported": 0,
        "started_at_ms": int(now_ms),
        "finished_at_ms": int(now_ms),
    }
