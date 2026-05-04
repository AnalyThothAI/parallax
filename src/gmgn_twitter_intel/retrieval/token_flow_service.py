from __future__ import annotations

import json
import time
from typing import Any

from .diffusion_health import diffusion_health
from .discussion_quality_scoring import discussion_quality_score
from .opportunity_scoring import opportunity_score
from .post_text_quality import post_text_features
from .propagation_scoring import propagation_score
from .rolling_token_flow import RollingTokenFlow
from .social_heat_scoring import social_heat_score
from .timing_scoring import timing_score
from .token_baseline import token_baseline
from .tradeability_scoring import tradeability_score

FRESH_MARKET_MS = 30 * 60_000


class TokenFlowService:
    def __init__(self, *, signals, tokens, enrichment=None):
        self.signals = signals
        self.tokens = tokens
        self.enrichment = enrichment

    def token_flow(
        self,
        *,
        window: str,
        limit: int = 20,
        scope: str = "all",
        now_ms: int | None = None,
    ) -> list[dict[str, Any]]:
        requested_limit = max(0, int(limit))
        if requested_limit == 0:
            return []
        candidate_limit = max(requested_limit, min(max(requested_limit * 5, 100), 500))
        rows = RollingTokenFlow(self.signals.conn).token_flow(
            window=window,
            limit=candidate_limit,
            watched_only=scope == "matched",
            now_ms=now_ms,
        )
        watched_only = scope == "matched"
        evidence_counts = self._evidence_total_counts(rows, watched_only=watched_only)
        items = [
            self._token_flow_item(
                row,
                window=window,
                scope=scope,
                evidence_total_count=evidence_counts.get(str(row.get("token_id")), 0),
            )
            for row in rows
        ]
        items.sort(key=_token_flow_rank_key, reverse=True)
        return items[:requested_limit]

    def _token_flow_item(
        self,
        row: dict[str, Any],
        *,
        window: str,
        scope: str,
        evidence_total_count: int,
    ) -> dict[str, Any]:
        token = self.tokens.get_token(row.get("token_id"))
        baseline = self._baseline_block(row, window=window)
        market = self._market_block(row)
        flow = self._flow_block(row, baseline=baseline)
        diffusion = self._diffusion_block(row)
        fresh = self._fresh_block(row, market=market)
        watch = self._watch_block(row)
        identity = self._identity_block(row, token)
        social_heat = social_heat_score(self._social_heat_features(row, flow=flow, fresh=fresh)) | {
            "window": window,
            "mentions": flow["mentions"],
        }
        discussion_quality = discussion_quality_score(
            self._discussion_quality_features(row, flow=flow, diffusion=diffusion)
        )
        propagation = propagation_score(self._propagation_features(row, diffusion=diffusion, watch=watch))
        tradeability = tradeability_score(self._tradeability_features(identity=identity, market=market))
        timing = timing_score(self._timing_features(row, market=market, social_heat=social_heat))
        opportunity = opportunity_score(
            {
                "heat": social_heat,
                "quality": discussion_quality,
                "propagation": propagation,
                "tradeability": tradeability,
                "timing": timing,
            }
        )
        return {
            "identity": identity,
            "market": market,
            "flow": flow,
            "social_heat": social_heat,
            "discussion_quality": discussion_quality,
            "propagation": propagation,
            "tradeability": tradeability,
            "timing": timing,
            "opportunity": opportunity,
            "evidence_total_count": evidence_total_count,
            "posts_query": self._posts_query(row, window=window, scope=scope),
            "timeline_query": self._timeline_query(row, window=window, scope=scope),
        }

    def _identity_block(self, row: dict[str, Any], token: dict[str, Any] | None) -> dict[str, Any]:
        return {
            "identity_key": str(row["identity_key"]),
            "identity_status": row["identity_status"],
            "token_id": row.get("token_id"),
            "chain": row.get("chain"),
            "address": row.get("address"),
            "symbol": token.get("symbol") if token else row.get("symbol"),
        }

    def _baseline_block(self, row: dict[str, Any], *, window: str) -> dict[str, Any]:
        if isinstance(row.get("baseline"), dict):
            return row["baseline"]
        return token_baseline(slot_counts=[], current_mentions=int(row.get("mention_count") or 0))

    def _market_block(self, row: dict[str, Any]) -> dict[str, Any]:
        reference_ms = int(row.get("window_end_ms") or _now_ms())
        window_start_ms = int(row.get("window_start_ms") or reference_ms)
        social_start_ms = int(row.get("first_seen_ms") or window_start_ms)
        token_id = row.get("token_id")
        end_snapshot = self.tokens.market_snapshot_at_or_before(token_id, reference_ms)
        if end_snapshot is None:
            observation_status = self._market_observation_status(
                token_id=token_id,
                start_ms=social_start_ms,
                end_ms=reference_ms,
                has_market_snapshot=False,
                has_ready_history=False,
            )
            return {
                "market_status": "missing",
                "price": None,
                "market_cap": None,
                "liquidity": None,
                "pool_status": "missing",
                "holder_count": None,
                "volume_24h": None,
                "snapshot_age_ms": None,
                "snapshot_received_at_ms": None,
                "social_signal_start_ms": social_start_ms,
                "reference_ms": reference_ms,
                "price_at_social_start": None,
                "price_at_reference": None,
                "price_change_since_social_pct": None,
                "price_before_social_start": None,
                "price_change_before_social_pct": None,
                "market_observation_status": observation_status,
                "price_change_status": _price_change_status(
                    observation_status=observation_status,
                    has_ready_history=False,
                    missing_market=True,
                ),
            }

        start_snapshot = self.tokens.market_snapshot_at_or_before(token_id, social_start_ms)
        before_snapshot = self.tokens.market_snapshot_at_or_before(token_id, window_start_ms)
        if before_snapshot is None and social_start_ms > 0:
            before_snapshot = self.tokens.market_snapshot_at_or_before(token_id, social_start_ms - 1)
        age_ms = max(0, reference_ms - int(end_snapshot["received_at_ms"]))
        market_status = "fresh" if age_ms <= FRESH_MARKET_MS else "stale"
        start_price = _float_or_none(start_snapshot.get("price")) if start_snapshot else None
        end_price = _float_or_none(end_snapshot.get("price"))
        before_price = _float_or_none(before_snapshot.get("price")) if before_snapshot else None
        raw = _raw_snapshot(end_snapshot)
        price_change = None
        has_ready_history = False
        if (
            start_snapshot is not None
            and start_snapshot.get("snapshot_id") != end_snapshot.get("snapshot_id")
            and start_price
            and end_price is not None
        ):
            price_change = round((end_price - start_price) / start_price, 12)
            has_ready_history = True
        price_change_before = _price_change_between(before_snapshot, start_snapshot)
        observation_status = self._market_observation_status(
            token_id=token_id,
            start_ms=social_start_ms,
            end_ms=reference_ms,
            has_market_snapshot=True,
            has_ready_history=has_ready_history,
        )
        liquidity = _first_number(raw, ["liquidity", "liquidity_usd", "pool.liquidity", "pool.liquidity_usd"])
        pool_address = _first_string(raw, ["pool.pool_address", "pool.address", "pool"])
        return {
            "market_status": market_status,
            "price": end_price,
            "market_cap": end_snapshot.get("market_cap"),
            "liquidity": liquidity,
            "pool_status": "ready" if pool_address else "missing",
            "holder_count": _first_number(raw, ["holder_count", "holders", "holder"]),
            "volume_24h": _first_number(raw, ["volume_24h", "volume", "stat.volume_24h", "stat.volume"]),
            "snapshot_age_ms": age_ms,
            "snapshot_received_at_ms": end_snapshot.get("received_at_ms"),
            "social_signal_start_ms": social_start_ms,
            "reference_ms": reference_ms,
            "price_at_social_start": start_price,
            "price_at_reference": end_price,
            "price_change_since_social_pct": price_change,
            "price_before_social_start": before_price,
            "price_change_before_social_pct": price_change_before,
            "market_observation_status": observation_status,
            "price_change_status": _price_change_status(
                observation_status=observation_status,
                has_ready_history=has_ready_history,
                missing_market=False,
            ),
        }

    def _market_observation_status(
        self,
        *,
        token_id: str | None,
        start_ms: int,
        end_ms: int,
        has_market_snapshot: bool,
        has_ready_history: bool,
    ) -> str:
        if not token_id:
            return "missing_observation"
        rows = self.tokens.conn.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM token_market_observations
            WHERE token_id = ?
              AND target_received_at_ms >= ?
              AND target_received_at_ms <= ?
            GROUP BY status
            """,
            (token_id, start_ms, end_ms),
        ).fetchall()
        counts = {str(row["status"]): int(row["count"] or 0) for row in rows}
        if has_ready_history:
            return "ready"
        for status in ("pending", "running"):
            if counts.get(status):
                return status
        for status in (
            "provider_not_configured",
            "provider_error",
            "rate_limited",
            "dead",
            "provider_not_found",
        ):
            if counts.get(status):
                return status
        if counts.get("ready") or counts.get("cached") or has_market_snapshot:
            return "ready"
        return "missing_observation"

    def _flow_block(self, row: dict[str, Any], *, baseline: dict[str, Any]) -> dict[str, Any]:
        mentions = int(row["mention_count"])
        previous_mentions = int(row.get("previous_mentions") if row.get("previous_mentions") is not None else 0)
        mention_delta = mentions - previous_mentions
        mention_delta_pct = (mention_delta / previous_mentions) if previous_mentions else None
        return {
            "window": row["window"],
            "window_start_ms": row["window_start_ms"],
            "window_end_ms": row["window_end_ms"],
            "mentions": mentions,
            "direct_mentions": int(row.get("direct_mention_count") or 0),
            "symbol_mentions": int(row.get("symbol_mention_count") or 0),
            "weighted_mentions": float(row.get("weighted_mention_count") or mentions),
            "avg_attribution_confidence": float(row.get("avg_attribution_confidence") or 0.0),
            "watched_mentions": int(row["watched_mention_count"]),
            "previous_mentions": previous_mentions,
            "mention_delta": mention_delta,
            "mention_delta_pct": mention_delta_pct,
            "z_score": baseline["z_score"],
            "new_burst_score": baseline["new_burst_score"],
            "stream_dominance": row["market_mindshare"],
            "baseline_status": baseline["baseline_status"],
            "baseline_sample_count": baseline["sample_count"],
        }

    def _diffusion_block(self, row: dict[str, Any]) -> dict[str, Any]:
        mentions = row.get("events_for_diffusion")
        if not isinstance(mentions, list):
            mentions = []
        watched_author_handles = {
            str(item.get("author_handle"))
            for item in mentions
            if isinstance(item, dict) and item.get("author_handle") and item.get("is_watched")
        }
        return diffusion_health(mentions=mentions, watched_author_handles=watched_author_handles)

    def _fresh_block(self, row: dict[str, Any], *, market: dict[str, Any]) -> dict[str, Any]:
        reference_ms = int(row.get("window_end_ms") or _now_ms())
        window_start_ms = int(row.get("window_start_ms") or reference_ms)
        window_end_ms = int(row.get("window_end_ms") or reference_ms)
        bounds = {
            "first_seen_ms": row.get("first_seen_ms"),
            "latest_seen_ms": row.get("latest_seen_ms"),
            "first_watched_seen_ms": row.get("first_watched_seen_ms"),
        }
        if bounds["first_seen_ms"] is None and bounds["latest_seen_ms"] is None:
            bounds = self.signals.token_attribution_bounds(identity_key=str(row["identity_key"]))
        first_seen_ms = _int_or_none(bounds.get("first_seen_ms"))
        latest_seen_ms = _int_or_none(bounds.get("latest_seen_ms"))
        first_watched_seen_ms = _int_or_none(bounds.get("first_watched_seen_ms"))
        return {
            "latest_evidence_age_ms": _age_ms(reference_ms, latest_seen_ms),
            "first_seen_age_ms": _age_ms(reference_ms, first_seen_ms),
            "market_snapshot_age_ms": market["snapshot_age_ms"],
            "is_new_local_evidence": _in_window(first_seen_ms, window_start_ms, window_end_ms),
            "is_first_seen_by_watched": _in_window(first_watched_seen_ms, window_start_ms, window_end_ms),
        }

    def _watch_block(self, row: dict[str, Any]) -> dict[str, Any]:
        direct_mentions = int(row.get("watched_mention_count") or 0)
        direct_authors = int(row.get("watched_author_count") or 0)
        seed_links = self._seed_links(row)
        top_seed = seed_links[0]["seed"] if seed_links else None
        seed_link_count = len(seed_links)
        if direct_mentions > 0:
            return {
                "status": "direct_watch",
                "direct_mentions": direct_mentions,
                "direct_authors": direct_authors,
                "seed_link_count": seed_link_count,
                "top_seed": top_seed,
                "reasons": ["watched_direct_mention"],
                "risks": [],
            }
        if seed_links:
            return {
                "status": "seed_linked",
                "direct_mentions": direct_mentions,
                "direct_authors": direct_authors,
                "seed_link_count": seed_link_count,
                "top_seed": top_seed,
                "reasons": ["watched_seed_link"],
                "risks": [],
            }
        return {
            "status": "public_only",
            "direct_mentions": direct_mentions,
            "direct_authors": direct_authors,
            "seed_link_count": 0,
            "top_seed": None,
            "reasons": ["public_stream_evidence"],
            "risks": ["no_watched_confirmation"],
        }

    def _social_heat_features(
        self,
        row: dict[str, Any],
        *,
        flow: dict[str, Any],
        fresh: dict[str, Any],
    ) -> dict[str, Any]:
        mentions = int(flow.get("mentions") or 0)
        watched_mentions = int(flow.get("watched_mentions") or 0)
        return {
            "mentions": mentions,
            "mentions_5m": mentions if row.get("window") == "5m" else 0,
            "mentions_1h": mentions if row.get("window") == "1h" else mentions,
            "mentions_24h": mentions if row.get("window") == "24h" else 0,
            "weighted_mentions": flow.get("weighted_mentions"),
            "previous_mentions": flow.get("previous_mentions"),
            "mention_delta": flow.get("mention_delta"),
            "mention_delta_pct": flow.get("mention_delta_pct"),
            "z_score": flow.get("z_score"),
            "new_burst_score": flow.get("new_burst_score"),
            "stream_share": flow.get("stream_dominance"),
            "watched_share": watched_mentions / mentions if mentions else 0.0,
            "is_new_local_evidence": fresh.get("is_new_local_evidence"),
            "is_first_seen_by_watched": fresh.get("is_first_seen_by_watched"),
        }

    def _discussion_quality_features(
        self,
        row: dict[str, Any],
        *,
        flow: dict[str, Any],
        diffusion: dict[str, Any],
    ) -> dict[str, Any]:
        informative_count = 0
        market_context_count = 0
        for event in row.get("events_for_diffusion", []):
            if not isinstance(event, dict):
                continue
            features = post_text_features(event.get("text_clean") or event.get("search_text"))
            informative_count += 1 if features["informative"] else 0
            market_context_count += 1 if features["has_market_context"] else 0
        return {
            "mentions": flow.get("mentions"),
            "direct_mentions": flow.get("direct_mentions"),
            "avg_attribution_confidence": flow.get("avg_attribution_confidence"),
            "duplicate_text_share": diffusion.get("duplicate_text_share"),
            "informative_post_count": informative_count,
            "watched_source_count": row.get("watched_author_count"),
            "market_context_count": market_context_count,
        }

    def _propagation_features(
        self,
        row: dict[str, Any],
        *,
        diffusion: dict[str, Any],
        watch: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "mentions": row.get("mention_count"),
            "independent_authors": diffusion.get("independent_authors"),
            "effective_authors": diffusion.get("effective_authors"),
            "new_authors": diffusion.get("independent_authors"),
            "top_author_share": diffusion.get("top_author_share"),
            "duplicate_text_share": diffusion.get("duplicate_text_share"),
            "watched_author_count": row.get("watched_author_count"),
            "seed_lag_ms": _seed_lag_ms(watch),
            "top_authors": diffusion.get("top_authors") or row.get("top_authors") or [],
        }

    def _tradeability_features(self, *, identity: dict[str, Any], market: dict[str, Any]) -> dict[str, Any]:
        return {
            "identity_status": identity.get("identity_status"),
            "token_id": identity.get("token_id"),
            "chain": identity.get("chain"),
            "address": identity.get("address"),
            "market_status": market.get("market_status"),
            "market_cap": market.get("market_cap"),
            "liquidity": market.get("liquidity"),
            "pool_status": market.get("pool_status"),
        }

    def _timing_features(
        self,
        row: dict[str, Any],
        *,
        market: dict[str, Any],
        social_heat: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "social_signal_start_ms": market.get("social_signal_start_ms"),
            "burst_ms": row.get("latest_seen_ms"),
            "price_change_since_social_pct": market.get("price_change_since_social_pct"),
            "price_change_before_social_pct": market.get("price_change_before_social_pct"),
            "market_observation_status": market.get("market_observation_status"),
            "social_heat_score": social_heat.get("score"),
        }

    def _seed_links(self, row: dict[str, Any]) -> list[dict[str, Any]]:
        if self.enrichment is None:
            return []
        return self.enrichment.seed_links_for_token(
            identity_key=str(row["identity_key"]),
            token_id=row.get("token_id"),
            chain=row.get("chain"),
            address=row.get("address"),
            symbol=row.get("symbol"),
            since_ms=int(row["window_start_ms"]),
            limit=5,
        )

    def _evidence_total_counts(self, rows: list[dict[str, Any]], *, watched_only: bool) -> dict[str, int]:
        if not rows:
            return {}
        token_ids = sorted({str(row.get("token_id")) for row in rows if row.get("token_id")})
        if not token_ids:
            return {}
        watched_clause = "AND eta.is_watched = 1" if watched_only else ""
        placeholders = ",".join("?" for _ in token_ids)
        window_start_ms = int(rows[0]["window_start_ms"])
        window_end_ms = int(rows[0]["window_end_ms"])
        results = self.signals.conn.execute(
            f"""
            SELECT eta.token_id, COUNT(DISTINCT eta.event_id) AS count
            FROM event_token_attributions eta
            WHERE eta.received_at_ms >= ?
              AND eta.received_at_ms < ?
              AND eta.token_id IN ({placeholders})
              AND eta.token_id IS NOT NULL
              AND eta.attribution_status IN ('direct', 'selected')
              AND eta.attribution_weight > 0
              AND eta.chain IS NOT NULL
              AND eta.address IS NOT NULL
              AND eta.chain NOT IN ('unknown', 'evm', 'evm_unknown')
              {watched_clause}
            GROUP BY eta.token_id
            """,
            (window_start_ms, window_end_ms, *token_ids),
        ).fetchall()
        return {str(row["token_id"]): int(row["count"] or 0) for row in results}

    def _posts_query(self, row: dict[str, Any], *, window: str, scope: str) -> dict[str, Any]:
        return {
            "token_id": row.get("token_id"),
            "chain": row.get("chain"),
            "address": row.get("address"),
            "window": window,
            "scope": scope,
        }

    def _timeline_query(self, row: dict[str, Any], *, window: str, scope: str) -> dict[str, Any]:
        return {
            "token_id": row.get("token_id"),
            "chain": row.get("chain"),
            "address": row.get("address"),
            "window": window,
            "bucket": "1m",
            "scope": scope,
        }


def _token_flow_rank_key(item: dict[str, Any]) -> tuple[int, int, int, int, int, int]:
    opportunity = item.get("opportunity") or {}
    heat = item.get("social_heat") or {}
    propagation = item.get("propagation") or {}
    flow = item.get("flow") or {}
    latest_seen = int(flow.get("window_end_ms") or 0)
    return (
        int(opportunity.get("decision_priority") or 0),
        int(opportunity.get("score") or 0),
        int(heat.get("score") or 0),
        int(propagation.get("score") or 0),
        int(flow.get("watched_mentions") or 0),
        latest_seen,
    )


def _seed_lag_ms(watch: dict[str, Any]) -> int | None:
    seed = watch.get("top_seed")
    if not isinstance(seed, dict):
        return None
    value = seed.get("lag_ms")
    return int(value) if value is not None else None


def _age_ms(reference_ms: int, value: int | None) -> int | None:
    if value is None:
        return None
    return max(0, reference_ms - value)


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _price_change_between(start_snapshot: dict[str, Any] | None, end_snapshot: dict[str, Any] | None) -> float | None:
    start_price = _float_or_none(start_snapshot.get("price")) if start_snapshot else None
    end_price = _float_or_none(end_snapshot.get("price")) if end_snapshot else None
    if not start_price or end_price is None:
        return None
    return round((end_price - start_price) / start_price, 12)


def _price_change_status(*, observation_status: str, has_ready_history: bool, missing_market: bool) -> str:
    if observation_status in {"pending", "running"}:
        return "pending_observation"
    if observation_status in {
        "provider_not_configured",
        "provider_not_found",
        "provider_error",
        "rate_limited",
        "dead",
    }:
        return observation_status
    if missing_market:
        return "missing_market"
    return "ready" if has_ready_history else "insufficient_history"


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _in_window(value: int | None, start_ms: int, end_ms: int) -> bool:
    return value is not None and start_ms <= value < end_ms


def _raw_snapshot(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    if not snapshot:
        return {}
    raw_json = snapshot.get("raw_json")
    if not isinstance(raw_json, str):
        return {}
    try:
        raw = json.loads(raw_json)
    except json.JSONDecodeError:
        return {}
    return raw if isinstance(raw, dict) else {}


def _first_number(raw: dict[str, Any], paths: list[str]) -> float | None:
    for path in paths:
        number = _float_or_none(_path_value(raw, path))
        if number is not None:
            return number
    return None


def _first_string(raw: dict[str, Any], paths: list[str]) -> str | None:
    for path in paths:
        value = _path_value(raw, path)
        if isinstance(value, dict):
            continue
        if value is not None:
            text = str(value).strip()
            if text:
                return text
    return None


def _path_value(raw: dict[str, Any], path: str) -> Any:
    current: Any = raw
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _now_ms() -> int:
    return int(time.time() * 1000)
