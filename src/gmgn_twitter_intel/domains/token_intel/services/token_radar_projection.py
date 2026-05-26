from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Mapping
from contextlib import AbstractContextManager
from typing import Any, cast

from gmgn_twitter_intel.domains.narrative_intel.interfaces import NARRATIVE_SCHEMA_VERSION
from gmgn_twitter_intel.domains.token_intel._constants import (
    TOKEN_RADAR_FACTOR_FAMILIES,
    TOKEN_RADAR_PROJECTION_NAME,
    TOKEN_RADAR_PROJECTION_VERSION,
    TOKEN_RADAR_SOURCE_TABLE,
    WINDOW_MS,
)
from gmgn_twitter_intel.domains.token_intel.queries.token_radar_rank_source_query import TokenRadarSourceRequest
from gmgn_twitter_intel.domains.token_intel.repositories.projection_repository import ProjectionRepository
from gmgn_twitter_intel.domains.token_intel.repositories.token_radar_repository import TOKEN_RADAR_RANK_INPUT_VERSION
from gmgn_twitter_intel.domains.token_intel.scoring.cross_section_normalizer import (
    MIN_COHORT_SIZE,
    NORMALIZER_VERSION,
    rank_factors_within_cohort,
    weighted_rank_score,
)
from gmgn_twitter_intel.domains.token_intel.scoring.factor_cohort import (
    COHORT_DEFINITION_VERSION,
    is_active_cohort_member,
)
from gmgn_twitter_intel.domains.token_intel.scoring.factor_snapshot import (
    build_token_factor_snapshot,
)
from gmgn_twitter_intel.domains.token_intel.scoring.factor_snapshot_contract import require_token_factor_snapshot
from gmgn_twitter_intel.domains.token_intel.scoring.token_radar_feature_builder import (
    BASELINE_SLOT_COUNT,
    build_radar_features,
)
from gmgn_twitter_intel.domains.token_intel.services.atomic_mention import HIGH_CONF_RESOLUTION_STATUSES, KOL_TIER_TAGS

PROJECTION_VERSION = TOKEN_RADAR_PROJECTION_VERSION
STALE_RUNNING_PROJECTION_MS = 10 * 60 * 1000
STALE_RUNNING_CLEANUP_INTERVAL_MS = STALE_RUNNING_PROJECTION_MS
MAX_ANALYSIS_LOOKBACK_MS = 48 * 60 * 60 * 1000
DEX_DECISION_FLOORS = {
    "holders": 100,
    "liquidity_usd": 25_000.0,
    "market_cap_usd": 50_000.0,
}
LIVE_LATEST_MAX_AGE_MS = 90 * 1000
FRESH_LATEST_MAX_AGE_MS = 5 * 60 * 1000
DIRTY_TARGET_LEASE_MS = 2 * 60 * 1000
DIRTY_TARGET_RETRY_MS = 30 * 1000
PULSE_TRIGGER_WINDOWS = frozenset({"1h", "4h"})
PULSE_TRIGGER_SCOPES = frozenset({"all", "matched"})
NARRATIVE_ADMISSION_WINDOWS = frozenset({"1h"})
NARRATIVE_ADMISSION_SCOPE = "all"


