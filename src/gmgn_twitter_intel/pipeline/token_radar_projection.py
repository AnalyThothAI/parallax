from __future__ import annotations

import hashlib
import time
from typing import Any

from ..storage.projection_repository import ProjectionRepository

WINDOW_MS = {
    "5m": 5 * 60 * 1000,
    "1h": 60 * 60 * 1000,
    "4h": 4 * 60 * 60 * 1000,
    "24h": 24 * 60 * 60 * 1000,
}
PROJECTION_VERSION = "token-radar-v3"


class TokenRadarProjection:
    def __init__(self, *, repos):
        self.repos = repos

    def rebuild(self, *, window: str, scope: str, now_ms: int | None = None, limit: int = 100) -> dict[str, Any]:
        computed_at_ms = int(now_ms or time.time() * 1000)
        since_ms = computed_at_ms - WINDOW_MS.get(window, WINDOW_MS["1h"])
        source_rows = self._source_rows(since_ms=since_ms, scope=scope)
        grouped = self._group_rows(source_rows)
        projected = [_project_group(group, now_ms=computed_at_ms) for group in grouped.values()]
        resolved = [row for row in projected if row["lane"] == "resolved"]
        attention = [row for row in projected if row["lane"] == "attention"]
        resolved.sort(key=_rank_key)
        attention.sort(key=_rank_key)
        rows = []
        for lane_rows in (resolved, attention):
            for rank, row in enumerate(lane_rows[:limit], start=1):
                rows.append({**row, "rank": rank})
        source_max_received_at_ms = max(
            (int(row.get("source_max_received_at_ms") or 0) for row in rows),
            default=0,
        )
        run = ProjectionRepository(self.repos.conn).start_run(
            projection_name="token-radar",
            projection_version=PROJECTION_VERSION,
            mode="rebuild",
            source_start_ms=since_ms,
            source_end_ms=computed_at_ms,
            commit=False,
        )
        self.repos.token_radar.replace_rows(
            projection_version=PROJECTION_VERSION,
            window=window,
            scope=scope,
            computed_at_ms=computed_at_ms,
            rows=rows,
            commit=False,
        )
        ProjectionRepository(self.repos.conn).advance_offset(
            projection_name="token-radar",
            projection_version=PROJECTION_VERSION,
            source_table="token_intent_resolutions",
            source_max_received_at_ms=source_max_received_at_ms,
            source_max_id=str(rows[0]["row_id"]) if rows else "",
            last_run_id=str(run["run_id"]),
            lag_ms=max(0, computed_at_ms - source_max_received_at_ms) if source_max_received_at_ms else 0,
            status="ready",
            commit=False,
        )
        ProjectionRepository(self.repos.conn).finish_run(
            run_id=str(run["run_id"]),
            status="ready",
            rows_read=len(source_rows),
            rows_written=len(rows),
            dirty_ranges_written=0,
            commit=True,
        )
        return {"rows_written": len(rows), "source_rows": len(source_rows), "computed_at_ms": computed_at_ms}

    def _source_rows(self, *, since_ms: int, scope: str) -> list[dict[str, Any]]:
        watched_clause = "AND events.is_watched = true" if scope == "matched" else ""
        rows = self.repos.conn.execute(
            f"""
            SELECT
              token_intents.*,
              token_intent_resolutions.resolution_id,
              token_intent_resolutions.asset_id AS resolved_asset_id,
              token_intent_resolutions.primary_venue_id,
              token_intent_resolutions.resolution_status,
              token_intent_resolutions.identity_status AS resolution_identity_status,
              token_intent_resolutions.confidence AS resolution_confidence,
              token_intent_resolutions.reasons_json,
              token_intent_resolutions.risks_json,
              token_intent_resolutions.decision_time_ms,
              events.author_handle,
              events.is_watched,
              events.received_at_ms,
              assets.asset_type,
              assets.canonical_symbol,
              assets.display_name AS asset_display_name,
              assets.identity_status AS asset_identity_status,
              asset_venues.venue_id,
              asset_venues.venue_type,
              asset_venues.exchange,
              asset_venues.chain,
              asset_venues.address,
              asset_venues.inst_id,
              asset_venues.base_symbol,
              asset_venues.quote_symbol,
              asset_venues.inst_type
            FROM token_intents
            JOIN token_intent_resolutions
              ON token_intent_resolutions.intent_id = token_intents.intent_id
             AND token_intent_resolutions.resolution_status <> 'superseded'
            JOIN events ON events.event_id = token_intents.event_id
            LEFT JOIN assets ON assets.asset_id = token_intent_resolutions.asset_id
            LEFT JOIN asset_venues ON asset_venues.venue_id = token_intent_resolutions.primary_venue_id
            WHERE events.received_at_ms >= %s {watched_clause}
            """,
            (since_ms,),
        ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _group_rows(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            key = str(row.get("resolved_asset_id") or row.get("intent_id"))
            grouped.setdefault(key, []).append(row)
        return grouped


def _project_group(rows: list[dict[str, Any]], *, now_ms: int) -> dict[str, Any]:
    latest = max(rows, key=lambda row: int(row.get("received_at_ms") or 0))
    event_ids = sorted({str(row["event_id"]) for row in rows})
    authors = {str(row.get("author_handle") or "") for row in rows if row.get("author_handle")}
    watched = sum(1 for row in rows if row.get("is_watched"))
    latest_seen_ms = max(int(row.get("received_at_ms") or 0) for row in rows)
    identity_status = str(latest.get("resolution_identity_status") or "unresolved")
    resolved = (
        identity_status == "resolved"
        and bool(latest.get("resolved_asset_id"))
        and bool(latest.get("primary_venue_id"))
    )
    lane = "resolved" if resolved else "attention"
    market = _market(latest, identity_status=identity_status)
    score = _score(mentions=len(event_ids), authors=len(authors), watched=watched, resolved=resolved, market=market)
    decision = _decision(score=score, resolved=resolved)
    return {
        "row_id": _stable_id("token-radar-row", str(latest.get("intent_id")), str(now_ms)),
        "source_max_received_at_ms": latest_seen_ms,
        "lane": lane,
        "rank": 0,
        "intent_id": latest["intent_id"],
        "event_id": latest["event_id"],
        "asset_id": latest.get("resolved_asset_id"),
        "primary_venue_id": latest.get("primary_venue_id"),
        "intent_json": {
            "intent_id": latest["intent_id"],
            "display_symbol": latest.get("display_symbol"),
            "display_name": latest.get("display_name"),
            "evidence": [],
        },
        "asset_json": {
            "asset_id": latest.get("resolved_asset_id"),
            "symbol": _display_symbol(latest),
            "asset_type": latest.get("asset_type"),
            "identity_status": identity_status,
        },
        "primary_venue_json": _venue(latest) if latest.get("primary_venue_id") else None,
        "attention_json": {
            "mentions_5m": len(event_ids),
            "mentions_1h": len(event_ids),
            "mentions_window": len(event_ids),
            "unique_authors": len(authors),
            "watched_mentions": watched,
            "latest_seen_ms": latest_seen_ms,
        },
        "resolution_json": {
            "status": identity_status if identity_status in {"resolved", "ambiguous"} else "unresolved",
            "resolution_status": latest.get("resolution_status"),
            "confidence": latest.get("resolution_confidence"),
            "reasons": latest.get("reasons_json") or [],
            "risks": latest.get("risks_json") or [],
        },
        "market_json": market,
        "score_json": score,
        "decision": decision,
        "data_health_json": {
            "identity": identity_status,
            "market": market["market_observation_status"],
            "coverage": "public_stream",
        },
        "source_event_ids_json": event_ids,
        "created_at_ms": now_ms,
    }


def _market(row: dict[str, Any], *, identity_status: str) -> dict[str, Any]:
    if identity_status != "resolved" or not row.get("primary_venue_id"):
        return {
            "market_status": "missing",
            "market_observation_status": "no_venue",
            "price_change_status": "no_venue",
            "provider": None,
            "price_usd": None,
            "market_cap_usd": None,
            "liquidity_usd": None,
            "volume_24h_usd": None,
            "open_interest_usd": None,
            "holders": None,
            "snapshot_age_ms": None,
            "snapshot_observed_at_ms": None,
            "price_change_since_social_pct": None,
            "price_change_before_social_pct": None,
        }
    return {
        "market_status": "missing",
        "market_observation_status": "pending_refresh",
        "price_change_status": "pending_refresh",
        "provider": None,
        "price_usd": None,
        "market_cap_usd": None,
        "liquidity_usd": None,
        "volume_24h_usd": None,
        "open_interest_usd": None,
        "holders": None,
        "snapshot_age_ms": None,
        "snapshot_observed_at_ms": None,
        "price_change_since_social_pct": None,
        "price_change_before_social_pct": None,
    }


def _score(*, mentions: int, authors: int, watched: int, resolved: bool, market: dict[str, Any]) -> dict[str, Any]:
    heat = min(100, 30 + mentions * 6 + authors * 8 + watched * 8)
    quality = min(100, 70 + watched * 8) if resolved else min(70, 35 + mentions * 8)
    propagation = min(100, 30 + authors * 14)
    tradeability = (
        80
        if resolved and market["market_observation_status"] in {"ready", "stale", "pending_refresh"}
        else 20
    )
    timing = 50 if resolved else 35
    opportunity = round(heat * 0.4 + quality * 0.25 + propagation * 0.2 + tradeability * 0.1 + timing * 0.05)
    return {
        "heat": _score_block(heat),
        "quality": _score_block(quality),
        "propagation": _score_block(propagation),
        "tradeability": _score_block(tradeability, hard_risks=[] if resolved else ["unresolved_token_identity"]),
        "timing": _score_block(timing),
        "opportunity": _score_block(opportunity, hard_risks=[] if resolved else ["unresolved_token_identity"]),
    }


def _score_block(score: int, *, hard_risks: list[str] | None = None) -> dict[str, Any]:
    return {
        "score": int(score),
        "score_version": "token_radar_v3",
        "reasons": [],
        "risks": hard_risks or [],
        "hard_risks": hard_risks or [],
        "contributions": [],
        "risk_caps": [],
    }


def _decision(*, score: dict[str, Any], resolved: bool) -> str:
    if not resolved:
        return "investigate"
    opportunity = int((score.get("opportunity") or {}).get("score") or 0)
    return "driver" if opportunity >= 75 else "watch" if opportunity >= 45 else "discard"


def _venue(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "venue_id": row.get("primary_venue_id"),
        "venue_type": row.get("venue_type"),
        "exchange": row.get("exchange"),
        "chain": row.get("chain"),
        "address": row.get("address"),
        "inst_id": row.get("inst_id"),
        "base_symbol": row.get("base_symbol"),
        "quote_symbol": row.get("quote_symbol"),
        "inst_type": row.get("inst_type"),
    }


def _display_symbol(row: dict[str, Any]) -> str | None:
    return row.get("display_symbol") or row.get("canonical_symbol") or row.get("base_symbol")


def _rank_key(row: dict[str, Any]) -> tuple[int, int]:
    attention = row["attention_json"]
    return (-int(attention["mentions_window"]), -int(attention["latest_seen_ms"]))


def _stable_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
