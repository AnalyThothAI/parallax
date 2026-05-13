from __future__ import annotations

import hashlib
import time
from typing import Any

from gmgn_twitter_intel.domains.token_intel._constants import (
    TOKEN_RADAR_FACTOR_FAMILIES,
    TOKEN_RADAR_PROJECTION_NAME,
    TOKEN_RADAR_PROJECTION_VERSION,
    TOKEN_RADAR_SOURCE_TABLE,
    WINDOW_MS,
)
from gmgn_twitter_intel.domains.token_intel.queries.token_radar_source_query import TokenRadarSourceQuery
from gmgn_twitter_intel.domains.token_intel.repositories.projection_repository import ProjectionRepository
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
MAX_ANALYSIS_LOOKBACK_MS = 48 * 60 * 60 * 1000
DEX_DECISION_FLOORS = {
    "holders": 100,
    "liquidity_usd": 25_000.0,
    "market_cap_usd": 50_000.0,
}
LIVE_LATEST_MAX_AGE_MS = 90 * 1000
FRESH_LATEST_MAX_AGE_MS = 5 * 60 * 1000


class TokenRadarProjection:
    def __init__(
        self,
        *,
        repos: Any,
    ) -> None:
        self.repos = repos

    def rebuild(self, *, window: str, scope: str, now_ms: int | None = None, limit: int = 100) -> dict[str, Any]:
        computed_at_ms = int(now_ms or time.time() * 1000)
        window_ms = WINDOW_MS.get(window, WINDOW_MS["1h"])
        score_since_ms = computed_at_ms - window_ms
        analysis_since_ms = _analysis_since_ms(computed_at_ms=computed_at_ms, window_ms=window_ms)
        self.repos.token_radar.mark_coverage(
            projection_version=PROJECTION_VERSION,
            window=window,
            scope=scope,
            status="running",
            reason="projection_window_running",
            source_rows=0,
            row_count=0,
            computed_at_ms=computed_at_ms,
            started_at_ms=computed_at_ms,
            finished_at_ms=None,
            error=None,
            commit=True,
        )
        try:
            source_rows = self._source_rows(
                since_ms=analysis_since_ms,
                scope=scope,
                now_ms=computed_at_ms,
            )
            grouped = self._group_rows(source_rows)
            total_window_events = len(
                {str(row["event_id"]) for row in source_rows if int(row.get("received_at_ms") or 0) >= score_since_ms}
            )
            projected = [
                row
                for group in grouped.values()
                if (
                    row := _project_group(
                        group,
                        now_ms=computed_at_ms,
                        window=window,
                        scope=scope,
                        score_since_ms=score_since_ms,
                        window_ms=window_ms,
                        total_window_events=total_window_events,
                    )
                )
            ]
            projected = self._apply_cross_section(projected)
            resolved = [row for row in projected if row["lane"] == "resolved"]
            attention = [row for row in projected if row["lane"] == "attention"]
            resolved.sort(key=_rank_key)
            attention.sort(key=_rank_key)
            rows = []
            for lane_rows in (resolved, attention):
                for rank, row in enumerate(lane_rows[:limit], start=1):
                    rows.append({**row, "rank": rank})
            source_max_received_at_ms = max(
                (int(row.get("source_max_received_at_ms") or 0) for row in rows),
                default=0,
            )
            projection_repo = ProjectionRepository(self.repos.conn)
            projection_repo.mark_stale_running_runs(
                projection_name=TOKEN_RADAR_PROJECTION_NAME,
                projection_version=PROJECTION_VERSION,
                stale_before_ms=computed_at_ms - STALE_RUNNING_PROJECTION_MS,
                finished_at_ms=computed_at_ms,
                commit=False,
            )
            run = projection_repo.start_run(
                projection_name=TOKEN_RADAR_PROJECTION_NAME,
                projection_version=PROJECTION_VERSION,
                mode="rebuild",
                source_start_ms=analysis_since_ms,
                source_end_ms=computed_at_ms,
                commit=False,
            )
            rows_replaced = self.repos.token_radar.replace_rows(
                projection_version=PROJECTION_VERSION,
                window=window,
                scope=scope,
                computed_at_ms=computed_at_ms,
                rows=rows,
                commit=False,
            )
            if not rows_replaced:
                projection_repo.finish_run(
                    run_id=str(run["run_id"]),
                    status="stale_skipped",
                    rows_read=len(source_rows),
                    rows_written=0,
                    dirty_ranges_written=0,
                    error="newer_projection_exists",
                    commit=True,
                )
                return {
                    "rows_written": 0,
                    "source_rows": len(source_rows),
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
                rows_read=len(source_rows),
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
                source_rows=len(source_rows),
                row_count=len(rows),
                computed_at_ms=computed_at_ms,
                started_at_ms=computed_at_ms,
                finished_at_ms=_now_ms(),
                error=None,
                commit=True,
            )
            return {
                "rows_written": len(rows),
                "source_rows": len(source_rows),
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

    def _source_rows(
        self,
        *,
        since_ms: int,
        scope: str,
        now_ms: int,
    ) -> list[dict[str, Any]]:
        return TokenRadarSourceQuery(self.repos.conn).source_rows(
            since_ms=since_ms,
            scope=scope,
            now_ms=now_ms,
        )

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

    @staticmethod
    def _apply_cross_section(projected: list[dict[str, Any]]) -> list[dict[str, Any]]:
        factor_scores: dict[str, dict[str, float | None]] = {}
        factor_weights: dict[str, dict[str, float]] = {}
        cohort: set[str] = set()
        cohort_metadata: dict[str, dict[str, Any]] = {}

        for row in projected:
            factor_snapshot = _factor_snapshot_or_raise(row)
            target_id = str(row.get("target_id") or "")
            if not target_id:
                continue
            families = factor_snapshot["families"]
            factor_scores[target_id] = {
                family: _family_raw_score(families.get(family)) for family in TOKEN_RADAR_FACTOR_FAMILIES
            }
            factor_weights[target_id] = {
                family: _family_weight(families.get(family)) for family in TOKEN_RADAR_FACTOR_FAMILIES
            }

            high_conf = _count_high_conf(row)
            kol_count = _count_kol_authors(row)
            public_followup_count = _count_public_followup(row)
            first_seen_global = _cohort_first_seen_global(row)
            symbol = (
                (row.get("target_json") or {}).get("symbol")
                or (row.get("intent_json") or {}).get("display_symbol")
                or ""
            ).upper()
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
                "public_followup_authors": public_followup_count,
                "first_seen_global_24h": first_seen_global,
                "symbol": symbol,
            }

        cohort_status = _cohort_rank_status(factor_scores=factor_scores, cohort=cohort)
        factor_ranks_by_id = rank_factors_within_cohort(factor_scores=factor_scores, cohort=cohort)

        for row in projected:
            target_id = str(row.get("target_id") or "")
            factor_snapshot = _factor_snapshot_or_raise(row)
            families = factor_snapshot["families"]
            factor_ranks = factor_ranks_by_id.get(target_id) or {family: None for family in TOKEN_RADAR_FACTOR_FAMILIES}
            weights = factor_weights.get(target_id) or {
                family: _family_weight(families.get(family)) for family in TOKEN_RADAR_FACTOR_FAMILIES
            }
            alpha_rank = weighted_rank_score(factor_ranks, weights)
            normalization_status = "ranked" if alpha_rank is not None else "no_signal"
            for family in TOKEN_RADAR_FACTOR_FAMILIES:
                rank = factor_ranks.get(family)
                if rank is not None and isinstance(families.get(family), dict):
                    families[family]["score"] = round(float(rank) * 100.0)
            rank_score = (
                round(float(alpha_rank) * 100.0) if alpha_rank is not None else _raw_composite_score(factor_snapshot)
            )
            decision = _decision_from_score_and_gates(rank_score, factor_snapshot["gates"])
            family_scores = {
                family: _family_display_score(families.get(family)) for family in TOKEN_RADAR_FACTOR_FAMILIES
            }
            factor_snapshot["normalization"] = {
                "status": normalization_status,
                "cohort_status": cohort_status,
                "cohort": {
                    "in_cohort": target_id in cohort,
                    "size": len(cohort),
                    "definition_version": COHORT_DEFINITION_VERSION,
                    "normalizer_version": NORMALIZER_VERSION,
                    **(cohort_metadata.get(target_id, {})),
                },
                "factor_ranks": factor_ranks,
                "alpha_rank": alpha_rank,
            }
            factor_snapshot["composite"]["family_scores"] = family_scores
            factor_snapshot["composite"]["rank_score"] = rank_score
            factor_snapshot["composite"]["recommended_decision"] = decision
            row["factor_snapshot_json"] = factor_snapshot
            row["decision"] = decision
            for key in list(row):
                if str(key).startswith("_cohort_"):
                    row.pop(key, None)

        return projected


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


def _now_ms() -> int:
    return int(time.time() * 1000)


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
    # Cohort accounting fields — consumed by _apply_cross_section after all groups settle.
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
        # Internal cohort fields — NOT persisted (stripped in _apply_cross_section).
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
            readiness=_market_readiness(
                event_anchor=None,
                decision_latest=None,
                target_type=None,
                now_ms=now_ms,
            ),
        )
    social_start = min(window_rows, key=lambda item: int(item.get("received_at_ms") or 0))
    event_anchor = _observation_from_row(social_start, prefix="event_price", source="event_anchor")
    latest_row = max(
        window_rows,
        key=lambda item: int(item.get("decision_latest_observed_at_ms") or 0),
    )
    decision_latest = _observation_from_row(latest_row, prefix="decision_latest", source="decision_latest")
    return _market_context_dict(
        event_anchor=event_anchor,
        decision_latest=decision_latest,
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
    readiness: dict[str, Any],
) -> dict[str, Any]:
    return {
        "event_anchor": event_anchor,
        "decision_latest": decision_latest,
        "readiness": readiness,
    }


def _observation_from_row(row: dict[str, Any], *, prefix: str, source: str) -> dict[str, Any] | None:
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
        "source": source,
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