class TokenRadarProjection:
    def __init__(
        self,
        *,
        repos: Any,
    ) -> None:
        self.repos = repos
        self._last_stale_cleanup_at_ms: dict[tuple[str, str], int] = {}

    def rebuild(self, *, window: str, scope: str, now_ms: int | None = None, limit: int = 100) -> dict[str, Any]:
        computed_at_ms = int(now_ms or time.time() * 1000)
        return self.refresh_rank_set(window=window, scope=scope, now_ms=computed_at_ms, limit=limit)

    def rebuild_dirty_targets(
        self,
        *,
        windows: tuple[str, ...] = (),
        scopes: tuple[str, ...] = (),
        work_items: tuple[tuple[str, str], ...] | None = None,
        now_ms: int | None = None,
        limit: int = 100,
        rank_limit: int = 100,
        lease_owner: str = "token_radar_projection",
    ) -> dict[str, Any]:
        computed_at_ms = int(now_ms or time.time() * 1000)
        resolved_work_items = _resolve_work_items(windows=windows, scopes=scopes, work_items=work_items)
        readiness = self.repos.token_radar.rank_input_readiness_for_work_items(
            projection_version=PROJECTION_VERSION,
            work_items=resolved_work_items,
        )
        if not readiness.ready:
            return {
                "computed_at_ms": computed_at_ms,
                "rows_written": 0,
                "source_rows": 0,
                "claimed": 0,
                "windows": {},
                "status": "blocked",
                "blocked_precondition": True,
                "reason": "token_radar_rank_inputs_require_full_rebuild",
                "stale_rank_input_count": int(readiness.stale_count),
                "stale_rank_input_counts": _readiness_counts_by_key(readiness.stale_by_work_item),
            }
        claims = self.repos.token_radar_dirty_targets.claim_due(
            limit=limit,
            lease_ms=DIRTY_TARGET_LEASE_MS,
            now_ms=computed_at_ms,
            lease_owner=lease_owner,
            commit=True,
        )
        result: dict[str, Any] = {
            "computed_at_ms": computed_at_ms,
            "rows_written": 0,
            "source_rows": 0,
            "claimed": len(claims),
            "windows": {},
            "status": "idle" if not claims else "ready",
        }
        if not claims:
            return result

        source_requests = _source_requests_for_targets(claims, resolved_work_items, now_ms=computed_at_ms)
        self.repos.token_radar_rank_sources.populate_edges_for_requests(
            source_requests,
            projected_at_ms=computed_at_ms,
            commit=False,
        )
        rows_by_request = self.repos.token_radar_rank_sources.load_rows_for_requests(source_requests)
        requests_by_target = _source_requests_by_target(source_requests)
        touched: set[tuple[str, str]] = set()
        successful_claims: list[dict[str, str | int]] = []
        failures = 0
        first_error: str | None = None
        for claim_index, claim in enumerate(claims):
            claim_key = _claim_key(claim)
            try:
                for request in requests_by_target.get(claim_index, []):
                    score_result = self._project_source_request(
                        request=request,
                        target=claim,
                        source_rows=rows_by_request.get(request.request_key, []),
                        now_ms=computed_at_ms,
                    )
                    result["source_rows"] += int(score_result.get("source_rows") or 0)
                    touched.add((request.window, request.scope))
                successful_claims.append(claim_key)
            except Exception as exc:
                failures += 1
                first_error = first_error or str(exc)
                self.repos.token_radar_dirty_targets.mark_error(
                    [claim_key],
                    error=str(exc),
                    retry_ms=DIRTY_TARGET_RETRY_MS,
                    now_ms=computed_at_ms,
                    commit=True,
                )

        for window, scope in sorted(touched):
            key = f"{window}:{scope}"
            try:
                rank_result = self.refresh_rank_set(
                    window=window,
                    scope=scope,
                    now_ms=computed_at_ms,
                    limit=rank_limit,
                )
                if str(rank_result.get("status") or "") != "ready":
                    raise RuntimeError(
                        f"rank refresh did not publish current rows: {rank_result.get('status') or 'unknown'}"
                    )
            except Exception as exc:
                failures += 1
                first_error = first_error or str(exc)
                rank_result = {
                    "rows_written": 0,
                    "source_rows": 0,
                    "computed_at_ms": computed_at_ms,
                    "status": "failed",
                    "error": str(exc),
                }
            result["windows"][key] = rank_result
            result["rows_written"] += int(rank_result.get("rows_written") or 0)

        if failures:
            result["status"] = "failed"
            errors = [str(item.get("error")) for item in result["windows"].values() if item.get("error")]
            result["error"] = errors[0] if errors else "dirty target projection failed"
            if successful_claims:
                self.repos.token_radar_dirty_targets.mark_error(
                    successful_claims,
                    error=first_error or str(result["error"]),
                    retry_ms=DIRTY_TARGET_RETRY_MS,
                    now_ms=computed_at_ms,
                    commit=True,
                )
        elif successful_claims:
            self.repos.token_radar_dirty_targets.mark_done(successful_claims, now_ms=computed_at_ms, commit=True)
        return result

    def rebuild_rank_inputs_full(
        self,
        *,
        windows: tuple[str, ...],
        scopes: tuple[str, ...],
        now_ms: int | None = None,
        batch_size: int = 5000,
    ) -> dict[str, Any]:
        computed_at_ms = int(now_ms or time.time() * 1000)
        parsed_batch_size = max(1, int(batch_size))
        legacy_rows_seen = 0
        source_rows = 0
        rows_written = 0
        touched: set[tuple[str, str]] = set()
        seen_keys: set[tuple[str, str, str, str, str]] = set()

        while True:
            rebuild_keys = self.repos.token_radar.list_rank_input_rebuild_keys(
                projection_version=PROJECTION_VERSION,
                windows=windows,
                scopes=scopes,
                limit=parsed_batch_size,
            )
            if not rebuild_keys:
                break
            legacy_rows_seen += len(rebuild_keys)
            for key in rebuild_keys:
                stable_key = (
                    str(key.get("window") or ""),
                    str(key.get("scope") or ""),
                    str(key.get("lane") or ""),
                    str(key.get("target_type_key") or ""),
                    str(key.get("identity_id") or ""),
                )
                if stable_key in seen_keys:
                    raise RuntimeError("rank input rebuild made no progress for legacy target feature")
                seen_keys.add(stable_key)
            source_requests = _source_requests_for_rank_rebuild_keys(rebuild_keys, now_ms=computed_at_ms)
            self.repos.token_radar_rank_sources.populate_edges_for_requests(
                source_requests,
                projected_at_ms=computed_at_ms,
                commit=False,
            )
            rows_by_request = self.repos.token_radar_rank_sources.load_rows_for_requests(source_requests)
            requests_by_key = {request.request_key: request for request in source_requests}
            with _transaction_context(self.repos.conn):
                for key in rebuild_keys:
                    request = requests_by_key[_rank_rebuild_request_key(key)]
                    score_result = self._project_source_request(
                        request=request,
                        target=key,
                        source_rows=rows_by_request.get(request.request_key, []),
                        now_ms=computed_at_ms,
                    )
                    source_rows += int(score_result.get("source_rows") or 0)
                    rows_written += int(score_result.get("rows_written") or 0)
                    touched.add((request.window, request.scope))

        window_results: dict[str, dict[str, Any]] = {}
        for window, scope in sorted(touched):
            rank_result = self.refresh_rank_set(
                window=window,
                scope=scope,
                now_ms=computed_at_ms,
                limit=parsed_batch_size,
            )
            window_results[f"{window}:{scope}"] = rank_result
            if str(rank_result.get("status") or "") != "ready":
                raise RuntimeError(f"rank input rebuild refresh failed for {window}:{scope}")

        return {
            "status": "ready",
            "computed_at_ms": computed_at_ms,
            "legacy_rows_seen": legacy_rows_seen,
            "source_rows": source_rows,
            "rows_written": rows_written,
            "windows": window_results,
        }

    def _project_source_request(
        self,
        *,
        request: TokenRadarSourceRequest,
        target: dict[str, Any],
        source_rows: list[dict[str, Any]],
        now_ms: int,
    ) -> dict[str, Any]:
        window = request.window
        scope = request.scope
        window_ms = WINDOW_MS.get(window, WINDOW_MS["1h"])
        score_since_ms = int(request.score_since_ms)
        total_window_events = len(
            {str(row["event_id"]) for row in source_rows if int(row.get("received_at_ms") or 0) >= score_since_ms}
        )
        projected = _project_group(
            source_rows,
            now_ms=int(now_ms),
            window=window,
            scope=scope,
            score_since_ms=score_since_ms,
            window_ms=window_ms,
            total_window_events=total_window_events,
        )
        target_type_key = str(target.get("target_type_key") or target.get("target_type") or "")
        identity_id = str(target.get("identity_id") or target.get("target_id") or "")
        if projected is None:
            deleted = 0
            for lane in ("resolved", "attention"):
                deleted += self.repos.token_radar.delete_target_feature(
                    projection_version=PROJECTION_VERSION,
                    window=window,
                    scope=scope,
                    lane=lane,
                    target_type_key=target_type_key,
                    identity_id=identity_id,
                    commit=False,
                )
            self.repos.token_radar.mark_target_projection_coverage(
                projection_version=PROJECTION_VERSION,
                target_type_key=target_type_key,
                identity_id=identity_id,
                latest_market_observed_at_ms=int(now_ms),
                projected_at_ms=int(now_ms),
                commit=False,
            )
            return {"status": "deleted" if deleted else "empty", "source_rows": len(source_rows), "rows_written": 0}

        written = self.repos.token_radar.upsert_target_feature(
            projection_version=PROJECTION_VERSION,
            window=window,
            scope=scope,
            row=projected,
            computed_at_ms=int(now_ms),
            commit=False,
        )
        opposite_lane = "attention" if projected["lane"] == "resolved" else "resolved"
        self.repos.token_radar.delete_target_feature(
            projection_version=PROJECTION_VERSION,
            window=window,
            scope=scope,
            lane=opposite_lane,
            target_type_key=target_type_key,
            identity_id=identity_id,
            commit=False,
        )
        return {"status": "updated", "source_rows": len(source_rows), "rows_written": written}

    def refresh_rank_set(
        self,
        *,
        window: str,
        scope: str,
        now_ms: int,
        limit: int = 100,
    ) -> dict[str, Any]:
        computed_at_ms = int(now_ms)
        try:
            rank_inputs, rows = self._rank_and_hydrate_selected_rows(window=window, scope=scope, limit=limit)
            source_max_received_at_ms = max(
                (int(row.get("source_max_received_at_ms") or 0) for row in rows),
                default=0,
            )
            projection_repo = ProjectionRepository(self.repos.conn)
            with _transaction_context(self.repos.conn):
                self._maybe_mark_stale_running_runs(
                    projection_repo,
                    projection_name=TOKEN_RADAR_PROJECTION_NAME,
                    projection_version=PROJECTION_VERSION,
                    window=window,
                    scope=scope,
                    stale_before_ms=computed_at_ms - STALE_RUNNING_PROJECTION_MS,
                    finished_at_ms=computed_at_ms,
                )
                run = projection_repo.start_run(
                    projection_name=TOKEN_RADAR_PROJECTION_NAME,
                    projection_version=PROJECTION_VERSION,
                    mode="rebuild",
                    source_start_ms=0,
                    source_end_ms=computed_at_ms,
                    commit=False,
                )
                rows_replaced = self.repos.token_radar.publish_rows(
                    projection_version=PROJECTION_VERSION,
                    window=window,
                    scope=scope,
                    computed_at_ms=computed_at_ms,
                    rows=rows,
                    on_current_changes=self._enqueue_runtime_dirty_targets_for_rank_changes,
                    commit=False,
                )
                if not rows_replaced:
                    projection_repo.finish_run(
                        run_id=str(run["run_id"]),
                        status="stale_skipped",
                        rows_read=len(rank_inputs),
                        rows_written=0,
                        dirty_ranges_written=0,
                        error="newer_projection_exists",
                        commit=False,
                    )
                    return {
                        "rows_written": 0,
                        "source_rows": len(rank_inputs),
                        "computed_at_ms": computed_at_ms,
                        "status": "stale_skipped",
                    }
                projection_repo.advance_offset(
                    projection_name=TOKEN_RADAR_PROJECTION_NAME,
                    projection_version=PROJECTION_VERSION,
                    source_table=TOKEN_RADAR_SOURCE_TABLE,
                    source_max_received_at_ms=source_max_received_at_ms,
                    source_max_id=str(rows[0]["row_id"]) if rows else "",
                    last_run_id=str(run["run_id"]),
                    lag_ms=max(0, computed_at_ms - source_max_received_at_ms) if source_max_received_at_ms else 0,
                    status="ready",
                    commit=False,
                )
                projection_repo.finish_run(
                    run_id=str(run["run_id"]),
                    status="ready",
                    rows_read=len(rank_inputs),
                    rows_written=len(rows),
                    dirty_ranges_written=0,
                    commit=False,
                )
                self.repos.token_radar.mark_coverage(
                    projection_version=PROJECTION_VERSION,
                    window=window,
                    scope=scope,
                    status="ready",
                    reason=None,
                    source_rows=len(rank_inputs),
                    row_count=len(rows),
                    computed_at_ms=computed_at_ms,
                    started_at_ms=computed_at_ms,
                    finished_at_ms=_now_ms(),
                    error=None,
                    commit=False,
                )
            return {
                "rows_written": len(rows),
                "source_rows": len(rank_inputs),
                "computed_at_ms": computed_at_ms,
                "status": "ready",
            }
        except Exception as exc:
            self.repos.token_radar.mark_coverage(
                projection_version=PROJECTION_VERSION,
                window=window,
                scope=scope,
                status="failed",
                reason="projection_window_failed",
                source_rows=0,
                row_count=0,
                computed_at_ms=computed_at_ms,
                started_at_ms=computed_at_ms,
                finished_at_ms=_now_ms(),
                error=str(exc),
                commit=True,
            )
            raise

    def _maybe_mark_stale_running_runs(
        self,
        projection_repo: ProjectionRepository,
        *,
        projection_name: str,
        projection_version: str,
        window: str,
        scope: str,
        stale_before_ms: int,
        finished_at_ms: int,
    ) -> int:
        cleanup_key = (str(window), str(scope))
        last_cleanup_ms = self._last_stale_cleanup_at_ms.get(cleanup_key)
        if last_cleanup_ms is not None and int(finished_at_ms) - last_cleanup_ms < STALE_RUNNING_CLEANUP_INTERVAL_MS:
            return 0
        updated = projection_repo.mark_stale_running_runs(
            projection_name=projection_name,
            projection_version=projection_version,
            stale_before_ms=int(stale_before_ms),
            finished_at_ms=int(finished_at_ms),
            commit=False,
        )
        self._last_stale_cleanup_at_ms[cleanup_key] = int(finished_at_ms)
        return updated

    def _rank_and_hydrate_selected_rows(
        self,
        *,
        window: str,
        scope: str,
        limit: int,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        stale_rank_inputs = self.repos.token_radar.stale_rank_input_count(
            projection_version=PROJECTION_VERSION,
            window=window,
            scope=scope,
            limit=1,
        )
        if stale_rank_inputs:
            raise RuntimeError("token_radar_rank_inputs_require_full_rebuild")
        rank_inputs = self.repos.token_radar.list_rank_inputs_for_rank_set(
            projection_version=PROJECTION_VERSION,
            window=window,
            scope=scope,
            rank_input_version=TOKEN_RADAR_RANK_INPUT_VERSION,
        )
        ranked = self.rank_compact_inputs(rank_inputs)
        selected_ranked = _select_top_ranked_by_lane(ranked, limit=limit)
        try:
            return rank_inputs, self._hydrate_ranked_rows(selected_ranked)
        except RuntimeError as exc:
            if "payload_hash changed" not in str(exc):
                raise
        rank_inputs = self.repos.token_radar.list_rank_inputs_for_rank_set(
            projection_version=PROJECTION_VERSION,
            window=window,
            scope=scope,
            rank_input_version=TOKEN_RADAR_RANK_INPUT_VERSION,
        )
        ranked = self.rank_compact_inputs(rank_inputs)
        selected_ranked = _select_top_ranked_by_lane(ranked, limit=limit)
        return rank_inputs, self._hydrate_ranked_rows(selected_ranked)

    def _hydrate_ranked_rows(self, selected_ranked: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not selected_ranked:
            return []
        hydrated_rows = self.repos.token_radar.load_target_feature_payloads_for_ranked_keys(selected_ranked)
        hydrated_by_key = {_rank_payload_key(row): row for row in hydrated_rows}
        rows: list[dict[str, Any]] = []
        for ranked in selected_ranked:
            hydrated = hydrated_by_key.get(_rank_payload_key(ranked))
            if hydrated is None:
                raise RuntimeError("Token Radar payload_hash changed during selected-row hydration")
            rows.append(_patch_hydrated_rank_row(hydrated, ranked))
        return rows

    @staticmethod
    def rank_compact_inputs(rank_inputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        factor_scores: dict[str, dict[str, float | None]] = {}
        factor_weights: dict[str, dict[str, float]] = {}
        cohort: set[str] = set()
        cohort_metadata: dict[str, dict[str, Any]] = {}

        for row in rank_inputs:
            target_id = _compact_target_id(row)
            if not target_id:
                continue
            factor_scores[target_id] = {
                family: _compact_family_raw_score(row, family) for family in TOKEN_RADAR_FACTOR_FAMILIES
            }
            factor_weights[target_id] = {
                family: _compact_family_weight(row, family) for family in TOKEN_RADAR_FACTOR_FAMILIES
            }
            high_conf = int(row.get("cohort_high_confidence_mentions") or 0)
            kol_count = int(row.get("cohort_kol_mentions") or 0)
            first_seen_global = row.get("cohort_first_seen_global_24h") is True
            symbol = str(row.get("cohort_symbol") or "").upper()
            if is_active_cohort_member(
                target_id=target_id,
                symbol=symbol,
                high_confidence_mention_count=high_conf,
                kol_mention_count=kol_count,
                was_first_seen_global_24h=first_seen_global,
            ):
                cohort.add(target_id)
            cohort_metadata[target_id] = {
                "high_confidence_mentions": high_conf,
                "kol_mentions": kol_count,
                "public_followup_authors": int(row.get("cohort_public_followup_authors") or 0),
                "first_seen_global_24h": first_seen_global,
                "symbol": symbol,
            }

        cohort_status = _cohort_rank_status(factor_scores=factor_scores, cohort=cohort)
        factor_ranks_by_id = rank_factors_within_cohort(factor_scores=factor_scores, cohort=cohort)
        compact_rows: list[dict[str, Any]] = []
        for row in rank_inputs:
            target_id = _compact_target_id(row)
            factor_ranks = factor_ranks_by_id.get(target_id) or {family: None for family in TOKEN_RADAR_FACTOR_FAMILIES}
            weights = factor_weights.get(target_id) or {
                family: _compact_family_weight(row, family) for family in TOKEN_RADAR_FACTOR_FAMILIES
            }
            alpha_rank = weighted_rank_score(factor_ranks, weights)
            rank_score = (
                round(float(alpha_rank) * 100.0)
                if alpha_rank is not None
                else _display_score_from_value(row.get("raw_composite_score"))
            )
            decision = _decision_from_score_and_gates(rank_score, {"max_decision": row.get("gates_max_decision")})
            compact_rows.append(
                {
                    **dict(row),
                    "rank_score": rank_score,
                    "recommended_decision": decision,
                    "normalization_status": "ranked" if alpha_rank is not None else "no_signal",
                    "cohort_status": cohort_status,
                    "cohort_in_cohort": target_id in cohort,
                    "cohort_size": len(cohort),
                    "cohort_metadata": cohort_metadata.get(target_id, {}),
                    "factor_ranks": factor_ranks,
                    "alpha_rank": alpha_rank,
                }
            )
        compact_rows.sort(key=_compact_rank_key)
        return compact_rows

    def _enqueue_runtime_dirty_targets_for_rank_changes(
        self,
        *,
        window: str,
        scope: str,
        rows: list[dict[str, Any]],
        exited_rows: list[dict[str, Any]],
        previous_by_key: dict[tuple[str, str, str], dict[str, Any]],
        computed_at_ms: int,
    ) -> None:
        self._enqueue_pulse_triggers_for_rank_changes(
            window=window,
            scope=scope,
            rows=rows,
            exited_rows=exited_rows,
            previous_by_key=previous_by_key,
            computed_at_ms=computed_at_ms,
        )
        self._enqueue_narrative_admission_for_rank_changes(
            window=window,
            scope=scope,
            rows=rows,
            exited_rows=exited_rows,
            previous_by_key=previous_by_key,
            computed_at_ms=computed_at_ms,
        )
        self._enqueue_token_profile_current_for_rank_changes(
            window=window,
            scope=scope,
            rows=rows,
            exited_rows=exited_rows,
            previous_by_key=previous_by_key,
            computed_at_ms=computed_at_ms,
        )

    def _enqueue_pulse_triggers_for_rank_changes(
        self,
        *,
        window: str,
        scope: str,
        rows: list[dict[str, Any]],
        exited_rows: list[dict[str, Any]],
        previous_by_key: dict[tuple[str, str, str], dict[str, Any]],
        computed_at_ms: int,
    ) -> None:
        if str(window) not in PULSE_TRIGGER_WINDOWS or str(scope) not in PULSE_TRIGGER_SCOPES:
            return
        targets: list[dict[str, Any]] = []
        for row in rows:
            previous = previous_by_key.get(_current_key(row))
            if previous is not None and str(previous.get("payload_hash") or "") == str(row.get("payload_hash") or ""):
                continue
            target = _pulse_trigger_target(
                row,
                previous=previous,
                window=window,
                scope=scope,
                computed_at_ms=computed_at_ms,
                exited=False,
            )
            if target is not None:
                targets.append(target)
        for row in exited_rows:
            target = _pulse_trigger_target(
                row,
                previous=row,
                window=window,
                scope=scope,
                computed_at_ms=computed_at_ms,
                exited=True,
            )
            if target is not None:
                targets.append(target)
        if not targets:
            return
        repo = getattr(self.repos, "pulse_trigger_dirty_targets", None)
        if repo is None:
            raise RuntimeError("pulse_trigger_dirty_targets repository is required for Token Radar Pulse triggers")
        grouped: dict[str, list[dict[str, Any]]] = {}
        for target in targets:
            grouped.setdefault(str(target.pop("dirty_reason")), []).append(target)
        for reason, reason_targets in grouped.items():
            repo.enqueue_targets(reason_targets, reason=reason, now_ms=computed_at_ms, commit=False)

    def _enqueue_narrative_admission_for_rank_changes(
        self,
        *,
        window: str,
        scope: str,
        rows: list[dict[str, Any]],
        exited_rows: list[dict[str, Any]],
        previous_by_key: dict[tuple[str, str, str], dict[str, Any]],
        computed_at_ms: int,
    ) -> None:
        if str(window) not in NARRATIVE_ADMISSION_WINDOWS or str(scope) != NARRATIVE_ADMISSION_SCOPE:
            return
        targets: list[dict[str, Any]] = []
        for row in rows:
            previous = previous_by_key.get(_current_key(row))
            if previous is not None and str(previous.get("payload_hash") or "") == str(row.get("payload_hash") or ""):
                continue
            target = _narrative_admission_target(
                row,
                previous=previous,
                window=window,
                scope=scope,
                computed_at_ms=computed_at_ms,
                exited=False,
            )
            if target is not None:
                targets.append(target)
        for row in exited_rows:
            target = _narrative_admission_target(
                row,
                previous=row,
                window=window,
                scope=scope,
                computed_at_ms=computed_at_ms,
                exited=True,
            )
            if target is not None:
                targets.append(target)
        if not targets:
            return
        repo = getattr(self.repos, "narrative_admission_dirty_targets", None)
        if repo is None:
            raise RuntimeError(
                "narrative_admission_dirty_targets repository is required for Token Radar Narrative Admission"
            )
        grouped: dict[str, list[dict[str, Any]]] = {}
        for target in targets:
            grouped.setdefault(str(target.pop("dirty_reason")), []).append(target)
        for reason, reason_targets in grouped.items():
            repo.enqueue_targets(reason_targets, reason=reason, now_ms=computed_at_ms, commit=False)

    def _enqueue_token_profile_current_for_rank_changes(
        self,
        *,
        window: str,
        scope: str,
        rows: list[dict[str, Any]],
        exited_rows: list[dict[str, Any]],
        previous_by_key: dict[tuple[str, str, str], dict[str, Any]],
        computed_at_ms: int,
    ) -> None:
        targets: list[dict[str, Any]] = []
        for row in rows:
            previous = previous_by_key.get(_current_key(row))
            if previous is not None and str(previous.get("payload_hash") or "") == str(row.get("payload_hash") or ""):
                continue
            target = _token_profile_current_target(
                row,
                previous=previous,
                window=window,
                scope=scope,
                computed_at_ms=computed_at_ms,
                exited=False,
            )
            if target is not None:
                targets.append(target)
        for row in exited_rows:
            target = _token_profile_current_target(
                row,
                previous=row,
                window=window,
                scope=scope,
                computed_at_ms=computed_at_ms,
                exited=True,
            )
            if target is not None:
                targets.append(target)
        if not targets:
            return
        repo = getattr(self.repos, "token_profile_current_dirty_targets", None)
        if repo is None:
            raise RuntimeError("token_profile_current_dirty_targets repository is required for Token Radar profiles")
        grouped: dict[str, list[dict[str, Any]]] = {}
        for target in targets:
            grouped.setdefault(str(target.pop("dirty_reason")), []).append(target)
        for reason, reason_targets in grouped.items():
            repo.enqueue_targets(reason_targets, reason=reason, now_ms=computed_at_ms, commit=False)

    @staticmethod
    def _group_rows(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            key = (
                f"{row.get('target_type')}:{row.get('target_id')}"
                if row.get("target_type") and row.get("target_id")
                else str(row.get("intent_id"))
            )
            grouped.setdefault(key, []).append(row)
        return grouped


def _cohort_rank_status(
    *,
    factor_scores: dict[str, dict[str, float | None]],
    cohort: set[str],
) -> str:
    rankable = [
        tuple(scores.get(family) for family in TOKEN_RADAR_FACTOR_FAMILIES)
        for token_id, scores in factor_scores.items()
        if token_id in cohort and any(scores.get(family) is not None for family in TOKEN_RADAR_FACTOR_FAMILIES)
    ]
    if len(rankable) < MIN_COHORT_SIZE:
        return "insufficient"
    if len(set(rankable)) <= 1:
        return "all_tied"
    return "ready"


def _analysis_since_ms(*, computed_at_ms: int, window_ms: int) -> int:
    score_since_ms = computed_at_ms - window_ms
    baseline_since_ms = score_since_ms - BASELINE_SLOT_COUNT * window_ms
    return max(baseline_since_ms, computed_at_ms - MAX_ANALYSIS_LOOKBACK_MS)


def _resolve_work_items(
    *,
    windows: tuple[str, ...],
    scopes: tuple[str, ...],
    work_items: tuple[tuple[str, str], ...] | None,
) -> tuple[tuple[str, str], ...]:
    if work_items is not None:
        return tuple(dict.fromkeys((str(window), str(scope)) for window, scope in work_items if window and scope))
    return tuple((window, scope) for window in windows for scope in scopes)


def _source_requests_for_targets(
    targets: list[dict[str, Any]],
    work_items: tuple[tuple[str, str], ...],
    *,
    now_ms: int,
) -> list[TokenRadarSourceRequest]:
    requests: list[TokenRadarSourceRequest] = []
    for target_index, target in enumerate(targets):
        target_type_key = str(target.get("target_type_key") or target.get("target_type") or "")
        identity_id = str(target.get("identity_id") or target.get("target_id") or "")
        for window, scope in work_items:
            window_ms = WINDOW_MS.get(window, WINDOW_MS["1h"])
            score_since_ms = int(now_ms) - window_ms
            requests.append(
                TokenRadarSourceRequest(
                    request_key=_target_source_request_key(
                        target_index=target_index,
                        target_type_key=target_type_key,
                        identity_id=identity_id,
                        window=window,
                        scope=scope,
                    ),
                    target_type_key=target_type_key,
                    identity_id=identity_id,
                    window=window,
                    scope=scope,
                    analysis_since_ms=_analysis_since_ms(computed_at_ms=int(now_ms), window_ms=window_ms),
                    score_since_ms=score_since_ms,
                    now_ms=int(now_ms),
                )
            )
    return requests


def _source_requests_for_rank_rebuild_keys(
    rebuild_keys: list[dict[str, Any]],
    *,
    now_ms: int,
) -> list[TokenRadarSourceRequest]:
    requests: list[TokenRadarSourceRequest] = []
    for key in rebuild_keys:
        window = str(key.get("window") or "")
        scope = str(key.get("scope") or "")
        target_type_key = str(key.get("target_type_key") or key.get("target_type") or "")
        identity_id = str(key.get("identity_id") or key.get("target_id") or "")
        window_ms = WINDOW_MS.get(window, WINDOW_MS["1h"])
        requests.append(
            TokenRadarSourceRequest(
                request_key=_rank_rebuild_request_key(key),
                target_type_key=target_type_key,
                identity_id=identity_id,
                window=window,
                scope=scope,
                analysis_since_ms=_analysis_since_ms(computed_at_ms=int(now_ms), window_ms=window_ms),
                score_since_ms=int(now_ms) - window_ms,
                now_ms=int(now_ms),
            )
        )
    return requests


def _source_requests_by_target(
    requests: list[TokenRadarSourceRequest],
) -> dict[int, list[TokenRadarSourceRequest]]:
    grouped: dict[int, list[TokenRadarSourceRequest]] = {}
    for request in requests:
        parts = request.request_key.split(":", 1)
        if not parts or not parts[0].startswith("target-"):
            continue
        target_index = int(parts[0].removeprefix("target-"))
        grouped.setdefault(target_index, []).append(request)
    return grouped


def _target_source_request_key(
    *,
    target_index: int,
    target_type_key: str,
    identity_id: str,
    window: str,
    scope: str,
) -> str:
    stable = _stable_id("token-radar-source-request", str(target_index), target_type_key, identity_id, window, scope)
    return f"target-{target_index}:{stable}"


def _rank_rebuild_request_key(key: Mapping[str, Any]) -> str:
    return _stable_id(
        "token-radar-rank-rebuild-source-request",
        str(key.get("window") or ""),
        str(key.get("scope") or ""),
        str(key.get("lane") or ""),
        str(key.get("target_type_key") or key.get("target_type") or ""),
        str(key.get("identity_id") or key.get("target_id") or ""),
        str(key.get("payload_hash") or ""),
    )


def _readiness_counts_by_key(stale_by_work_item: Mapping[tuple[str, str], int]) -> dict[str, int]:
    return {f"{window}:{scope}": int(count) for (window, scope), count in stale_by_work_item.items()}


def _now_ms() -> int:
    return int(time.time() * 1000)


def _claim_key(claim: dict[str, Any]) -> dict[str, str | int]:
    return {
        "target_type_key": str(claim.get("target_type_key") or claim.get("target_type") or ""),
        "identity_id": str(claim.get("identity_id") or claim.get("target_id") or ""),
        "payload_hash": str(claim.get("payload_hash") or ""),
        "lease_owner": str(claim.get("lease_owner") or ""),
        "attempt_count": int(claim.get("attempt_count") or 0),
    }


def _current_key(row: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("lane") or ""),
        str(row.get("target_type_key") or row.get("target_type") or ""),
        str(row.get("identity_id") or row.get("target_id") or row.get("intent_id") or ""),
    )


def _pulse_trigger_target(
    row: Mapping[str, Any],
    *,
    previous: Mapping[str, Any] | None,
    window: str,
    scope: str,
    computed_at_ms: int,
    exited: bool,
) -> dict[str, Any] | None:
    target_type = str(row.get("target_type") or "").strip()
    target_id = str(row.get("target_id") or "").strip()
    if not target_type or not target_id:
        return None
    reason = _pulse_trigger_reason(row, previous=previous, exited=exited)
    source_watermark_ms = int(row.get("source_max_received_at_ms") or computed_at_ms)
    payload = {
        "target_type": target_type,
        "target_id": target_id,
        "window": str(window),
        "scope": str(scope),
        "rank": row.get("rank"),
        "lane": row.get("lane"),
        "decision": row.get("decision"),
        "exited": bool(exited),
        "factor_snapshot_hash": _stable_payload_hash(row.get("factor_snapshot_json") or {}),
        "source_event_ids": _json_ready(row.get("source_event_ids_json") or []),
        "source_watermark_ms": source_watermark_ms,
        "token_radar_payload_hash": row.get("payload_hash"),
        "reason": reason,
    }
    return {
        "target_type": target_type,
        "target_id": target_id,
        "window": str(window),
        "scope": str(scope),
        "dirty_reason": reason,
        "payload_hash": _stable_payload_hash(payload),
        "source_watermark_ms": source_watermark_ms,
        "priority": 50 if exited else 40,
        "due_at_ms": int(computed_at_ms),
    }


def _narrative_admission_target(
    row: Mapping[str, Any],
    *,
    previous: Mapping[str, Any] | None,
    window: str,
    scope: str,
    computed_at_ms: int,
    exited: bool,
) -> dict[str, Any] | None:
    target_type = str(row.get("target_type") or "").strip()
    target_id = str(row.get("target_id") or "").strip()
    if not target_type or not target_id:
        return None
    reason = _narrative_admission_reason(row, previous=previous, exited=exited)
    source_watermark_ms = int(row.get("source_max_received_at_ms") or computed_at_ms)
    payload = {
        "target_type": target_type,
        "target_id": target_id,
        "window": str(window),
        "scope": str(scope),
        "projection_version": TOKEN_RADAR_PROJECTION_VERSION,
        "schema_version": NARRATIVE_SCHEMA_VERSION,
        "rank": row.get("rank"),
        "lane": row.get("lane"),
        "decision": row.get("decision"),
        "exited": bool(exited),
        "factor_snapshot_hash": _stable_payload_hash(row.get("factor_snapshot_json") or {}),
        "source_event_ids": _json_ready(row.get("source_event_ids_json") or []),
        "source_watermark_ms": source_watermark_ms,
        "token_radar_payload_hash": row.get("payload_hash"),
        "reason": reason,
    }
    return {
        "target_type": target_type,
        "target_id": target_id,
        "window": str(window),
        "scope": str(scope),
        "projection_version": TOKEN_RADAR_PROJECTION_VERSION,
        "schema_version": NARRATIVE_SCHEMA_VERSION,
        "dirty_reason": reason,
        "payload_hash": _stable_payload_hash(payload),
        "source_watermark_ms": source_watermark_ms,
        "priority": 50 if exited else 40,
        "due_at_ms": int(computed_at_ms),
    }


def _token_profile_current_target(
    row: Mapping[str, Any],
    *,
    previous: Mapping[str, Any] | None,
    window: str,
    scope: str,
    computed_at_ms: int,
    exited: bool,
) -> dict[str, Any] | None:
    target_type = str(row.get("target_type") or "").strip()
    target_id = str(row.get("target_id") or "").strip()
    if target_type not in {"Asset", "CexToken"} or not target_id:
        return None
    reason = _token_profile_current_reason(row, previous=previous, exited=exited)
    source_watermark_ms = int(row.get("source_max_received_at_ms") or computed_at_ms)
    payload = {
        "target_type": target_type,
        "target_id": target_id,
        "window": str(window),
        "scope": str(scope),
        "rank": row.get("rank"),
        "lane": row.get("lane"),
        "decision": row.get("decision"),
        "exited": bool(exited),
        "source_watermark_ms": source_watermark_ms,
        "token_radar_payload_hash": row.get("payload_hash"),
        "reason": reason,
    }
    return {
        "target_type": target_type,
        "target_id": target_id,
        "dirty_reason": reason,
        "payload_hash": _stable_payload_hash(payload),
        "source_watermark_ms": source_watermark_ms,
        "priority": 60 if exited else 70,
        "due_at_ms": int(computed_at_ms),
    }


def _pulse_trigger_reason(
    row: Mapping[str, Any],
    *,
    previous: Mapping[str, Any] | None,
    exited: bool,
) -> str:
    if exited:
        return "token_radar_exited"
    if previous is None:
        return "token_radar_entered"
    if int(previous.get("rank") or 0) != int(row.get("rank") or 0):
        return "token_radar_rank_changed"
    if int(previous.get("source_max_received_at_ms") or 0) != int(row.get("source_max_received_at_ms") or 0):
        return "token_radar_source_watermark_changed"
    return "token_radar_changed"


def _token_profile_current_reason(
    row: Mapping[str, Any],
    *,
    previous: Mapping[str, Any] | None,
    exited: bool,
) -> str:
    if exited:
        return "token_radar_exited"
    if previous is None:
        return "token_radar_entered"
    if str(previous.get("lane") or "") != str(row.get("lane") or ""):
        return "token_radar_visibility_changed"
    if str(previous.get("decision") or "") != str(row.get("decision") or ""):
        return "token_radar_visibility_changed"
    if int(previous.get("rank") or 0) != int(row.get("rank") or 0):
        return "token_radar_rank_changed"
    if int(previous.get("source_max_received_at_ms") or 0) != int(row.get("source_max_received_at_ms") or 0):
        return "token_radar_source_watermark_changed"
    return "token_radar_changed"


def _narrative_admission_reason(
    row: Mapping[str, Any],
    *,
    previous: Mapping[str, Any] | None,
    exited: bool,
) -> str:
    if exited:
        return "token_radar_exited"
    if previous is None:
        return "token_radar_entered"
    if str(previous.get("lane") or "") != str(row.get("lane") or ""):
        return "token_radar_visibility_changed"
    if str(previous.get("decision") or "") != str(row.get("decision") or ""):
        return "token_radar_visibility_changed"
    if int(previous.get("rank") or 0) != int(row.get("rank") or 0):
        return "token_radar_rank_changed"
    if int(previous.get("source_max_received_at_ms") or 0) != int(row.get("source_max_received_at_ms") or 0):
        return "token_radar_source_watermark_changed"
    return "token_radar_changed"


def _stable_payload_hash(payload: Any) -> str:
    encoded = json.dumps(_json_ready(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _transaction_context(conn: Any) -> AbstractContextManager[Any]:
    transaction = getattr(conn, "transaction", None)
    if transaction is None:
        raise RuntimeError("token_radar_projection_requires_transactional_connection")
    return cast(AbstractContextManager[Any], transaction())


def _json_ready(value: Any) -> Any:
    raw = getattr(value, "obj", value)
    if isinstance(raw, Mapping):
        return {str(key): _json_ready(item) for key, item in raw.items()}
    if isinstance(raw, list | tuple | set):
        return [_json_ready(item) for item in raw]
    return raw


def _project_group(
    rows: list[dict[str, Any]],
    *,
    now_ms: int,
    window: str,
    scope: str,
    score_since_ms: int | None = None,
    window_ms: int | None = None,
    total_window_events: int | None = None,
) -> dict[str, Any] | None:
    resolved_window_ms = window_ms or WINDOW_MS.get(window, WINDOW_MS["1h"])
    resolved_score_since_ms = (
        score_since_ms if score_since_ms is not None else min(int(row.get("received_at_ms") or 0) for row in rows)
    )
    window_rows = [row for row in rows if int(row.get("received_at_ms") or 0) >= resolved_score_since_ms]
    if not window_rows:
        return None
    previous_rows = [
        row
        for row in rows
        if resolved_score_since_ms - resolved_window_ms <= int(row.get("received_at_ms") or 0) < resolved_score_since_ms
    ]
    latest = max(window_rows, key=lambda row: int(row.get("received_at_ms") or 0))
    event_ids = sorted({str(row["event_id"]) for row in window_rows})
    latest_seen_ms = max(int(row.get("received_at_ms") or 0) for row in rows)
    resolution_status = str(latest.get("resolution_status") or "NIL")
    target_type = str(latest.get("target_type") or "") or None
    target_id = str(latest.get("target_id") or "") or None
    resolved = _has_resolved_target(latest)
    lane = "resolved" if resolved else "attention"
    target = _target(latest)
    market = _market_context(window_rows, resolved=resolved, now_ms=now_ms)
    scored_window_rows = [{**row, **_market_prefix_for_features(market)} for row in window_rows]
    features = build_radar_features(
        window_rows=scored_window_rows,
        context_rows=rows,
        previous_rows=previous_rows,
        now_ms=now_ms,
        window_ms=resolved_window_ms,
        total_window_events=total_window_events or len(event_ids),
    )
    factor_snapshot = build_token_factor_snapshot(
        target=target,
        attention=features.attention,
        social_quality={**features.quality, **features.propagation},
        social_semantics=_social_semantics(window_rows),
        market=market,
        timing=features.timing,
        source_event_ids=event_ids,
        computed_at_ms=now_ms,
    )
    decision = str(factor_snapshot["composite"]["recommended_decision"])
    # Cohort accounting fields are persisted as scalar rank inputs after each group settles.
    # These internal fields use the _cohort_* prefix and are stripped before persistence.
    cohort_high_conf_count = sum(
        1 for r in window_rows if (r.get("resolution_status") or "") in HIGH_CONF_RESOLUTION_STATUSES
    )
    cohort_kol_count = sum(1 for r in window_rows if set(r.get("gmgn_user_tags") or ()) & KOL_TIER_TAGS)
    cohort_first_seen_global_24h = any(row.get("first_seen_global_24h") is True for row in window_rows)
    cohort_public_followup_count = int(features.propagation.get("public_followup_author_count") or 0)
    return {
        "row_id": _stable_id(
            "token-radar-row",
            window,
            scope,
            str(target_id or latest.get("intent_id")),
            str(now_ms),
        ),
        "source_max_received_at_ms": latest_seen_ms,
        "lane": lane,
        "rank": 0,
        "intent_id": latest["intent_id"],
        "event_id": latest["event_id"],
        "target_type": target_type,
        "target_id": target_id,
        "pricefeed_id": latest.get("pricefeed_id"),
        "intent_json": {
            "intent_id": latest["intent_id"],
            "display_symbol": _real_symbol(latest.get("display_symbol")),
            "display_name": latest.get("display_name"),
            "evidence": [],
        },
        "asset_json": target if target_type == "Asset" else {},
        "target_json": target,
        "primary_venue_json": None,
        "factor_snapshot_json": factor_snapshot,
        "factor_version": factor_snapshot["schema_version"],
        "attention_json": {},
        "resolution_json": {
            "status": resolution_status,
            "target_type": target_type,
            "target_id": target_id,
            "pricefeed_id": latest.get("pricefeed_id"),
            "reason_codes": latest.get("reason_codes_json") or [],
            "candidate_ids": latest.get("candidate_ids_json") or [],
            "lookup_keys": latest.get("lookup_keys_json") or [],
            "discovery": _resolution_discovery(latest),
        },
        "market_json": {},
        "price_json": {},
        "score_json": {},
        "decision": decision,
        "data_health_json": {
            "factor_snapshot": "ready",
            "identity": factor_snapshot["data_health"]["identity"],
            "market": factor_snapshot["data_health"]["market"],
            "social": factor_snapshot["data_health"]["social"],
            "alpha": factor_snapshot["data_health"]["alpha"],
        },
        "source_event_ids_json": event_ids,
        "created_at_ms": now_ms,
        # Internal cohort fields are converted to scalar rank inputs before persistence.
        "_cohort_high_conf_count": cohort_high_conf_count,
        "_cohort_kol_count": cohort_kol_count,
        "_cohort_first_seen_global_24h": cohort_first_seen_global_24h,
        "_cohort_public_followup_count": cohort_public_followup_count,
    }


def _social_semantics(window_rows: list[dict[str, Any]]) -> dict[str, Any]:
    direction_counts: dict[str, int] = {}
    impact_values: list[float] = []
    novelty_values: list[float] = []
    confidence_values: list[float] = []

    for row in window_rows:
        direction = _semantic_direction(row.get("llm_direction_hint"))
        if direction:
            direction_counts[direction] = direction_counts.get(direction, 0) + 1
        impact = _float_or_none(row.get("llm_impact_hint"))
        if impact is not None:
            impact_values.append(impact)
        novelty = _float_or_none(row.get("llm_semantic_novelty_hint"))
        if novelty is not None:
            novelty_values.append(novelty)
        confidence = _float_or_none(row.get("llm_label_confidence"))
        if confidence is not None:
            confidence_values.append(confidence)

    return {
        "direction_counts": direction_counts,
        "impact_mean": _mean_or_none(impact_values),
        "novelty_mean": _mean_or_none(novelty_values),
        "confidence_mean": _mean_or_none(confidence_values),
    }


def _semantic_direction(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    if text in {"bullish", "positive", "attention_positive"} or "positive" in text:
        return "bullish"
    if text in {"bearish", "negative", "attention_negative"} or "negative" in text:
        return "bearish"
    if text == "neutral" or "neutral" in text:
        return "neutral"
    return text


def _mean_or_none(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 6)


def _has_resolved_target(row: dict[str, Any]) -> bool:
    if not bool(row.get("target_id")) or str(row.get("resolution_status") or "") not in {
        "EXACT",
        "UNIQUE_BY_CONTEXT",
    }:
        return False
    return not (
        row.get("target_type") == "Asset" and row.get("asset_registry_status") not in {"candidate", "canonical"}
    )


def _resolution_discovery(row: dict[str, Any]) -> list[dict[str, Any]]:
    lookup_keys = _discovery_lookup_keys(row.get("lookup_keys_json") or [])
    existing = [
        _discovery_result(item)
        for item in row.get("discovery_results_json") or []
        if isinstance(item, dict) and item.get("lookup_key")
    ]
    existing_by_key = {str(item["lookup_key"]): item for item in existing}
    out: list[dict[str, Any]] = [existing_by_key.get(key) or _not_searched_discovery(key) for key in lookup_keys]
    seen = {str(item["lookup_key"]) for item in out}
    out.extend(item for item in existing if str(item["lookup_key"]) not in seen)
    return out


def _discovery_lookup_keys(raw_keys: list[Any]) -> list[str]:
    out: list[str] = []
    for raw_key in raw_keys:
        key = str(raw_key or "")
        if key.startswith("symbol:") or key.startswith("address:"):
            out.append(key)
    return sorted(set(out))


def _discovery_result(item: dict[str, Any]) -> dict[str, Any]:
    lookup_key = str(item.get("lookup_key") or "")
    return {
        "lookup_key": lookup_key,
        "lookup_type": item.get("lookup_type") or _lookup_type(lookup_key),
        "status": item.get("status") or "unknown",
        "candidate_count": int(item.get("candidate_count") or 0),
        "last_lookup_at_ms": item.get("last_lookup_at_ms"),
        "next_refresh_at_ms": item.get("next_refresh_at_ms"),
        "last_error": item.get("last_error"),
        "error_count": int(item.get("error_count") or 0),
    }


def _not_searched_discovery(lookup_key: str) -> dict[str, Any]:
    return {
        "lookup_key": lookup_key,
        "lookup_type": _lookup_type(lookup_key),
        "status": "not_searched",
        "candidate_count": 0,
        "last_lookup_at_ms": None,
        "next_refresh_at_ms": None,
        "last_error": None,
        "error_count": 0,
    }


def _lookup_type(lookup_key: str) -> str:
    if lookup_key.startswith("symbol:"):
        return "dex_symbol_lookup"
    if lookup_key.startswith("address:"):
        return "address_lookup"
    return "unknown_lookup"


def _target(row: dict[str, Any]) -> dict[str, Any]:
    target_type = row.get("target_type")
    target_id = row.get("target_id")
    if not target_type or not target_id:
        return {
            "target_type": None,
            "target_id": None,
            "symbol": _display_symbol(row),
            "status": str(row.get("resolution_status") or "NIL"),
        }
    if target_type == "CexToken":
        return {
            "target_type": "CexToken",
            "target_id": target_id,
            "symbol": _target_symbol(row),
            "status": row.get("cex_token_status"),
            "pricefeed_id": row.get("pricefeed_id"),
            "native_market_id": row.get("native_market_id"),
            "quote_symbol": row.get("pricefeed_quote_symbol"),
            "feed_type": row.get("feed_type"),
            "provider": row.get("pricefeed_provider"),
        }
    return {
        "target_type": "Asset",
        "target_id": target_id,
        "symbol": _target_symbol(row),
        "name": row.get("asset_name"),
        "chain": row.get("asset_chain_id"),
        "chain_id": row.get("asset_chain_id"),
        "token_standard": row.get("asset_token_standard"),
        "address": row.get("asset_address"),
        "status": row.get("asset_registry_status"),
        "pricefeed_id": row.get("pricefeed_id"),
        "identity": {
            "confidence": row.get("asset_identity_confidence"),
            "reason_codes": row.get("asset_identity_reason_codes") or [],
            "conflict_count": row.get("asset_identity_conflict_count") or 0,
        },
    }


def _market_context(window_rows: list[dict[str, Any]], *, resolved: bool, now_ms: int) -> dict[str, Any]:
    if not resolved:
        latest = max(window_rows, key=lambda item: int(item.get("received_at_ms") or 0)) if window_rows else {}
        return _market_context_dict(
            event_anchor=None,
            decision_latest=None,
            capture_method=None,
            capture_reason=None,
            tick_lag_ms=None,
            readiness=_market_readiness(
                event_anchor=None,
                decision_latest=None,
                target_type=latest.get("target_type"),
                now_ms=now_ms,
            ),
        )
    if not window_rows:
        return _market_context_dict(
            event_anchor=None,
            decision_latest=None,
            capture_method=None,
            capture_reason=None,
            tick_lag_ms=None,
            readiness=_market_readiness(
                event_anchor=None,
                decision_latest=None,
                target_type=None,
                now_ms=now_ms,
            ),
        )
    social_start = min(window_rows, key=lambda item: int(item.get("received_at_ms") or 0))
    event_anchor = _observation_from_row(
        social_start,
        prefix="event_price",
        source=social_start.get("event_price_capture_method"),
    )
    latest_row = max(
        window_rows,
        key=lambda item: int(item.get("latest_price_observed_at_ms") or 0),
    )
    decision_latest = _observation_from_row(
        latest_row,
        prefix="latest_price",
        source=latest_row.get("latest_price_source_tier"),
    )
    return _market_context_dict(
        event_anchor=event_anchor,
        decision_latest=decision_latest,
        capture_method=_optional_str(social_start.get("event_price_capture_method")),
        capture_reason=_optional_str(social_start.get("event_price_capture_reason")),
        tick_lag_ms=_int_or_none(social_start.get("event_price_tick_lag_ms")),
        readiness=_market_readiness(
            event_anchor=event_anchor,
            decision_latest=decision_latest,
            target_type=social_start.get("target_type"),
            now_ms=now_ms,
        ),
    )


def _market_context_dict(
    *,
    event_anchor: dict[str, Any] | None,
    decision_latest: dict[str, Any] | None,
    capture_method: str | None,
    capture_reason: str | None,
    tick_lag_ms: int | None,
    readiness: dict[str, Any],
) -> dict[str, Any]:
    return {
        "event_anchor": event_anchor,
        "decision_latest": decision_latest,
        "capture_method": capture_method,
        "capture_reason": capture_reason,
        "tick_lag_ms": tick_lag_ms,
        "readiness": readiness,
    }


def _observation_from_row(row: dict[str, Any], *, prefix: str, source: Any) -> dict[str, Any] | None:
    price_usd = row.get(_observation_column(prefix, "price_usd"))
    price_quote = row.get(_observation_column(prefix, "price_quote"))
    observed_at_ms = _int_or_none(row.get(f"{prefix}_observed_at_ms"))
    if observed_at_ms is None or (price_usd is None and price_quote is None):
        return None
    return {
        "target_type": row.get("target_type"),
        "target_id": row.get("target_id"),
        "observed_at_ms": observed_at_ms,
        "received_at_ms": _int_or_none(row.get(f"{prefix}_received_at_ms") or row.get("received_at_ms")),
        "source": str(source or ""),
        "provider": row.get(f"{prefix}_provider"),
        "pricefeed_id": row.get(f"{prefix}_pricefeed_id") or row.get("pricefeed_id"),
        "price_usd": _float_or_none(price_usd),
        "price_quote": _float_or_none(price_quote),
        "quote_symbol": row.get(f"{prefix}_quote_symbol"),
        "price_basis": row.get(_observation_column(prefix, "price_basis")),
        "market_cap_usd": _float_or_none(row.get(f"{prefix}_market_cap_usd")),
        "liquidity_usd": _float_or_none(row.get(f"{prefix}_liquidity_usd")),
        "holders": _int_or_none(row.get(f"{prefix}_holders")),
        "volume_24h_usd": _float_or_none(row.get(f"{prefix}_volume_24h_usd")),
        "open_interest_usd": _float_or_none(row.get(f"{prefix}_open_interest_usd")),
        "raw_payload_hash": None,
    }


def _observation_column(prefix: str, field: str) -> str:
    if prefix == "event_price" and field in {"price_usd", "price_quote", "price_basis"}:
        return f"event_{field}"
    if prefix == "latest_price" and field in {"price_usd", "price_quote", "price_basis"}:
        return f"latest_{field}"
    return f"{prefix}_{field}"


def _market_readiness(
    *,
    event_anchor: dict[str, Any] | None,
    decision_latest: dict[str, Any] | None,
    target_type: Any,
    now_ms: int,
) -> dict[str, Any]:
    missing_fields = _missing_decision_fields(decision_latest, target_type=target_type)
    stale_fields = []
    latest_status = _latest_status(decision_latest, now_ms=now_ms)
    if latest_status == "stale":
        stale_fields.append("decision_latest")
    return {
        "anchor_status": "ready" if event_anchor is not None else "missing",
        "latest_status": latest_status,
        "dex_floor_status": _dex_floor_status(decision_latest, target_type=target_type, missing_fields=missing_fields),
        "missing_fields": missing_fields,
        "stale_fields": stale_fields,
    }


def _missing_decision_fields(decision_latest: dict[str, Any] | None, *, target_type: Any) -> list[str]:
    if str(target_type or "") != "Asset":
        return []
    latest = decision_latest or {}
    return [field for field in DEX_DECISION_FLOORS if latest.get(field) is None]


def _latest_status(decision_latest: dict[str, Any] | None, *, now_ms: int) -> str:
    if decision_latest is None:
        return "missing"
    observed_at_ms = _int_or_none(decision_latest.get("received_at_ms") or decision_latest.get("observed_at_ms"))
    if observed_at_ms is None:
        return "missing"
    age_ms = max(0, int(now_ms) - observed_at_ms)
    if age_ms <= LIVE_LATEST_MAX_AGE_MS:
        return "live"
    if age_ms <= FRESH_LATEST_MAX_AGE_MS:
        return "fresh"
    return "stale"


def _dex_floor_status(
    decision_latest: dict[str, Any] | None,
    *,
    target_type: Any,
    missing_fields: list[str],
) -> str:
    if str(target_type or "") != "Asset":
        return "ready"
    if missing_fields:
        return "missing_fields"
    latest = decision_latest or {}
    for field, floor in DEX_DECISION_FLOORS.items():
        value = _float_or_none(latest.get(field))
        if value is None:
            return "missing_fields"
        if value < floor:
            return "below_floor"
    return "ready"


def _readiness_status(market: dict[str, Any]) -> str:
    readiness = _dict(market.get("readiness"))
    if readiness.get("anchor_status") != "ready":
        return "missing"
    latest_status = str(readiness.get("latest_status") or "missing")
    return "ready" if latest_status in {"live", "fresh"} else "partial"


def _price_change_between(current: dict[str, Any], base: dict[str, Any]) -> float | None:
    if current.get("price_usd") is not None and base.get("price_usd") is not None:
        return _pct_change(current.get("price_usd"), base.get("price_usd"))
    if current.get("quote_symbol") and current.get("quote_symbol") == base.get("quote_symbol"):
        return _pct_change(current.get("price_quote"), base.get("price_quote"))
    return None


def _market_prefix_for_features(market: dict[str, Any]) -> dict[str, Any]:
    event_anchor = _dict(market.get("event_anchor"))
    decision_latest = _dict(market.get("decision_latest"))
    return {
        "market_status": _readiness_status(market),
        "market_observation_status": _dict(market.get("readiness")).get("anchor_status"),
        "market_market_cap_usd": decision_latest.get("market_cap_usd"),
        "market_liquidity_usd": decision_latest.get("liquidity_usd"),
        "market_volume_24h_usd": decision_latest.get("volume_24h_usd"),
        "market_open_interest_usd": decision_latest.get("open_interest_usd"),
        "market_holders": decision_latest.get("holders"),
        "price_change_since_social_pct": _price_change_between(decision_latest, event_anchor),
        "price_change_before_social_pct": None,
    }


def _price_values(row: dict[str, Any], prefix: str) -> dict[str, Any]:
    if prefix == "market":
        return {
            "price_usd": row.get("market_price_usd"),
            "price_quote": row.get("market_price_quote"),
            "quote_symbol": row.get("market_quote_symbol") or row.get("pricefeed_quote_symbol"),
            "price_basis": row.get("market_price_basis"),
        }
    return {
        "price_usd": row.get(f"{prefix}_price_usd"),
        "price_quote": row.get(f"{prefix}_price_quote"),
        "quote_symbol": row.get(f"{prefix}_price_quote_symbol"),
        "price_basis": row.get(f"{prefix}_price_basis"),
    }


def _comparable_price(current: dict[str, Any], base: dict[str, Any]) -> tuple[Any, Any, str]:
    if current.get("price_usd") is not None and base.get("price_usd") is not None:
        return current["price_usd"], base["price_usd"], "usd"
    current_quote = current.get("quote_symbol")
    base_quote = base.get("quote_symbol")
    if current_quote and base_quote and current_quote == base_quote:
        return current.get("price_quote"), base.get("price_quote"), f"quote:{current_quote}"
    return None, None, "basis_mismatch"


def _pct_change(current: Any, base: Any) -> float | None:
    current_value = _float_or_none(current)
    base_value = _float_or_none(base)
    if current_value is None or base_value is None or base_value == 0:
        return None
    return round(current_value / base_value - 1.0, 6)


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _field_status(value: Any) -> str:
    return "ready" if value is not None else "missing"


def _display_symbol(row: dict[str, Any]) -> str | None:
    for value in (
        row.get("display_symbol"),
        row.get("cex_base_symbol"),
        row.get("asset_symbol"),
        row.get("pricefeed_base_symbol"),
    ):
        symbol = _real_symbol(value)
        if symbol:
            return symbol
    return None


def _target_symbol(row: dict[str, Any]) -> str | None:
    if row.get("target_type") == "Asset":
        return _first_real_symbol(row.get("asset_symbol"))
    if row.get("target_type") == "CexToken":
        return _first_real_symbol(
            row.get("cex_base_symbol"),
            row.get("pricefeed_base_symbol"),
            row.get("display_symbol"),
        )
    return _display_symbol(row)


def _first_real_symbol(*values: Any) -> str | None:
    for value in values:
        symbol = _real_symbol(value)
        if symbol:
            return symbol
    return None


def _real_symbol(value: Any) -> str | None:
    if value is None:
        return None
    symbol = str(value).strip().lstrip("$")
    if not symbol:
        return None
    if _is_address_like_symbol(symbol):
        return None
    return symbol


def _is_address_like_symbol(symbol: str) -> bool:
    value = symbol.strip().upper()
    if value.startswith("0X") and len(value) >= 22:
        return all(char in "0123456789ABCDEF" for char in value[2:])
    if len(value) < 32:
        return False
    if value.endswith("PUMP"):
        value = value[:-4]
    return all(char.isdigit() or ("A" <= char <= "Z") for char in value)


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _rank_key(row: dict[str, Any]) -> tuple[int, float, int, int, int]:
    snapshot = _factor_snapshot_for_ranking(row)
    if snapshot is None:
        return (3, 0.0, 0, 0, 0)
    composite = _dict(snapshot.get("composite"))
    families = _dict(snapshot.get("families"))
    social_heat = _dict(families.get("social_heat"))
    social_propagation = _dict(families.get("social_propagation"))
    attention = _dict(social_heat.get("facts"))
    diffusion = _dict(social_propagation.get("facts"))
    decision_priority = {"high_alert": 0, "watch": 1, "discard": 2}
    decision = composite.get("recommended_decision") or "discard"
    rank_score = _float_or_none(composite.get("rank_score")) or 0.0
    return (
        decision_priority.get(str(decision), 2),
        -rank_score,
        -int(attention.get("watched_mentions") or 0),
        -int(attention.get("mentions_1h") or diffusion.get("mentions") or 0),
        -int(attention.get("latest_seen_ms") or 0),
    )


def _compact_rank_key(row: dict[str, Any]) -> tuple[int, float, int, int, int]:
    decision_priority = {"high_alert": 0, "watch": 1, "discard": 2}
    decision = row.get("recommended_decision") or "discard"
    rank_score = _float_or_none(row.get("rank_score")) or 0.0
    mentions_1h = int(row.get("social_heat_mentions_1h") or row.get("social_propagation_mentions") or 0)
    return (
        decision_priority.get(str(decision), 2),
        -rank_score,
        -int(row.get("social_heat_watched_mentions") or 0),
        -mentions_1h,
        -int(row.get("social_heat_latest_seen_ms") or 0),
    )


def _select_top_ranked_by_lane(ranked: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    lane_order = ("resolved", "attention")
    for lane in lane_order:
        lane_rows = [row for row in ranked if str(row.get("lane") or "") == lane]
        for rank, row in enumerate(lane_rows[: max(0, int(limit))], start=1):
            selected.append({**row, "rank": rank})
    return selected


def _rank_payload_key(row: dict[str, Any]) -> tuple[str, str, str, str, str, str, str]:
    return (
        str(row.get("projection_version") or ""),
        str(row.get("window") or ""),
        str(row.get("scope") or ""),
        str(row.get("lane") or ""),
        str(row.get("target_type_key") or ""),
        str(row.get("identity_id") or ""),
        str(row.get("payload_hash") or ""),
    )


def _patch_hydrated_rank_row(row: dict[str, Any], ranked: dict[str, Any]) -> dict[str, Any]:
    patched = dict(row)
    factor_snapshot = _factor_snapshot_or_raise(patched)
    families = _dict(factor_snapshot.get("families"))
    factor_ranks = _dict(ranked.get("factor_ranks"))
    for family in TOKEN_RADAR_FACTOR_FAMILIES:
        rank = factor_ranks.get(family)
        if rank is not None and isinstance(families.get(family), dict):
            families[family]["score"] = round(float(rank) * 100.0)
    family_scores = {family: _family_display_score(families.get(family)) for family in TOKEN_RADAR_FACTOR_FAMILIES}
    factor_snapshot["normalization"] = {
        "status": ranked.get("normalization_status") or "no_signal",
        "cohort_status": ranked.get("cohort_status") or "not_ranked",
        "cohort": {
            "in_cohort": ranked.get("cohort_in_cohort") is True,
            "size": int(ranked.get("cohort_size") or 0),
            "definition_version": COHORT_DEFINITION_VERSION,
            "normalizer_version": NORMALIZER_VERSION,
            **_dict(ranked.get("cohort_metadata")),
        },
        "factor_ranks": factor_ranks,
        "alpha_rank": ranked.get("alpha_rank"),
    }
    factor_snapshot["composite"]["family_scores"] = family_scores
    factor_snapshot["composite"]["rank_score"] = ranked.get("rank_score")
    factor_snapshot["composite"]["recommended_decision"] = ranked.get("recommended_decision")
    patched["factor_snapshot_json"] = factor_snapshot
    patched["decision"] = ranked.get("recommended_decision")
    patched["rank"] = int(ranked.get("rank") or 0)
    patched["source_max_received_at_ms"] = int(ranked.get("latest_event_received_at_ms") or 0)
    return patched


def _compact_target_id(row: dict[str, Any]) -> str:
    return str(row.get("target_id") or "")


def _compact_family_raw_score(row: dict[str, Any], family: str) -> float | None:
    return _float_or_none(row.get(f"{family}_raw_score"))


def _compact_family_weight(row: dict[str, Any], family: str) -> float:
    return _float_or_none(row.get(f"{family}_weight")) or 0.0


def _display_score_from_value(value: Any) -> int:
    score = _float_or_none(value) or 0.0
    return round(max(0.0, min(100.0, score)))


def _factor_snapshot_for_ranking(row: dict[str, Any]) -> dict[str, Any] | None:
    try:
        return _factor_snapshot_or_raise(row)
    except ValueError:
        return None


def _factor_snapshot_or_raise(row: dict[str, Any]) -> dict[str, Any]:
    factor_snapshot = row.get("factor_snapshot_json")
    return require_token_factor_snapshot(factor_snapshot, field_name="factor_snapshot_json")


def _dict(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


def _family_raw_score(family: Any) -> float | None:
    if not isinstance(family, dict):
        return None
    raw_score = _float_or_none(family.get("raw_score"))
    if raw_score is not None:
        return raw_score
    return _float_or_none(family.get("score"))


def _family_weight(family: Any) -> float:
    if not isinstance(family, dict):
        return 0.0
    return _float_or_none(family.get("weight")) or 0.0


def _family_display_score(family: Any) -> int:
    if not isinstance(family, dict):
        return 0
    score = _float_or_none(family.get("score")) or 0.0
    return round(max(0.0, min(100.0, score)))


def _raw_composite_score(factor_snapshot: dict[str, Any]) -> int:
    composite = _dict(factor_snapshot.get("composite"))
    score = _float_or_none(composite.get("rank_score"))
    if score is None:
        score = _float_or_none(composite.get("raw_alpha_score"))
    return round(max(0.0, min(100.0, score or 0.0)))


def _decision_from_score_and_gates(score: int, gates: dict[str, Any]) -> str:
    max_decision = str(gates.get("max_decision") or "discard")
    if max_decision == "discard":
        return "discard"
    if score >= 70 and max_decision == "high_alert":
        return "high_alert"
    if score >= 35 and max_decision in {"watch", "high_alert"}:
        return "watch"
    return "discard"


def _stable_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _count_high_conf(row: dict[str, Any]) -> int:
    return int(row.get("_cohort_high_conf_count") or 0)


def _count_kol_authors(row: dict[str, Any]) -> int:
    return int(row.get("_cohort_kol_count") or 0)


def _count_public_followup(row: dict[str, Any]) -> int:
    return int(row.get("_cohort_public_followup_count") or 0)


def _cohort_first_seen_global(row: dict[str, Any]) -> bool:
    if row.get("_cohort_first_seen_global_24h") is True:
        return True
    return row.get("first_seen_global_24h") is True
