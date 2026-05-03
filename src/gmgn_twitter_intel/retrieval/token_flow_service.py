from __future__ import annotations

import time
from statistics import mean, pstdev
from typing import Any

from .token_signal_scoring import evidence_score, signal_block, source_quality, top_author_share

BASELINE_LIMITS = {
    "1m": 60,
    "5m": 24,
    "1h": 48,
    "24h": 14,
}
FRESH_MARKET_MS = 30 * 60_000


class TokenFlowService:
    def __init__(self, *, signals, tokens):
        self.signals = signals
        self.tokens = tokens

    def token_flow(self, *, window: str, limit: int = 20, scope: str = "all") -> list[dict[str, Any]]:
        rows = self.signals.token_flow(window=window, limit=limit, watched_only=scope == "matched")
        return [self._token_flow_item(row, window=window) for row in rows]

    def _token_flow_item(self, row: dict[str, Any], *, window: str) -> dict[str, Any]:
        token = self.tokens.get_token(row.get("token_id"))
        baseline = self._baseline_block(row, window=window)
        market = self._market_block(row)
        flow = self._flow_block(row, baseline=baseline)
        sources = self._sources_block(row)
        fresh = self._fresh_block(row, market=market)
        evidence = self._evidence_items(row, sources=sources, market=market)
        evidence_best = evidence[0] if evidence else None
        signal = signal_block(
            row,
            market=market,
            flow=flow,
            sources=sources,
            evidence_best=evidence_best,
        )
        return {
            "identity": self._identity_block(row, token),
            "market": market,
            "flow": flow,
            "sources": sources,
            "fresh": fresh,
            "signal": signal,
            "evidence_best": evidence_best,
            "evidence": evidence,
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
        history = self.signals.token_window_history(
            identity_key=str(row["identity_key"]),
            window=window,
            before_start_ms=int(row["window_start_ms"]),
            limit=BASELINE_LIMITS.get(window, 24),
        )
        counts = [float(item["mention_count"]) for item in history]
        previous_mentions = int(counts[0]) if counts else 0
        if len(counts) < 3:
            return {
                "baseline_status": "insufficient_history",
                "sample_count": len(counts),
                "baseline_mean": None,
                "baseline_stddev": None,
                "z_score": None,
                "previous_mentions": previous_mentions,
            }
        baseline_mean = mean(counts)
        baseline_stddev = pstdev(counts) or 0.0
        current = float(row["mention_count"])
        z_score = (current - baseline_mean) / baseline_stddev if baseline_stddev else 0.0
        return {
            "baseline_status": "ready",
            "sample_count": len(counts),
            "baseline_mean": baseline_mean,
            "baseline_stddev": baseline_stddev,
            "z_score": z_score,
            "previous_mentions": previous_mentions,
        }

    def _market_block(self, row: dict[str, Any]) -> dict[str, Any]:
        reference_ms = int(row.get("window_end_ms") or _now_ms())
        start_ms = int(row.get("window_start_ms") or reference_ms)
        end_snapshot = self.tokens.market_snapshot_at_or_before(row.get("token_id"), reference_ms)
        if end_snapshot is None:
            return {
                "market_status": "missing",
                "price": None,
                "market_cap": None,
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
        else:
            previous_price = _float_or_none(end_snapshot.get("previous_price"))
            if previous_price and end_price is not None:
                start_price = previous_price
                price_change = round((end_price - previous_price) / previous_price, 12)
                price_change_status = "snapshot_previous"
        return {
            "market_status": market_status,
            "price": end_price,
            "market_cap": end_snapshot.get("market_cap"),
            "snapshot_age_ms": age_ms,
            "snapshot_received_at_ms": end_snapshot.get("received_at_ms"),
            "price_change_window_pct": price_change,
            "price_at_window_start": start_price,
            "price_at_window_end": end_price,
            "price_change_status": price_change_status,
        }

    def _flow_block(self, row: dict[str, Any], *, baseline: dict[str, Any]) -> dict[str, Any]:
        mentions = int(row["mention_count"])
        previous_mentions = int(baseline["previous_mentions"])
        mention_delta = mentions - previous_mentions
        mention_delta_pct = (mention_delta / previous_mentions) if previous_mentions else None
        return {
            "window": row["window"],
            "window_start_ms": row["window_start_ms"],
            "window_end_ms": row["window_end_ms"],
            "mentions": mentions,
            "watched_mentions": int(row["watched_mention_count"]),
            "previous_mentions": previous_mentions,
            "mention_delta": mention_delta,
            "mention_delta_pct": mention_delta_pct,
            "z_score": baseline["z_score"],
            "stream_dominance": row["market_mindshare"],
            "baseline_status": baseline["baseline_status"],
            "baseline_sample_count": baseline["sample_count"],
        }

    def _sources_block(self, row: dict[str, Any]) -> dict[str, Any]:
        author_stats = row.get("top_authors")
        if not isinstance(author_stats, list):
            author_stats = self.signals.token_window_author_stats(
                identity_key=str(row["identity_key"]),
                window_start_ms=int(row["window_start_ms"]),
                window_end_ms=int(row["window_end_ms"]),
            )
        top_authors = [
            {
                "handle": item.get("handle"),
                "count": int(item.get("count") or 0),
                "followers": int(item.get("followers") or 0),
                "watched_count": int(item.get("watched_count") or 0),
            }
            for item in author_stats
        ]
        unique_authors = len(top_authors)
        watched_authors = sum(1 for item in top_authors if int(item["watched_count"]) > 0)
        weighted_reach = sum(int(item["followers"]) for item in top_authors)
        author_share = top_author_share(top_authors, mentions=int(row["mention_count"]))
        score, reasons = source_quality(
            identity_status=str(row["identity_status"]),
            mentions=int(row["mention_count"]),
            unique_authors=unique_authors,
            watched_authors=watched_authors,
            weighted_reach=weighted_reach,
            top_author_share=author_share,
        )
        return {
            "unique_authors": unique_authors,
            "watched_authors": watched_authors,
            "weighted_reach": weighted_reach,
            "top_author_share": author_share,
            "top_authors": top_authors[:20],
            "source_quality_score": score,
            "source_quality_reasons": reasons,
        }

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
            bounds = self.signals.token_mention_bounds(identity_key=str(row["identity_key"]))
        first_seen_ms = _int_or_none(bounds.get("first_seen_ms"))
        latest_seen_ms = _int_or_none(bounds.get("latest_seen_ms"))
        first_watched_seen_ms = _int_or_none(bounds.get("first_watched_seen_ms"))
        return {
            "latest_evidence_age_ms": _age_ms(reference_ms, latest_seen_ms),
            "first_seen_age_ms": _age_ms(reference_ms, first_seen_ms),
            "market_snapshot_age_ms": market["snapshot_age_ms"],
            "is_new_token": _in_window(first_seen_ms, window_start_ms, window_end_ms),
            "is_first_seen_by_watched": _in_window(first_watched_seen_ms, window_start_ms, window_end_ms),
        }

    def _evidence_items(
        self,
        row: dict[str, Any],
        *,
        sources: dict[str, Any],
        market: dict[str, Any],
    ) -> list[dict[str, Any]]:
        reference_ms = int(row.get("window_end_ms") or _now_ms())
        items = []
        for event in row.get("top_events", []):
            if not isinstance(event, dict) or not event.get("event_id"):
                continue
            score, reasons = evidence_score(
                event,
                identity_status=str(row["identity_status"]),
                sources=sources,
                market=market,
                event_age_ms=_age_ms(reference_ms, _int_or_none(event.get("received_at_ms"))),
            )
            items.append(
                {
                    "event_id": event.get("event_id"),
                    "score": score,
                    "handle": event.get("author_handle"),
                    "text": event.get("text_clean"),
                    "received_at_ms": event.get("received_at_ms"),
                    "url": event.get("canonical_url"),
                    "reasons": reasons,
                }
            )
        items.sort(key=lambda item: (int(item["score"]), int(item.get("received_at_ms") or 0)), reverse=True)
        return items


def _age_ms(reference_ms: int, value: int | None) -> int | None:
    if value is None:
        return None
    return max(0, reference_ms - value)


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _in_window(value: int | None, start_ms: int, end_ms: int) -> bool:
    return value is not None and start_ms <= value < end_ms


def _now_ms() -> int:
    return int(time.time() * 1000)
