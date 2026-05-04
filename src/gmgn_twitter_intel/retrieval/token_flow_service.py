from __future__ import annotations

import json
import time
from typing import Any

from .diffusion_health import diffusion_health
from .rolling_token_flow import RollingTokenFlow
from .token_baseline import token_baseline
from .token_signal_scoring import evidence_score, signal_block

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
        attribution = self._attribution_block(row)
        evidence_highlights = self._evidence_items(row, diffusion=diffusion, market=market)
        evidence_highlight_best = evidence_highlights[0] if evidence_highlights else None
        signal = signal_block(
            row,
            market=market,
            flow=flow,
            diffusion=diffusion,
            watch=watch,
            evidence_highlight_best=evidence_highlight_best,
        )
        return {
            "identity": self._identity_block(row, token),
            "market": market,
            "flow": flow,
            "baseline": baseline,
            "diffusion": diffusion,
            "fresh": fresh,
            "watch": watch,
            "attribution": attribution,
            "signal": signal,
            "evidence_highlight_best": evidence_highlight_best,
            "evidence_highlights": evidence_highlights,
            "evidence_total_count": evidence_total_count,
            "posts_query": self._posts_query(row, window=window, scope=scope),
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
        start_ms = int(row.get("window_start_ms") or reference_ms)
        end_snapshot = self.tokens.market_snapshot_at_or_before(row.get("token_id"), reference_ms)
        if end_snapshot is None:
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
                "price_change_window_pct": None,
                "price_at_window_start": None,
                "price_at_window_end": None,
                "price_change_status": "missing_market",
            }

        start_snapshot = self.tokens.market_snapshot_at_or_before(row.get("token_id"), start_ms)
        age_ms = max(0, reference_ms - int(end_snapshot["received_at_ms"]))
        market_status = "fresh" if age_ms <= FRESH_MARKET_MS else "stale"
        start_price = _float_or_none(start_snapshot.get("price")) if start_snapshot else None
        end_price = _float_or_none(end_snapshot.get("price"))
        raw = _raw_snapshot(end_snapshot)
        price_change_status = "insufficient_history"
        price_change = None
        if (
            start_snapshot is not None
            and start_snapshot.get("snapshot_id") != end_snapshot.get("snapshot_id")
            and start_price
            and end_price is not None
        ):
            price_change = round((end_price - start_price) / start_price, 12)
            price_change_status = "ready"
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
            "price_change_window_pct": price_change,
            "price_at_window_start": start_price,
            "price_at_window_end": end_price,
            "price_change_status": price_change_status,
        }

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

    def _attribution_block(self, row: dict[str, Any]) -> dict[str, Any]:
        reasons = [str(item) for item in row.get("attribution_reasons", []) if item]
        risks = [str(item) for item in row.get("attribution_risks", []) if item]
        return {
            "status": "selected" if int(row.get("symbol_mention_count") or 0) else "direct",
            "avg_confidence": float(row.get("avg_attribution_confidence") or 0.0),
            "selected_symbol_mentions": int(row.get("selected_symbol_mentions") or 0),
            "candidate_count": int(row.get("candidate_count") or 0),
            "reasons": reasons,
            "risks": risks,
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

    def _evidence_items(
        self,
        row: dict[str, Any],
        *,
        diffusion: dict[str, Any],
        market: dict[str, Any],
    ) -> list[dict[str, Any]]:
        reference_ms = int(row.get("window_end_ms") or _now_ms())
        items = []
        for event in row.get("top_events", []):
            if not isinstance(event, dict) or not event.get("event_id"):
                continue
            score_payload = evidence_score(
                event,
                identity_status=str(row["identity_status"]),
                diffusion=diffusion,
                market=market,
                event_age_ms=_age_ms(reference_ms, _int_or_none(event.get("received_at_ms"))),
            )
            items.append(
                {
                    "event_id": event.get("event_id"),
                    "evidence_type": event.get("mention_source") or event.get("source") or "event_token_mention",
                    "handle": event.get("author_handle"),
                    "text": event.get("text_clean"),
                    "received_at_ms": event.get("received_at_ms"),
                    "url": event.get("canonical_url"),
                    "attribution_status": event.get("attribution_status"),
                    "attribution_confidence": event.get("attribution_confidence"),
                    "attribution_weight": event.get("attribution_weight"),
                    **score_payload,
                }
            )
        items.sort(
            key=lambda item: (
                int(item["score"]),
                _evidence_type_priority(str(item.get("evidence_type") or "")),
                int(item.get("received_at_ms") or 0),
            ),
            reverse=True,
        )
        return items

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


def _token_flow_rank_key(item: dict[str, Any]) -> tuple[int, int, int, float, int, int]:
    decision_priority = {"driver": 3, "watch": 2, "discard": 1}
    signal = item.get("signal") or {}
    flow = item.get("flow") or {}
    fresh = item.get("fresh") or {}
    latest_age = fresh.get("latest_evidence_age_ms")
    freshness_rank = -int(latest_age) if latest_age is not None else -10**18
    return (
        decision_priority.get(str(signal.get("decision") or ""), 0),
        int(signal.get("score") or 0),
        int(flow.get("watched_mentions") or 0),
        float(flow.get("z_score") or flow.get("new_burst_score") or 0.0),
        int(flow.get("mentions") or 0),
        freshness_rank,
    )


def _evidence_type_priority(value: str) -> int:
    if value == "gmgn_token_payload":
        return 3
    if value in {"ca", "regex", "contract_address"} or "ca" in value:
        return 2
    if value == "cashtag":
        return 1
    return 0


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
