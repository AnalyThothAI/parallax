from __future__ import annotations

import hashlib
import time
from typing import Any

from .harness_credit import assign_cluster_credits, update_weight_stat
from .harness_settlement import abnormal_return, actual_return, normalized_outcome
from .harness_snapshot_builder import HarnessSnapshotBuilder
from .social_event_extraction import AnchorTerm, SocialEventExtraction, SocialTokenCandidate

HORIZON_MS = {
    "6h": 6 * 60 * 60 * 1000,
    "24h": 24 * 60 * 60 * 1000,
}
BASELINE_VERSION = "benchmark-zero-v1"


def materialize_market_ready_seeds(
    *,
    harness,
    evidence,
    assets,
    limit: int = 100,
) -> dict[str, int]:
    rows = harness.conn.execute(
        """
        SELECT se.*
        FROM social_event_extractions se
        JOIN attention_seeds seed ON seed.extraction_id = se.extraction_id
        WHERE seed.seed_status = 'market_unavailable'
          AND NOT EXISTS (
            SELECT 1
            FROM harness_snapshots hs
            WHERE hs.source_event_id = se.event_id
          )
        ORDER BY se.received_at_ms ASC
        LIMIT %s
        """,
        (max(0, int(limit)),),
    ).fetchall()
    counts = {"seeds_scanned": len(rows), "snapshots_written": 0, "still_blocked": 0, "errors": 0}
    builder = HarnessSnapshotBuilder(harness, assets=assets)
    for row in rows:
        try:
            social_event = harness._decode_social_event(dict(row))
            event = evidence.events_by_ids([str(social_event["event_id"])]).get(str(social_event["event_id"]))
            if event is None:
                counts["errors"] += 1
                continue
            before = _snapshot_count_for_event(harness, str(social_event["event_id"]))
            materialized = builder.materialize(
                event=event,
                extraction=_social_event_extraction_from_row(social_event),
                run_id=social_event.get("run_id"),
                model_version=str(social_event.get("model_version") or "unknown"),
            )
            after = _snapshot_count_for_event(harness, str(social_event["event_id"]))
            written = max(0, after - before)
            counts["snapshots_written"] += written
            if written == 0 and not materialized.get("snapshots"):
                counts["still_blocked"] += 1
        except Exception:
            counts["errors"] += 1
    return counts


