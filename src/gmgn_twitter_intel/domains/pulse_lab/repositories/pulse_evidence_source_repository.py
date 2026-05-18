from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from gmgn_twitter_intel.domains.pulse_lab.repositories._pulse_repository_shared import (
    _now_ms,
    _optional_row,
    _row,
)


class PulseEvidenceSourceRepository:
    def __init__(self, conn: Any):
        self.conn = conn

    def list_source_events(self, event_ids: Sequence[str]) -> list[dict[str, Any]]:
        ids = _stable_ids(event_ids)
        if not ids:
            return []
        rows = self.conn.execute(
            """
            SELECT *
            FROM events
            WHERE event_id = ANY(%s)
            ORDER BY timestamp_ms DESC, event_id ASC
            """,
            (ids,),
        ).fetchall()
        return [_row(row) for row in rows]

    def list_enriched_events(self, event_ids: Sequence[str]) -> list[dict[str, Any]]:
        ids = _stable_ids(event_ids)
        if not ids:
            return []
        rows = self.conn.execute(
            """
            SELECT enriched_events.*
            FROM enriched_events
            WHERE event_id = ANY(%s)
            ORDER BY t_event_ms DESC, event_id ASC, intent_id ASC
            """,
            (ids,),
        ).fetchall()
        return [_row(row) for row in rows]

    def get_asset_identity(self, target_type: str, target_id: str) -> dict[str, Any] | None:
        if str(target_type).strip() not in {"asset", "chain_token", "cex_symbol"}:
            return None
        return _optional_row(
            self.conn.execute(
                """
                SELECT *
                FROM asset_identity_current
                WHERE asset_id = %s
                """,
                (target_id,),
            ).fetchone()
        )

    def get_latest_profile(self, target_type: str, target_id: str) -> dict[str, Any] | None:
        token_profile = _optional_row(
            self.conn.execute(
                """
                SELECT *
                FROM token_profile_current
                WHERE target_type = %s
                  AND target_id = %s
                """,
                (target_type, target_id),
            ).fetchone()
        )
        if token_profile is not None:
            return token_profile
        if str(target_type).strip() != "cex_symbol":
            return None
        return _optional_row(
            self.conn.execute(
                """
                SELECT *
                FROM cex_token_profiles
                WHERE cex_token_id = %s
                ORDER BY updated_at_ms DESC, provider ASC
                LIMIT 1
                """,
                (target_id,),
            ).fetchone()
        )

    def get_latest_market_tick(self, target_type: str, target_id: str, max_age_ms: int) -> dict[str, Any] | None:
        min_observed_at_ms = max(0, _now_ms() - max(0, int(max_age_ms)))
        return _optional_row(
            self.conn.execute(
                """
                SELECT *
                FROM market_ticks
                WHERE target_type = %s
                  AND target_id = %s
                  AND observed_at_ms >= %s
                ORDER BY observed_at_ms DESC, tick_id DESC
                LIMIT 1
                """,
                (target_type, target_id, min_observed_at_ms),
            ).fetchone()
        )

    def list_market_facts(self, context: Any, *, max_age_ms: int = 3_600_000) -> list[dict[str, Any]]:
        target_type = _context_value(context, "target_type")
        target_id = _context_value(context, "target_id")
        if not target_type or not target_id:
            return []
        rows: list[dict[str, Any]] = []
        tick = self.get_latest_market_tick(target_type, target_id, max_age_ms)
        if tick is not None:
            rows.append(_market_fact_from_tick(tick))
        return rows

    def list_identity_facts(self, context: Any) -> list[dict[str, Any]]:
        target_type = _context_value(context, "target_type")
        target_id = _context_value(context, "target_id")
        if not target_type or not target_id:
            return []
        rows: list[dict[str, Any]] = []
        identity = self.get_asset_identity(target_type, target_id)
        if identity is not None:
            rows.append(
                {
                    **identity,
                    "source_id": f"identity:{target_id}",
                    "source_table": "asset_identity_current",
                    "summary_zh": _identity_summary(identity, fallback=f"目标身份 {target_id}"),
                    "quality": "high",
                }
            )
        profile = self.get_latest_profile(target_type, target_id)
        if profile is not None:
            rows.append(
                {
                    **profile,
                    "source_id": f"profile:{target_id}",
                    "source_table": _profile_source_table(target_type),
                    "summary_zh": _identity_summary(profile, fallback=f"目标 Profile {target_id}"),
                    "quality": "medium",
                }
            )
        return rows


def _stable_ids(values: Sequence[str]) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value).strip()})


def _context_value(context: Any, key: str) -> str:
    value = context.get(key) if isinstance(context, dict) else getattr(context, key, None)
    return str(value or "").strip()


def _market_fact_from_tick(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "source_table": "market_ticks",
        "route": _route_from_target(row.get("target_type")),
        "target_market_type": _target_market_type(row.get("target_type")),
        "instrument_ref": row.get("pricefeed_id") or row.get("target_id"),
        "source_provider": row.get("source_provider"),
        "observed_at_ms": row.get("observed_at_ms"),
    }


def _route_from_target(value: Any) -> str:
    text = str(value or "").lower()
    if "cex" in text or text in {"spot", "perp", "perpetual"}:
        return "cex"
    if "chain" in text or "dex" in text:
        return "meme"
    return "unknown"


def _target_market_type(value: Any) -> str:
    text = str(value or "").strip()
    if text:
        return text
    return "unknown"


def _identity_summary(row: dict[str, Any], *, fallback: str) -> str:
    for key in ("summary_zh", "name", "symbol", "description"):
        value = row.get(key)
        if value:
            return str(value)
    return fallback


def _profile_source_table(target_type: str) -> str:
    return "cex_token_profiles" if target_type == "cex_symbol" else "token_profile_current"
