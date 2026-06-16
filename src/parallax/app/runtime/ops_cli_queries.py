from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def market_tick_current_rebuild_estimate(conn: Any) -> dict[str, Any]:
    scanned_row = conn.execute("SELECT COUNT(*) AS scanned FROM market_ticks").fetchall()
    scanned = int(scanned_row[0]["scanned"]) if scanned_row else 0
    rows = conn.execute(
        """
        SELECT target_type, COUNT(*) AS estimated_rows
        FROM (
          SELECT DISTINCT target_type, target_id
          FROM market_ticks
        ) latest
        GROUP BY target_type
        ORDER BY target_type ASC
        """
    ).fetchall()
    counts_by_target_type = {str(row["target_type"]): int(row["estimated_rows"]) for row in rows}
    return {
        "scanned": scanned,
        "estimated_rows": sum(counts_by_target_type.values()),
        "counts_by_target_type": counts_by_target_type,
    }


def token_radar_source_count(
    conn: Any,
    *,
    since_ms: int,
    scope: str,
    resolver_policy_version: str,
) -> int:
    watched_clause = "AND events.is_watched = true" if scope == "matched" else ""
    row = conn.execute(
        f"""
        SELECT COUNT(*) AS value
        FROM token_intents
        JOIN token_intent_resolutions
          ON token_intent_resolutions.intent_id = token_intents.intent_id
         AND token_intent_resolutions.is_current = true
         AND token_intent_resolutions.resolver_policy_version = %s
         AND token_intent_resolutions.target_type IN ('Asset', 'CexToken')
         AND token_intent_resolutions.target_id IS NOT NULL
        JOIN events ON events.event_id = token_intents.event_id
        WHERE events.received_at_ms >= %s {watched_clause}
        """,
        (str(resolver_policy_version), int(since_ms)),
    ).fetchone()
    return int(row["value"] or 0) if row else 0


def token_radar_max_resolution_ms(conn: Any) -> int | None:
    row = conn.execute(
        """
        SELECT MAX(decision_time_ms) AS value
        FROM token_intent_resolutions
        WHERE is_current = true
          AND target_type IN ('Asset', 'CexToken')
          AND target_id IS NOT NULL
        """
    ).fetchone()
    value = row["value"] if row else None
    return int(value) if value is not None else None


def token_radar_max_market_tick_observed_at_ms(conn: Any) -> int | None:
    row = conn.execute("SELECT MAX(tick_observed_at_ms) AS value FROM market_tick_current").fetchone()
    value = row["value"] if row else None
    return int(value) if value is not None else None


def token_profile_image_repair_targets(conn: Any, *, limit: int, now_ms: int) -> list[dict[str, Any]]:
    del now_ms
    rows = conn.execute(
        """
        SELECT target_type, target_id, updated_at_ms AS source_watermark_ms
        FROM token_profile_current
        WHERE status = 'ready'
          AND (
            quality_flags_json ? 'logo_mirror_pending'
            OR quality_flags_json ? 'source_not_admitted'
            OR quality_flags_json ? 'logo_mirror_unsupported'
            OR quality_flags_json ? 'logo_mirror_failed'
          )
        ORDER BY updated_at_ms DESC, target_type ASC, target_id ASC
        LIMIT %s
        """,
        (int(limit),),
    ).fetchall()
    return [
        {
            "target_type": str(row["target_type"]),
            "target_id": str(row["target_id"]),
            "source_watermark_ms": _required_source_watermark_ms(row),
            "priority": 25,
        }
        for row in rows
    ]


def _required_source_watermark_ms(row: Mapping[str, Any]) -> int:
    try:
        value = row["source_watermark_ms"]
    except KeyError as exc:
        raise ValueError("token_profile_image_repair_source_watermark_required") from exc
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("token_profile_image_repair_source_watermark_required")
    if value <= 0:
        raise ValueError("token_profile_image_repair_source_watermark_required")
    return int(value)


__all__ = [
    "market_tick_current_rebuild_estimate",
    "token_profile_image_repair_targets",
    "token_radar_max_market_tick_observed_at_ms",
    "token_radar_max_resolution_ms",
    "token_radar_source_count",
]
