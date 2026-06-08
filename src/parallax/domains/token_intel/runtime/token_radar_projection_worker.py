from __future__ import annotations

import asyncio
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, cast

from loguru import logger

from parallax.app.runtime.worker_base import WorkerBase
from parallax.app.runtime.worker_result import WorkerResult
from parallax.domains.token_intel._constants import (
    TOKEN_RADAR_DEFAULT_VENUE,
    TOKEN_RADAR_PROJECTION_VERSION,
    TOKEN_RADAR_VENUES,
)

DEFAULT_WINDOWS = ("5m", "1h", "4h", "24h")
DEFAULT_SCOPES = ("all", "matched")
DEFAULT_HOT_WINDOWS = ("5m",)
ADVISORY_LOCK_KEY = 2026051501

if TYPE_CHECKING:
    from parallax.domains.token_intel.services.token_radar_projection import TokenRadarProjection


class TokenRadarProjectionWorker(WorkerBase):
    SINGLE_WRITER_KEY = ADVISORY_LOCK_KEY

    def __init__(
        self,
        *,
        name: str,
        settings: Any,
        db: Any,
        telemetry: Any,
        wake_bus: Any | None = None,
        wake_waiter: Any | None = None,
        enqueue_narrative_admission: bool = True,
    ) -> None:
        super().__init__(
            name=name,
            settings=settings,
            db=db,
            telemetry=telemetry,
            wake_waiter=wake_waiter,
        )
        self.windows = tuple(getattr(settings, "windows", DEFAULT_WINDOWS) or DEFAULT_WINDOWS)
        self.scopes = tuple(getattr(settings, "scopes", DEFAULT_SCOPES) or DEFAULT_SCOPES)
        self.venues = tuple(getattr(settings, "venues", TOKEN_RADAR_VENUES) or TOKEN_RADAR_VENUES)
        hot_windows = tuple(getattr(settings, "hot_windows", DEFAULT_HOT_WINDOWS) or DEFAULT_HOT_WINDOWS)
        self.hot_windows = tuple(window for window in hot_windows if window in self.windows)
        self.limit = max(1, int(getattr(settings, "batch_size", 100) or 100))
        self.hot_interval_ms = int(self.interval_seconds * 1000)
        self.cold_interval_ms = int(float(getattr(settings, "cold_interval_seconds", 60.0) or 0) * 1000)
        self.wake_bus = wake_bus
        self.enqueue_narrative_admission = bool(enqueue_narrative_admission)
        self._cursor = 0

    async def run_once(self, *, now_ms: int | None = None) -> WorkerResult:
        result = await asyncio.to_thread(self.rebuild_once, now_ms=now_ms)
        failed = sum(1 for item in result["windows"].values() if str(item.get("status") or "") == "failed")
        skipped = 1 if str(result.get("status") or "") == "idle" else 0
        processed = 0 if skipped else max(0, len(result["windows"]) - failed)
        return WorkerResult(
            processed=processed,
            failed=failed,
            skipped=skipped,
            notes={
                "computed_at_ms": result["computed_at_ms"],
                "rows_written": result["rows_written"],
                "source_rows": result["source_rows"],
                "window": result.get("window"),
                "scope": result.get("scope"),
                "status": result.get("status"),
                "reason": result.get("reason"),
                "claimed": result.get("claimed"),
                "catch_up_enqueued": result.get("catch_up_enqueued"),
                "windows": result["windows"],
            },
        )

    def rebuild_once(
        self,
        *,
        now_ms: int | None = None,
        windows: tuple[str, ...] | None = None,
        scopes: tuple[str, ...] | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        computed_at_ms = int(now_ms if now_ms is not None else _now_ms())
        self.last_error = None
        original_windows = self.windows
        original_scopes = self.scopes
        original_venues = self.venues
        original_hot_windows = self.hot_windows
        original_limit = self.limit
        if windows is not None:
            self.windows = tuple(windows)
            self.hot_windows = tuple(window for window in self.hot_windows if window in self.windows)
        if scopes is not None:
            self.scopes = tuple(scopes)
        if limit is not None:
            self.limit = max(1, int(limit))
        try:
            return self._rebuild_once(computed_at_ms=computed_at_ms)
        finally:
            self.windows = original_windows
            self.scopes = original_scopes
            self.venues = original_venues
            self.hot_windows = original_hot_windows
            self.limit = original_limit

    def _rebuild_once(self, *, computed_at_ms: int) -> dict[str, Any]:
        try:
            with self._worker_session() as repos:
                publication_work_items = self._next_work_items(
                    publication_state=_latest_publication_state_from_repos(
                        repos,
                        windows=self.windows,
                        scopes=self.scopes,
                        venues=self.venues,
                    ),
                    computed_at_ms=computed_at_ms,
                )[0]
                target_claims = repos.token_radar_dirty_targets.claim_due(
                    limit=self.limit,
                    lease_ms=_dirty_target_lease_ms(),
                    now_ms=computed_at_ms,
                    lease_owner=self.name,
                    commit=True,
                )
                source_dirty_repo = getattr(repos, "token_radar_source_dirty_events", None)
                source_claims = (
                    source_dirty_repo.claim_due(
                        limit=self.limit,
                        lease_ms=_dirty_target_lease_ms(),
                        now_ms=computed_at_ms,
                        lease_owner=self.name,
                        commit=True,
                    )
                    if source_dirty_repo is not None
                    else []
                )
            has_claims = bool(target_claims or source_claims)
            if publication_work_items or has_claims:
                score_work_items = _dedupe_work_items(
                    _configured_work_items(windows=self.windows, scopes=self.scopes, venues=self.venues)
                    if has_claims
                    else publication_work_items
                )
                publish_work_items = _dedupe_work_items(publication_work_items)
                with self._worker_session() as repos:
                    projection = _projection_class()(
                        repos=repos,
                        enqueue_narrative_admission=self.enqueue_narrative_admission,
                    )
                    metadata_work_items = score_work_items or publish_work_items
                    rebuild_kwargs: dict[str, Any] = {
                        "windows": tuple(dict.fromkeys(window for window, _scope, _venue in metadata_work_items)),
                        "scopes": tuple(dict.fromkeys(scope for _window, scope, _venue in metadata_work_items)),
                        "work_items": _service_work_items(publish_work_items),
                        "now_ms": computed_at_ms,
                        "limit": self.limit,
                        "rank_limit": self.limit,
                        "lease_owner": self.name,
                        "claimed_targets": tuple(dict(claim) for claim in target_claims),
                        "claimed_source_events": tuple(dict(claim) for claim in source_claims),
                    }
                    if has_claims:
                        rebuild_kwargs["score_work_items"] = _service_work_items(score_work_items)
                    venues = tuple(dict.fromkeys(venue for _window, _scope, venue in metadata_work_items))
                    if venues != (TOKEN_RADAR_DEFAULT_VENUE,):
                        rebuild_kwargs["venues"] = venues
                    result = projection.rebuild_dirty_targets(**rebuild_kwargs)
            else:
                result = _idle_result(computed_at_ms=computed_at_ms)
        except Exception as exc:
            self.last_error = str(exc)
            logger.exception(f"token radar dirty target projection failed: error={exc}")
            result = {
                "computed_at_ms": computed_at_ms,
                "rows_written": 0,
                "source_rows": 0,
                "status": "failed",
                "error": str(exc),
                "claimed": 0,
                "catch_up_enqueued": 0,
                "windows": {},
            }

        result = self._finalize_result(result=result, computed_at_ms=computed_at_ms)

        if str(result.get("status") or "") == "failed":
            self.last_error = self.last_error or str(result.get("error") or "token radar projection failed")

        for key, window_result in result["windows"].items():
            if str(window_result.get("status") or "") != "ready" or self.wake_bus is None:
                continue
            parts = str(key).split(":", 2)
            window, scope = parts[0], parts[1]
            self.wake_bus.notify_token_radar_updated(window=window, scope=scope)
        return result

    def _finalize_result(self, *, result: dict[str, Any], computed_at_ms: int) -> dict[str, Any]:
        result.setdefault("computed_at_ms", computed_at_ms)
        result.setdefault("rows_written", 0)
        result.setdefault("source_rows", 0)
        result.setdefault("windows", {})
        result.setdefault("claimed", 0)
        result.setdefault("catch_up_enqueued", 0)
        result["window"] = self.windows[0] if self.windows else None
        result["scope"] = self.scopes[0] if self.scopes else None
        result["venue"] = self.venues[0] if self.venues else None
        return result

    def _next_work_items(
        self,
        *,
        publication_state: dict[tuple[str, str, str], dict[str, Any]],
        computed_at_ms: int,
    ) -> tuple[list[tuple[str, str, str]], tuple[str, str, str] | None]:
        hot_items = self._hot_work_items(
            publication_state=publication_state,
            computed_at_ms=computed_at_ms,
        )
        background_item = self._next_background_window_scope(
            publication_state=publication_state,
            computed_at_ms=computed_at_ms,
        )
        missing_items = self._missing_work_items(publication_state, computed_at_ms=computed_at_ms)
        work_items = list(hot_items)
        work_items.extend(missing_items)
        if background_item is not None and background_item not in work_items:
            work_items.append(background_item)
        work_items = _dedupe_work_items(work_items)
        if not work_items:
            return [], None
        return work_items, background_item or work_items[-1]

    def _next_background_window_scope(
        self,
        *,
        publication_state: dict[tuple[str, str, str], dict[str, Any]],
        computed_at_ms: int,
    ) -> tuple[str, str, str] | None:
        work_items = [
            (window, scope, venue)
            for window in self.windows
            if window not in self.hot_windows
            for scope in self.scopes
            for venue in self.venues
        ]
        if not work_items:
            return None
        for _ in range(len(work_items)):
            item = work_items[self._cursor % len(work_items)]
            self._cursor += 1
            if _publication_due(
                publication_state.get(item),
                computed_at_ms=computed_at_ms,
                interval_ms=self.cold_interval_ms,
                failed_retry_ms=self.cold_interval_ms,
            ):
                return item
        return None

    def _hot_work_items(
        self,
        *,
        publication_state: dict[tuple[str, str, str], dict[str, Any]],
        computed_at_ms: int,
    ) -> list[tuple[str, str, str]]:
        due: list[tuple[str, str, str]] = []
        for window in self.hot_windows:
            for scope in self.scopes:
                for venue in self.venues:
                    item = (window, scope, venue)
                    if _publication_due(
                        publication_state.get(item),
                        computed_at_ms=computed_at_ms,
                        interval_ms=self.hot_interval_ms,
                        failed_retry_ms=self.cold_interval_ms,
                    ):
                        due.append(item)
        return due

    def _latest_publication_state(self) -> dict[tuple[str, str, str], dict[str, Any]]:
        with self._worker_session() as repos:
            return _latest_publication_state_from_repos(
                repos,
                windows=self.windows,
                scopes=self.scopes,
                venues=self.venues,
            )

    def _missing_work_items(
        self,
        publication_state: dict[tuple[str, str, str], dict[str, Any]],
        *,
        computed_at_ms: int,
    ) -> list[tuple[str, str, str]]:
        missing: list[tuple[str, str, str]] = []
        for window in self.windows:
            if window not in self.hot_windows:
                continue
            for scope in self.scopes:
                for venue in self.venues:
                    item = (window, scope, venue)
                    item_state = publication_state.get(item, {})
                    status = str(item_state.get("latest_attempt_status") or "")
                    if status == "ready":
                        continue
                    interval_ms = self.hot_interval_ms if window in self.hot_windows else self.cold_interval_ms
                    if not _publication_due(
                        item_state or None,
                        computed_at_ms=computed_at_ms,
                        interval_ms=interval_ms,
                        failed_retry_ms=self.cold_interval_ms,
                    ):
                        continue
                    missing.append(item)
        return missing

    def _mark_publication_failed(
        self,
        *,
        window: str,
        scope: str,
        venue: str = TOKEN_RADAR_DEFAULT_VENUE,
        computed_at_ms: int,
        error: str,
    ) -> None:
        try:
            with self._worker_session() as repos:
                repos.token_radar.mark_publication_failed(
                    projection_version=TOKEN_RADAR_PROJECTION_VERSION,
                    window=window,
                    scope=scope,
                    venue=venue,
                    generation_id=f"worker-failed:{window}:{scope}:{venue}:{computed_at_ms}",
                    started_at_ms=computed_at_ms,
                    finished_at_ms=_now_ms(),
                    error=error,
                    commit=True,
                )
        except Exception as exc:  # pragma: no cover - diagnostic side path
            logger.exception(f"failed to mark token radar publication failure: {exc}")

    @contextmanager
    def _worker_session(self) -> Iterator[Any]:
        with self.db.worker_session(
            self.name,
            statement_timeout_seconds=getattr(self.settings, "statement_timeout_seconds", None),
        ) as repos:
            yield repos


def _now_ms() -> int:
    return int(time.time() * 1000)


def _idle_result(*, computed_at_ms: int) -> dict[str, Any]:
    return {
        "computed_at_ms": computed_at_ms,
        "rows_written": 0,
        "source_rows": 0,
        "status": "idle",
        "reason": "no_due_work_items",
        "claimed": 0,
        "catch_up_enqueued": 0,
        "windows": {},
    }


def _publication_due(
    state: dict[str, Any] | None,
    *,
    computed_at_ms: int,
    interval_ms: int,
    failed_retry_ms: int,
) -> bool:
    if not state:
        return True

    status = str(state.get("latest_attempt_status") or "")
    published_at_ms = _state_ms(state, "last_published_at_ms", "current_published_at_ms")

    if status == "ready":
        if published_at_ms is None:
            return True
        return _elapsed_due(
            computed_at_ms=computed_at_ms,
            since_ms=published_at_ms,
            interval_ms=interval_ms,
        )

    if status == "failed":
        if published_at_ms is not None or state.get("current_generation_id") is not None:
            retry_since_ms = (
                _state_ms(
                    state,
                    "latest_attempt_finished_at_ms",
                    "updated_at_ms",
                    "latest_attempt_started_at_ms",
                )
                or published_at_ms
            )
            return _elapsed_due(
                computed_at_ms=computed_at_ms,
                since_ms=retry_since_ms,
                interval_ms=failed_retry_ms,
            )
        failed_at_ms = _state_ms(
            state,
            "latest_attempt_finished_at_ms",
            "updated_at_ms",
            "latest_attempt_started_at_ms",
        )
        return failed_at_ms is None or _elapsed_due(
            computed_at_ms=computed_at_ms,
            since_ms=failed_at_ms,
            interval_ms=interval_ms,
        )

    if published_at_ms is None:
        return True
    return _elapsed_due(
        computed_at_ms=computed_at_ms,
        since_ms=published_at_ms,
        interval_ms=interval_ms,
    )


def _elapsed_due(*, computed_at_ms: int, since_ms: int | None, interval_ms: int) -> bool:
    if since_ms is None:
        return True
    return computed_at_ms - int(since_ms) >= max(0, int(interval_ms))


def _state_ms(state: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = state.get(key)
        if value is not None:
            return int(value)
    return None


def _dedupe_work_items(items: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    seen: set[tuple[str, str, str]] = set()
    out: list[tuple[str, str, str]] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _configured_work_items(
    *,
    windows: tuple[str, ...],
    scopes: tuple[str, ...],
    venues: tuple[str, ...],
) -> list[tuple[str, str, str]]:
    return [(window, scope, venue) for window in windows for scope in scopes for venue in venues]


def _service_work_items(items: list[tuple[str, str, str]]) -> tuple[tuple[str, ...], ...]:
    if all(venue == TOKEN_RADAR_DEFAULT_VENUE for _window, _scope, venue in items):
        return tuple((window, scope) for window, scope, _venue in items)
    return tuple(items)


def _latest_publication_state_from_repos(
    repos: Any,
    *,
    windows: tuple[str, ...],
    scopes: tuple[str, ...],
    venues: tuple[str, ...],
) -> dict[tuple[str, str, str], dict[str, Any]]:
    return cast(
        dict[tuple[str, str, str], dict[str, Any]],
        repos.token_radar.latest_publication_state(
            projection_version=TOKEN_RADAR_PROJECTION_VERSION,
            windows=windows,
            scopes=scopes,
            venues=venues,
        ),
    )


def _projection_class() -> type[TokenRadarProjection]:
    from parallax.domains.token_intel.services.token_radar_projection import TokenRadarProjection

    return TokenRadarProjection


def _dirty_target_lease_ms() -> int:
    from parallax.domains.token_intel.services.token_radar_projection import DIRTY_TARGET_LEASE_MS

    return DIRTY_TARGET_LEASE_MS
