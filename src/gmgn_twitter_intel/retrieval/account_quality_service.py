from __future__ import annotations

from collections import defaultdict
from typing import Any

from ..storage.account_quality_repository import AccountQualityRepository

EARLY_AUTHOR_MS = 5 * 60_000
MIN_OUTCOME_HORIZON_MS = 5 * 60_000


class AccountQualityService:
    def __init__(self, *, signals, repository: AccountQualityRepository):
        self.signals = signals
        self.repository = repository
        self.conn: Any = signals.conn

    def backfill_account_token_call_stats(self, *, limit: int = 1000) -> dict[str, Any]:
        rows = self._account_token_rows(limit=limit)
        handles_touched: set[str] = set()
        for row in rows:
            handle = str(row["handle"])
            token_id = str(row["token_id"])
            first_mention_ms = int(row["first_mention_ms"])
            latest_mention_ms = int(row["latest_mention_ms"])
            mention_count = int(row["mention_count"])
            follower_max = _int_or_none(row.get("follower_max"))
            watched_status = "watched" if int(row.get("watched_count") or 0) else "public"
            outcome = self._token_outcome(token_id=token_id, first_mention_ms=first_mention_ms)
            self.repository.upsert_profile(
                handle=handle,
                first_seen_ms=first_mention_ms,
                latest_seen_ms=latest_mention_ms,
                follower_max=follower_max,
                watched_status=watched_status,
                commit=False,
            )
            self.repository.upsert_token_call_stat(
                handle=handle,
                token_id=token_id,
                first_mention_ms=first_mention_ms,
                mention_count=mention_count,
                was_early_author=first_mention_ms <= int(row["global_first_mention_ms"]) + EARLY_AUTHOR_MS,
                price_change_5m_pct=outcome["price_change_5m_pct"],
                price_change_1h_pct=outcome["price_change_1h_pct"],
                price_change_24h_pct=outcome["price_change_24h_pct"],
                max_drawdown_1h_pct=outcome["max_drawdown_1h_pct"],
                outcome_status=outcome["outcome_status"],
                commit=False,
            )
            handles_touched.add(handle)
        for handle in sorted(handles_touched):
            self._write_quality_snapshot(handle)
        self.conn.commit()
        return {
            "accounts_touched": len(handles_touched),
            "stats_upserted": len(rows),
        }

    def account_quality(self, handle: str) -> dict[str, Any]:
        data = self.repository.account_quality(handle)
        return _account_quality_payload(data)

    def account_quality_for_handles(self, handles: list[str]) -> dict[str, Any]:
        normalized = [_handle(handle) for handle in handles if _handle(handle)]
        seen: set[str] = set()
        unique_handles = [handle for handle in normalized if not (handle in seen or seen.add(handle))]
        accounts = [_account_quality_payload(self.repository.account_quality(handle)) for handle in unique_handles]
        return {
            "query": {"handles": unique_handles},
            "accounts": accounts,
        }

    def _account_token_rows(self, *, limit: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            WITH filtered AS (
              SELECT
                eta.token_id,
                lower(eta.author_handle) AS handle,
                eta.event_id,
                eta.received_at_ms,
                eta.author_followers,
                eta.is_watched
              FROM event_token_attributions eta
              WHERE eta.token_id IS NOT NULL
                AND eta.author_handle IS NOT NULL
                AND eta.author_handle != ''
                AND eta.attribution_status IN ('direct', 'selected')
                AND eta.attribution_weight > 0
                AND eta.chain IS NOT NULL
                AND eta.address IS NOT NULL
                AND eta.chain NOT IN ('unknown', 'evm', 'evm_unknown')
            ),
            token_first AS (
              SELECT token_id, MIN(received_at_ms) AS global_first_mention_ms
              FROM filtered
              GROUP BY token_id
            )
            SELECT
              f.handle,
              f.token_id,
              MIN(f.received_at_ms) AS first_mention_ms,
              MAX(f.received_at_ms) AS latest_mention_ms,
              COUNT(DISTINCT f.event_id) AS mention_count,
              MAX(f.author_followers) AS follower_max,
              SUM(CASE WHEN f.is_watched = true THEN 1 ELSE 0 END) AS watched_count,
              MIN(tf.global_first_mention_ms) AS global_first_mention_ms
            FROM filtered f
            JOIN token_first tf ON tf.token_id = f.token_id
            GROUP BY f.handle, f.token_id
            ORDER BY first_mention_ms DESC, f.handle, f.token_id
            LIMIT %s
            """,
            (max(0, int(limit)),),
        ).fetchall()
        return [dict(row) for row in rows]

    def _token_outcome(self, *, token_id: str, first_mention_ms: int) -> dict[str, Any]:
        rows = self.conn.execute(
            """
            SELECT price, received_at_ms
            FROM token_market_snapshots
            WHERE token_id = %s
              AND received_at_ms >= %s
              AND received_at_ms <= %s
              AND price IS NOT NULL
            ORDER BY received_at_ms ASC
            """,
            (token_id, first_mention_ms, first_mention_ms + 24 * 60 * 60_000),
        ).fetchall()
        if not rows:
            return _empty_outcome("insufficient_market_history")
        first_price = _float_or_none(rows[0]["price"])
        latest_ms = int(rows[-1]["received_at_ms"])
        if first_price is None or first_price <= 0 or latest_ms < first_mention_ms + MIN_OUTCOME_HORIZON_MS:
            return _empty_outcome("insufficient_market_history")
        changes = {
            "price_change_5m_pct": _price_change_at(
                rows,
                start_price=first_price,
                target_ms=first_mention_ms + 5 * 60_000,
            ),
            "price_change_1h_pct": _price_change_at(
                rows,
                start_price=first_price,
                target_ms=first_mention_ms + 60 * 60_000,
            ),
            "price_change_24h_pct": _price_change_at(
                rows,
                start_price=first_price,
                target_ms=first_mention_ms + 24 * 60 * 60_000,
            ),
        }
        drawdown = _max_drawdown(rows, start_price=first_price, before_ms=first_mention_ms + 60 * 60_000)
        outcome_status = (
            "ready"
            if any(value is not None for value in changes.values())
            else "insufficient_market_history"
        )
        return changes | {
            "max_drawdown_1h_pct": drawdown,
            "outcome_status": outcome_status,
        }

    def _write_quality_snapshot(self, handle: str) -> None:
        stats = self.repository.account_quality(handle)["token_call_stats"]
        sample_size = len(stats)
        if sample_size == 0:
            return
        early_count = sum(1 for row in stats if int(row.get("was_early_author") or 0))
        ready_returns = [
            float(row["price_change_1h_pct"])
            for row in stats
            if row.get("price_change_1h_pct") is not None and row.get("outcome_status") == "ready"
        ]
        duplicate_tokens = _duplicate_token_mentions(stats)
        precision_score = None
        avg_return = None
        if ready_returns:
            wins = sum(1 for value in ready_returns if value > 0)
            precision_score = round(100 * wins / len(ready_returns), 2)
            avg_return = round(sum(ready_returns) / len(ready_returns), 6)
        self.repository.insert_quality_snapshot(
            handle=handle,
            window="30d",
            precision_score=precision_score,
            early_call_score=round(100 * early_count / sample_size, 2),
            spam_risk_score=round(min(100.0, duplicate_tokens * 20.0), 2),
            avg_realized_return=avg_return,
            sample_size=sample_size,
            commit=False,
        )


def _account_quality_payload(data: dict[str, Any]) -> dict[str, Any]:
    profile = data.get("profile")
    snapshots = data.get("quality_snapshots") or []
    latest = snapshots[0] if snapshots else None
    sample_size = int(latest.get("sample_size") or 0) if latest else 0
    return {
        "profile": profile,
        "summary": {
            "status": "ready" if sample_size >= 5 else "insufficient_sample",
            "sample_size": sample_size,
            "precision_score": latest.get("precision_score") if latest else None,
            "early_call_score": latest.get("early_call_score") if latest else None,
            "spam_risk_score": latest.get("spam_risk_score") if latest else None,
            "avg_realized_return": latest.get("avg_realized_return") if latest else None,
        },
        "token_call_stats": data.get("token_call_stats") or [],
        "quality_snapshots": snapshots,
    }


def _price_change_at(rows: list[dict[str, Any]], *, start_price: float, target_ms: int) -> float | None:
    candidate = None
    for row in rows:
        if int(row["received_at_ms"]) <= target_ms:
            candidate = row
        else:
            break
    if candidate is None:
        return None
    price = _float_or_none(candidate["price"])
    if price is None:
        return None
    return round((price - start_price) / start_price, 12)


def _max_drawdown(rows: list[dict[str, Any]], *, start_price: float, before_ms: int) -> float | None:
    prices = [
        price
        for row in rows
        if int(row["received_at_ms"]) <= before_ms and (price := _float_or_none(row["price"])) is not None
    ]
    if not prices:
        return None
    return round((min(prices) - start_price) / start_price, 12)


def _duplicate_token_mentions(stats: list[dict[str, Any]]) -> int:
    by_token: defaultdict[str, int] = defaultdict(int)
    for row in stats:
        by_token[str(row.get("token_id"))] += int(row.get("mention_count") or 0)
    return sum(1 for count in by_token.values() if count >= 5)


def _empty_outcome(status: str) -> dict[str, Any]:
    return {
        "price_change_5m_pct": None,
        "price_change_1h_pct": None,
        "price_change_24h_pct": None,
        "max_drawdown_1h_pct": None,
        "outcome_status": status,
    }


def _handle(handle: str) -> str:
    return handle.strip().lstrip("@").lower()


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)