def settle_harness_snapshots(
    *,
    harness,
    assets,
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
        WHERE horizon = %s
          AND outcome_status = 'pending'
          AND decision_time_ms + %s <= %s
        ORDER BY decision_time_ms ASC
        LIMIT %s
        """,
        (horizon, horizon_ms, now, max(0, int(limit))),
    ).fetchall()
    counts = {
        "snapshots_scanned": len(rows),
        "outcomes_written": 0,
        "skipped_missing_market": 0,
        "skipped_insufficient_market_data": 0,
        "errors": 0,
    }
    for row in rows:
        try:
            snapshot = harness.snapshot_by_id(str(row["snapshot_id"]))
            if snapshot is None:
                counts["errors"] += 1
                continue
            asset_id = str(snapshot["asset"])
            decision_time_ms = int(snapshot["decision_time_ms"])
            entry = assets.market_snapshot_at_or_before(asset_id, decision_time_ms)
            exit_ = assets.market_snapshot_at_or_before(asset_id, decision_time_ms + horizon_ms)
            entry_price = _float_or_none(entry.get("price_usd")) if entry else None
            exit_price = _float_or_none(exit_.get("price_usd")) if exit_ else None
            gap_status = _market_gap_status(
                asset_id=asset_id,
                entry=entry,
                exit_=exit_,
                entry_price=entry_price,
                exit_price=exit_price,
            )
            if gap_status is not None:
                harness.mark_snapshot_outcome_status(
                    snapshot_id=str(snapshot["snapshot_id"]),
                    outcome_status=gap_status,
                )
                if gap_status == "missing_market":
                    counts["skipped_missing_market"] += 1
                else:
                    counts["skipped_insufficient_market_data"] += 1
                continue
            actual = actual_return(entry_price=entry_price, exit_price=exit_price)
            expected = 0.0
            abnormal = abnormal_return(actual, expected)
            realized_vol = max(abs(actual), 0.03)
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


def _market_gap_status(
    *,
    asset_id: str | None,
    entry: dict[str, Any] | None,
    exit_: dict[str, Any] | None,
    entry_price: float | None,
    exit_price: float | None,
) -> str | None:
    if asset_id is None or entry is None or entry_price is None:
        return "missing_market"
    if exit_ is None or exit_price is None:
        return "insufficient_market_data"
    if int(exit_["observed_at_ms"]) <= int(entry["observed_at_ms"]):
        return "insufficient_market_data"
    return None


def attribute_harness_credits(*, harness, horizon: str, limit: int = 100) -> dict[str, int]:
    rows = harness.conn.execute(
        """
        SELECT *
        FROM harness_snapshots
        WHERE horizon = %s
          AND outcome_status = 'settled'
          AND credit_status != 'assigned'
        ORDER BY decision_time_ms ASC
        LIMIT %s
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
                    "UPDATE harness_snapshots SET credit_status = 'assigned' WHERE snapshot_id = %s",
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


def _social_event_extraction_from_row(row: dict[str, Any]) -> SocialEventExtraction:
    return SocialEventExtraction(
        is_signal_event=bool(row["is_signal_event"]),
        event_type=str(row["event_type"]),
        source_action=str(row["source_action"]),
        subject=str(row["subject"]),
        direction_hint=str(row["direction_hint"]),
        attention_mechanism=str(row["attention_mechanism"]),
        impact_hint=float(row["impact_hint"]),
        semantic_novelty_hint=float(row["semantic_novelty_hint"]),
        confidence=float(row["confidence"]),
        anchor_terms=[
            AnchorTerm(term=str(item["term"]), role=str(item["role"]), evidence=str(item["evidence"]))
            for item in row.get("anchor_terms", [])
            if isinstance(item, dict)
        ],
        token_candidates=[
            SocialTokenCandidate(
                symbol=item.get("symbol"),
                project_name=item.get("project_name"),
                chain=item.get("chain"),
                address=item.get("address"),
                evidence=str(item["evidence"]),
                confidence=float(item["confidence"]),
            )
            for item in row.get("token_candidates", [])
            if isinstance(item, dict)
        ],
        semantic_risks=[str(risk) for risk in row.get("semantic_risks", [])],
        summary_zh=str(row.get("summary_zh") or ""),
        raw_response=row.get("raw_response") if isinstance(row.get("raw_response"), dict) else {},
    )


def _snapshot_count_for_event(harness, event_id: str) -> int:
    row = harness.conn.execute(
        "SELECT COUNT(*) AS count FROM harness_snapshots WHERE source_event_id = %s",
        (event_id,),
    ).fetchone()
    return int(row["count"] or 0)


def _credit_groups(harness, *, limit: int) -> list[dict[str, Any]]:
    rows = harness.conn.execute(
        """
        SELECT credit_id, asset, event_type, source, horizon, credit
        FROM harness_credits
        ORDER BY created_at_ms ASC
        LIMIT %s
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


def _outcome_exists(harness, snapshot_id: str) -> bool:
    row = harness.conn.execute("SELECT 1 FROM harness_outcomes WHERE snapshot_id = %s", (snapshot_id,)).fetchone()
    return row is not None


def _credit_exists(harness, credit_id: str) -> bool:
    row = harness.conn.execute("SELECT 1 FROM harness_credits WHERE credit_id = %s", (credit_id,)).fetchone()
    return row is not None


def _outcome_for_snapshot(harness, snapshot_id: str) -> dict[str, Any] | None:
    row = harness.conn.execute("SELECT * FROM harness_outcomes WHERE snapshot_id = %s", (snapshot_id,)).fetchone()
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
