from __future__ import annotations

import hashlib
import time
from typing import Any

from .harness_credit import assign_cluster_credits, update_weight_stat
from .harness_settlement import abnormal_return, actual_return, normalized_outcome

HORIZON_MS = {
    "6h": 6 * 60 * 60 * 1000,
    "24h": 24 * 60 * 60 * 1000,
}
BASELINE_VERSION = "baseline-zero-v0"


def settle_harness_snapshots(
    *,
    harness,
    tokens,
    horizon: str,
    now_ms: int | None = None,
    limit: int = 100,
) -> dict[str, int]:
    now = now_ms if now_ms is not None else _now_ms()
    horizon_ms = HORIZON_MS[horizon]
    rows = harness.conn.execute(
        """
        SELECT *
        FROM harness_snapshots
        WHERE horizon = ?
          AND outcome_status = 'pending'
          AND decision_time_ms + ? <= ?
        ORDER BY decision_time_ms ASC
        LIMIT ?
        """,
        (horizon, horizon_ms, now, max(0, int(limit))),
    ).fetchall()
    counts = {
        "snapshots_scanned": len(rows),
        "outcomes_written": 0,
        "skipped_missing_market": 0,
        "errors": 0,
    }
    for row in rows:
        try:
            snapshot = harness.snapshot_by_id(str(row["snapshot_id"]))
            if snapshot is None:
                counts["errors"] += 1
                continue
            token_id = _token_id_for_asset(tokens, str(snapshot["asset"]))
            decision_time_ms = int(snapshot["decision_time_ms"])
            entry = tokens.market_snapshot_at_or_before(token_id, decision_time_ms)
            exit_ = tokens.market_snapshot_at_or_before(token_id, decision_time_ms + horizon_ms)
            entry_price = _float_or_none(entry.get("price")) if entry else None
            exit_price = _float_or_none(exit_.get("price")) if exit_ else None
            if (
                token_id is None
                or entry is None
                or exit_ is None
                or int(exit_["received_at_ms"]) <= int(entry["received_at_ms"])
                or entry_price is None
                or exit_price is None
            ):
                counts["skipped_missing_market"] += 1
                continue
            actual = actual_return(entry_price=entry_price, exit_price=exit_price)
            expected = 0.0
            abnormal = abnormal_return(actual, expected)
            realized_vol = max(abs(actual), 1e-6)
            existed = _outcome_exists(harness, str(snapshot["snapshot_id"]))
            harness.record_outcome(
                snapshot_id=snapshot["snapshot_id"],
                settled_at_ms=now,
                actual_return=actual,
                expected_return=expected,
                abnormal_return=abnormal,
                realized_vol=realized_vol,
                normalized_outcome=normalized_outcome(abnormal, realized_vol=realized_vol),
                baseline_version=BASELINE_VERSION,
            )
            if not existed:
                counts["outcomes_written"] += 1
        except Exception:
            counts["errors"] += 1
    return counts


def attribute_harness_credits(*, harness, horizon: str, limit: int = 100) -> dict[str, int]:
    rows = harness.conn.execute(
        """
        SELECT *
        FROM harness_snapshots
        WHERE horizon = ?
          AND outcome_status = 'settled'
          AND credit_status != 'assigned'
        ORDER BY decision_time_ms ASC
        LIMIT ?
        """,
        (horizon, max(0, int(limit))),
    ).fetchall()
    counts = {"snapshots_scanned": len(rows), "credits_written": 0, "errors": 0}
    for row in rows:
        try:
            snapshot = harness.snapshot_by_id(str(row["snapshot_id"]))
            outcome = _outcome_for_snapshot(harness, str(row["snapshot_id"]))
            if snapshot is None or outcome is None:
                counts["errors"] += 1
                continue
            credits = []
            for credit in assign_cluster_credits(
                snapshot.get("event_clusters") or [],
                normalized_outcome=float(outcome["normalized_outcome"]),
            ):
                credit_id = _id("harness_credit", snapshot["snapshot_id"], credit["cluster_id"])
                if _credit_exists(harness, credit_id):
                    continue
                credits.append(
                    {
                        "credit_id": credit_id,
                        "snapshot_id": snapshot["snapshot_id"],
                        "asset": snapshot["asset"],
                        "horizon": snapshot["horizon"],
                        **credit,
                    }
                )
            if credits:
                harness.record_credits(credits)
                counts["credits_written"] += len(credits)
            else:
                harness.conn.execute(
                    "UPDATE harness_snapshots SET credit_status = 'assigned' WHERE snapshot_id = ?",
                    (snapshot["snapshot_id"],),
                )
                harness.conn.commit()
        except Exception:
            counts["errors"] += 1
    return counts


