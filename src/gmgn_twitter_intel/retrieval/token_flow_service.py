from __future__ import annotations

import math
import time
from statistics import mean, pstdev
from typing import Any

BASELINE_LIMITS = {
    "1m": 60,
    "5m": 24,
    "1h": 48,
    "24h": 14,
}


class TokenFlowService:
    def __init__(self, *, signals, tokens):
        self.signals = signals
        self.tokens = tokens

    def token_flow(self, *, window: str, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.signals.token_flow(window=window, limit=limit)
        return [self._conviction_item(row, window=window) for row in rows]

    def _conviction_item(self, row: dict[str, Any], *, window: str) -> dict[str, Any]:
        identity_key = str(row["identity_key"])
        token = self.tokens.get_token(row.get("token_id"))
        market = self._market_block(row)
        baseline = self._baseline_block(row, window=window)
        anomaly = self._anomaly_block(row, baseline=baseline, market=market)
        confidence = self._confidence_block(row, baseline=baseline, anomaly=anomaly, market=market)
        return {
            "identity": {
                "identity_key": identity_key,
                "identity_status": row["identity_status"],
                "token_id": row.get("token_id"),
                "chain": row.get("chain"),
                "address": row.get("address"),
                "symbol": token.get("symbol") if token else row.get("symbol"),
            },
            "social": {
                "window": row["window"],
                "window_start_ms": row["window_start_ms"],
                "window_end_ms": row["window_end_ms"],
                "mention_count": row["mention_count"],
                "watched_mention_count": row["watched_mention_count"],
                "unique_author_count": row["unique_author_count"],
                "weighted_reach": row["weighted_reach"],
                "market_mindshare": row["market_mindshare"],
                "watched_mindshare": row["watched_mindshare"],
                "velocity": row["velocity"],
                "top_authors": row.get("top_authors", []),
            },
            "baseline": baseline,
            "anomaly": anomaly,
            "market": market,
            "confidence": confidence,
            "evidence": row.get("top_events", []),
        }

    def _baseline_block(self, row: dict[str, Any], *, window: str) -> dict[str, Any]:
        history = self.signals.token_window_history(
            identity_key=str(row["identity_key"]),
            window=window,
            before_start_ms=int(row["window_start_ms"]),
            limit=BASELINE_LIMITS.get(window, 24),
        )
        counts = [float(item["mention_count"]) for item in history]
        if len(counts) < 3:
            return {
                "baseline_status": "insufficient_history",
                "sample_count": len(counts),
                "baseline_mean": None,
                "baseline_stddev": None,
                "delta_pct": None,
                "z_score": None,
                "percentile": None,
                "acceleration": None,
            }
        baseline_mean = mean(counts)
        baseline_stddev = pstdev(counts) or 0.0
        current = float(row["mention_count"])
        previous = counts[0] if counts else 0.0
        z_score = (current - baseline_mean) / baseline_stddev if baseline_stddev else 0.0
        below_or_equal = sum(1 for value in counts if value <= current)
        return {
            "baseline_status": "ready",
            "sample_count": len(counts),
            "baseline_mean": baseline_mean,
            "baseline_stddev": baseline_stddev,
            "delta_pct": ((current - baseline_mean) / baseline_mean) if baseline_mean else None,
            "z_score": z_score,
            "percentile": below_or_equal / len(counts),
            "acceleration": current - previous,
        }

    def _market_block(self, row: dict[str, Any]) -> dict[str, Any]:
        snapshot = self.tokens.latest_market_snapshot(row.get("token_id"))
        if snapshot is None:
            return {
                "market_status": "missing",
                "market_confirmed": False,
                "price": None,
                "previous_price": None,
                "price_change_pct": None,
                "market_cap": None,
                "snapshot_age_ms": None,
                "snapshot_received_at_ms": None,
            }
        reference_ms = int(row.get("window_end_ms") or _now_ms())
        age_ms = max(0, reference_ms - int(snapshot["received_at_ms"]))
        price = snapshot.get("price")
        previous = snapshot.get("previous_price")
        price_change = None
        if price is not None and previous:
            price_change = (float(price) - float(previous)) / float(previous)
        market_status = "fresh" if age_ms <= 30 * 60_000 else "stale"
        return {
            "market_status": market_status,
            "market_confirmed": market_status == "fresh",
            "price": price,
            "previous_price": previous,
            "price_change_pct": price_change,
            "market_cap": snapshot.get("market_cap"),
            "snapshot_age_ms": age_ms,
            "snapshot_received_at_ms": snapshot.get("received_at_ms"),
        }

    def _anomaly_block(
        self,
        row: dict[str, Any],
        *,
        baseline: dict[str, Any],
        market: dict[str, Any],
    ) -> dict[str, Any]:
        reasons: list[str] = []
        if int(row["watched_mention_count"]) > 0:
            reasons.append("watched_first_mention")
        if baseline.get("z_score") is not None and float(baseline["z_score"]) >= 2:
            reasons.append("social_burst")
        if int(row["unique_author_count"]) >= 3:
            reasons.append("multi_author_convergence")
        if _author_concentration(row) >= 0.75 and int(row["mention_count"]) >= 3:
            reasons.append("author_concentration_high")
        if row["identity_status"] != "resolved_ca":
            reason = "symbol_unresolved" if row["identity_status"] == "unresolved_symbol" else row["identity_status"]
            reasons.append(reason)
        if market["market_confirmed"]:
            reasons.append("market_move_confirmed")
        if market["market_status"] == "missing":
            reasons.append("market_data_missing")
        score = min(
            100,
            round(
                len(reasons) * 14
                + float(row["watched_mindshare"]) * 25
                + math.log1p(row["mention_count"]) * 12
            ),
        )
        return {"score": score, "reasons": reasons}

    def _confidence_block(
        self,
        row: dict[str, Any],
        *,
        baseline: dict[str, Any],
        anomaly: dict[str, Any],
        market: dict[str, Any],
    ) -> dict[str, Any]:
        score = 20
        reasons = ["coverage public_stream"]
        if row.get("token_id"):
            score += 25
            reasons.append("identity resolved")
        if int(row["watched_mention_count"]) > 0:
            score += 15
            reasons.append("watched evidence")
        if int(row["unique_author_count"]) > 1:
            score += 10
            reasons.append("multi-author evidence")
        if market["market_confirmed"]:
            score += 15
            reasons.append("fresh market snapshot")
        if baseline["baseline_status"] == "ready":
            score += 10
            reasons.append("baseline ready")
        else:
            score -= 10
            reasons.append("insufficient baseline")
        if row["identity_status"] in {"unresolved_symbol", "ambiguous_symbol"}:
            score -= 20
            reasons.append(row["identity_status"])
        if "author_concentration_high" in anomaly["reasons"]:
            score -= 10
            reasons.append("author concentration high")
        return {
            "score": max(0, min(100, score)),
            "coverage": "public_stream",
            "coverage_boundary": "GMGN anonymous public stream; not a full X firehose",
            "identity_status": row["identity_status"],
            "market_status": market["market_status"],
            "baseline_status": baseline["baseline_status"],
            "reasons": reasons,
        }


def _author_concentration(row: dict[str, Any]) -> float:
    authors = row.get("top_authors") or []
    if not authors:
        return 0.0
    total = max(1, int(row["mention_count"]))
    counts = [int(author.get("count") or 0) for author in authors if isinstance(author, dict)]
    if not counts:
        return 0.0
    top = max(counts)
    return top / total


def _now_ms() -> int:
    return int(time.time() * 1000)
