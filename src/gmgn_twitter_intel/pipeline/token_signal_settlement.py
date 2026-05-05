from __future__ import annotations

import hashlib
import time
from typing import Any

from ..storage.token_repository import TokenRepository
from ..storage.token_signal_repository import TokenSignalRepository

HORIZON_MS = {
    "6h": 6 * 60 * 60_000,
    "24h": 24 * 60 * 60_000,
}
ENTRY_AFTER_MS = 5 * 60_000
ENTRY_BEFORE_AGE_MS = 10 * 60_000
EXIT_TOLERANCE_MS = 30 * 60_000
VOL_FLOOR = 0.03


def select_entry_snapshot(
    tokens: TokenRepository,
    token_id: str,
    decision_time_ms: int,
    *,
    max_after_ms: int = ENTRY_AFTER_MS,
    max_before_age_ms: int = ENTRY_BEFORE_AGE_MS,
) -> dict[str, Any] | None:
    after = tokens.market_snapshot_at_or_after(token_id, decision_time_ms)
    if after is not None and int(after["received_at_ms"]) - decision_time_ms <= max_after_ms:
        return after
    before = tokens.market_snapshot_at_or_before(token_id, decision_time_ms)
    if before is not None and decision_time_ms - int(before["received_at_ms"]) <= max_before_age_ms:
        return before
    return None


def select_exit_snapshot(
    tokens: TokenRepository,
    token_id: str,
    target_time_ms: int,
    *,
    tolerance_ms: int = EXIT_TOLERANCE_MS,
) -> dict[str, Any] | None:
    return tokens.nearest_market_snapshot(token_id, target_ms=target_time_ms, tolerance_ms=tolerance_ms)


def actual_return(entry_price: float, exit_price: float) -> float:
    if entry_price <= 0:
        return 0.0
    return round((exit_price - entry_price) / entry_price, 12)


def abnormal_return(actual: float, benchmark: float) -> float:
    return round(float(actual) - float(benchmark), 12)


def realized_volatility_proxy(
    tokens: TokenRepository,
    token_id: str,
    *,
    start_ms: int,
    end_ms: int,
    fallback_abs_return: float,
) -> float:
    rows = tokens.market_snapshots_between(token_id, start_ms=start_ms, end_ms=end_ms)
    prices = [_float_or_none(row.get("price")) for row in rows]
    prices = [price for price in prices if price is not None and price > 0]
    if len(prices) < 2:
        return abs(float(fallback_abs_return))
    returns = [abs((current - previous) / previous) for previous, current in zip(prices, prices[1:], strict=False)]
    return max(returns, default=abs(float(fallback_abs_return)))


def normalized_outcome_v2(*, abnormal: float, realized_vol: float, vol_floor: float = VOL_FLOOR) -> float:
    denom = max(abs(float(realized_vol)), float(vol_floor))
    return max(-1.0, min(round(float(abnormal) / denom, 12), 1.0))


def settle_token_signal_snapshots(
    *,
    repository: TokenSignalRepository,
    tokens: TokenRepository,
    horizon: str,
    now_ms: int | None = None,
    limit: int = 500,
) -> dict[str, int]:
    now = now_ms if now_ms is not None else _now_ms()
    horizon_ms = HORIZON_MS[horizon]
    snapshots = repository.pending_settlement_snapshots(horizon=horizon, now_ms=now, limit=limit)
    counts = {
        "snapshots_scanned": 0,
        "outcomes_written": 0,
        "missing_entry": 0,
        "missing_exit": 0,
        "missing_price": 0,
        "not_due": 0,
        "errors": 0,
    }
    for snapshot in snapshots:
        try:
            decision_time_ms = int(snapshot["decision_time_ms"])
            if decision_time_ms + horizon_ms > now:
                counts["not_due"] += 1
                continue
            counts["snapshots_scanned"] += 1
            token_id = str(snapshot["token_id"])
            entry = select_entry_snapshot(tokens, token_id, decision_time_ms)
            if entry is None:
                _record_missing(repository, snapshot=snapshot, horizon=horizon, status="missing_entry", now_ms=now)
                counts["missing_entry"] += 1
                counts["outcomes_written"] += 1
                continue
            exit_ = select_exit_snapshot(tokens, token_id, decision_time_ms + horizon_ms)
            if exit_ is None:
                _record_missing(
                    repository,
                    snapshot=snapshot,
                    horizon=horizon,
                    status="missing_exit",
                    now_ms=now,
                    entry=entry,
                )
                counts["missing_exit"] += 1
                counts["outcomes_written"] += 1
                continue
            entry_price = _float_or_none(entry.get("price"))
            exit_price = _float_or_none(exit_.get("price"))
            if entry_price is None or exit_price is None:
                _record_missing(
                    repository,
                    snapshot=snapshot,
                    horizon=horizon,
                    status="missing_price",
                    now_ms=now,
                    entry=entry,
                    exit_=exit_,
                )
                counts["missing_price"] += 1
                counts["outcomes_written"] += 1
                continue
            actual = actual_return(entry_price, exit_price)
            benchmark = 0.0
            abnormal = abnormal_return(actual, benchmark)
            vol = max(
                realized_volatility_proxy(
                    tokens,
                    token_id,
                    start_ms=int(entry["received_at_ms"]),
                    end_ms=int(exit_["received_at_ms"]),
                    fallback_abs_return=abs(actual),
                ),
                VOL_FLOOR,
            )
            repository.record_outcome(
                outcome_id=_outcome_id(str(snapshot["snapshot_id"]), horizon),
                snapshot_id=snapshot["snapshot_id"],
                horizon=horizon,
                status="settled",
                entry_snapshot_id=entry.get("snapshot_id"),
                exit_snapshot_id=exit_.get("snapshot_id"),
                benchmark_snapshot_ids=[],
                entry_price=entry_price,
                exit_price=exit_price,
                benchmark_return=benchmark,
                actual_return=actual,
                abnormal_return=abnormal,
                realized_vol=vol,
                normalized_outcome=normalized_outcome_v2(abnormal=abnormal, realized_vol=vol),
                market_coverage_status="ready",
                settled_at_ms=now,
            )
            counts["outcomes_written"] += 1
        except Exception:
            counts["errors"] += 1
    return counts


def _record_missing(
    repository: TokenSignalRepository,
    *,
    snapshot: dict[str, Any],
    horizon: str,
    status: str,
    now_ms: int,
    entry: dict[str, Any] | None = None,
    exit_: dict[str, Any] | None = None,
) -> None:
    repository.record_outcome(
        outcome_id=_outcome_id(str(snapshot["snapshot_id"]), horizon),
        snapshot_id=snapshot["snapshot_id"],
        horizon=horizon,
        status=status,
        entry_snapshot_id=entry.get("snapshot_id") if entry else None,
        exit_snapshot_id=exit_.get("snapshot_id") if exit_ else None,
        benchmark_snapshot_ids=[],
        entry_price=_float_or_none(entry.get("price")) if entry else None,
        exit_price=_float_or_none(exit_.get("price")) if exit_ else None,
        benchmark_return=None,
        actual_return=None,
        abnormal_return=None,
        realized_vol=None,
        normalized_outcome=None,
        market_coverage_status=status,
        settled_at_ms=now_ms,
    )


def _outcome_id(snapshot_id: str, horizon: str) -> str:
    return hashlib.sha256(f"token_signal_outcome|{snapshot_id}|{horizon}".encode()).hexdigest()


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _now_ms() -> int:
    return int(time.time() * 1000)