def update_harness_weights(*, harness, limit: int = 1000) -> dict[str, int]:
    groups = _credit_groups(harness, limit=limit)
    updated = 0
    for group in groups:
        stat = update_weight_stat(
            {"n": int(group["n"]) - 1, "mean_credit": float(group["previous_mean"])},
            credit=float(group["last_credit"]),
        )
        harness.upsert_weight(
            key=group["key"],
            weight_type=group["weight_type"],
            asset=group.get("asset"),
            horizon=group["horizon"],
            n=stat["n"],
            mean_credit=stat["mean_credit"],
            weight=stat["weight"],
            status="report_only",
        )
        updated += 1
    return {"weights_updated": updated}


def _credit_groups(harness, *, limit: int) -> list[dict[str, Any]]:
    rows = harness.conn.execute(
        """
        SELECT credit_id, asset, event_type, source, horizon, credit
        FROM harness_credits
        ORDER BY created_at_ms ASC
        LIMIT ?
        """,
        (max(0, int(limit)),),
    ).fetchall()
    grouped: dict[tuple[str, str, str | None, str], list[float]] = {}
    for row in rows:
        credit = float(row["credit"])
        grouped.setdefault(("event_type", str(row["event_type"]), None, str(row["horizon"])), []).append(credit)
        grouped.setdefault(("source", str(row["source"]), None, str(row["horizon"])), []).append(credit)
        grouped.setdefault(("horizon", str(row["horizon"]), None, str(row["horizon"])), []).append(credit)
        grouped.setdefault(
            ("asset_event_type", str(row["event_type"]), str(row["asset"]), str(row["horizon"])),
            [],
        ).append(credit)

    result = []
    for (weight_type, name, asset, horizon), credits in grouped.items():
        previous = credits[:-1]
        previous_mean = sum(previous) / len(previous) if previous else 0.0
        key = f"{weight_type}:{asset + ':' if asset else ''}{name}:{horizon}"
        result.append(
            {
                "key": key,
                "weight_type": weight_type,
                "asset": asset,
                "horizon": horizon,
                "n": len(credits),
                "previous_mean": previous_mean,
                "last_credit": credits[-1],
            }
        )
    return result


def _token_id_for_asset(tokens, asset: str) -> str | None:
    if asset.startswith("token:"):
        return asset
    aliases = tokens.aliases_for_symbol(asset)
    return aliases[0] if len(aliases) == 1 else None


def _outcome_exists(harness, snapshot_id: str) -> bool:
    row = harness.conn.execute("SELECT 1 FROM harness_outcomes WHERE snapshot_id = ?", (snapshot_id,)).fetchone()
    return row is not None


def _credit_exists(harness, credit_id: str) -> bool:
    row = harness.conn.execute("SELECT 1 FROM harness_credits WHERE credit_id = ?", (credit_id,)).fetchone()
    return row is not None


def _outcome_for_snapshot(harness, snapshot_id: str) -> dict[str, Any] | None:
    row = harness.conn.execute("SELECT * FROM harness_outcomes WHERE snapshot_id = ?", (snapshot_id,)).fetchone()
    return dict(row) if row else None


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _now_ms() -> int:
    return int(time.time() * 1000)
