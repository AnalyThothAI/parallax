from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

HOT_PATH_COUNT_QUERIES: dict[str, str] = {
    "raw_frames": "SELECT count(*) AS value FROM raw_frames WHERE source = 'gmgn'",
    "events": "SELECT count(*) AS value FROM events WHERE event_id = %(event_id)s",
    "token_intents": "SELECT count(*) AS value FROM token_intents WHERE event_id = %(event_id)s",
    "token_intent_resolutions": (
        "SELECT count(*) AS value FROM token_intent_resolutions WHERE event_id = %(event_id)s"
    ),
    "enriched_events": "SELECT count(*) AS value FROM enriched_events WHERE event_id = %(event_id)s",
    "ready_enriched_events": (
        "SELECT count(*) AS value FROM enriched_events WHERE event_id = %(event_id)s AND tick_id IS NOT NULL"
    ),
    "event_anchor_jobs": "SELECT count(*) AS value FROM event_anchor_backfill_jobs WHERE event_id = %(event_id)s",
    "market_ticks": "SELECT count(*) AS value FROM market_ticks",
    "token_radar_rows": "SELECT count(*) AS value FROM token_radar_rows WHERE \"window\" = '1h' AND scope = 'all'",
    "pulse_agent_jobs": "SELECT count(*) AS value FROM pulse_agent_jobs",
    "pulse_agent_runs": "SELECT count(*) AS value FROM pulse_agent_runs",
    "pulse_candidates": "SELECT count(*) AS value FROM pulse_candidates",
    "notifications": "SELECT count(*) AS value FROM notifications",
    "notification_deliveries": "SELECT count(*) AS value FROM notification_deliveries",
    "delivered_notifications": "SELECT count(*) AS value FROM notification_deliveries WHERE status = 'delivered'",
}


def scalar(conn: Any, sql: str, params: dict[str, Any] | tuple[Any, ...] | None = None) -> Any:
    row = conn.execute(sql, params or {}).fetchone()
    if row is None:
        return None
    return row["value"] if isinstance(row, dict) else row[0]


def hot_path_counts(conn: Any, *, event_id: str) -> dict[str, int]:
    params = {"event_id": event_id}
    return {name: int(scalar(conn, sql, params) or 0) for name, sql in HOT_PATH_COUNT_QUERIES.items()}


def first_row(conn: Any, sql: str, params: dict[str, Any] | tuple[Any, ...] | None = None) -> dict[str, Any]:
    row = conn.execute(sql, params or {}).fetchone()
    assert row is not None
    return dict(row)


def assert_count_at_least(counts: dict[str, int], name: str, minimum: int = 1) -> None:
    actual = counts.get(name, 0)
    assert actual >= minimum, f"expected {name} >= {minimum}, got {actual}; counts={counts}"


def promote_latest_token_radar_row_for_pulse(conn: Any, *, target_id: str) -> None:
    rows = conn.execute(
        """
        SELECT row_id, factor_snapshot_json
        FROM token_radar_rows
        WHERE "window" = '1h'
          AND scope = 'all'
        ORDER BY (target_id = %(target_id)s) DESC, computed_at_ms DESC, rank ASC
        """,
        {"target_id": target_id},
    ).fetchall()
    assert rows
    for row in rows:
        snapshot = dict(row["factor_snapshot_json"])
        _make_snapshot_pulse_ready(snapshot)
        conn.execute(
            """
            UPDATE token_radar_rows
            SET factor_snapshot_json = %(factor_snapshot_json)s,
                decision = 'high_alert',
                data_health_json = %(data_health_json)s
            WHERE row_id = %(row_id)s
            """,
            {
                "row_id": row["row_id"],
                "factor_snapshot_json": Jsonb(snapshot),
                "data_health_json": Jsonb(snapshot["data_health"]),
            },
        )
    conn.commit()


def _make_snapshot_pulse_ready(snapshot: dict[str, Any]) -> None:
    subject = _dict_block(snapshot, "subject")
    subject["target_market_type"] = "dex"

    market = _dict_block(snapshot, "market")
    decision_latest = _dict_block(market, "decision_latest")
    decision_latest.update(
        {
            "price_usd": decision_latest.get("price_usd") or 0.129,
            "market_cap_usd": decision_latest.get("market_cap_usd") or 1_234_567.0,
            "liquidity_usd": decision_latest.get("liquidity_usd") or 456_789.0,
            "volume_24h_usd": decision_latest.get("volume_24h_usd") or 98_765.0,
            "holders": decision_latest.get("holders") or 4321,
        }
    )
    readiness = _dict_block(market, "readiness")
    readiness.update(
        {
            "anchor_status": "ready",
            "latest_status": "fresh",
            "dex_floor_status": "pass",
            "missing_fields": [],
            "stale_fields": [],
        }
    )

    normalization = _dict_block(snapshot, "normalization")
    normalization.update(
        {
            "status": "ranked",
            "cohort_status": "ready",
            "alpha_rank": 0.95,
        }
    )
    cohort = _dict_block(normalization, "cohort")
    cohort.update({"in_cohort": True, "size": 10})

    gates = _dict_block(snapshot, "gates")
    gates.update(
        {
            "eligible_for_high_alert": True,
            "blocked_reasons": [],
            "risk_reasons": [],
            "max_decision": "high_alert",
        }
    )

    composite = _dict_block(snapshot, "composite")
    composite.update({"rank_score": 95, "recommended_decision": "high_alert"})


def _dict_block(parent: dict[str, Any], key: str) -> dict[str, Any]:
    value = parent.get(key)
    if isinstance(value, dict):
        return value
    replacement: dict[str, Any] = {}
    parent[key] = replacement
    return replacement
