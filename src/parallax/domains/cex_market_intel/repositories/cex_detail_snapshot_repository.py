from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from psycopg.types.json import Jsonb

_HASH_METADATA_FIELDS = {
    "computed_at_ms",
    "updated_at_ms",
    "projected_at_ms",
    "created_at_ms",
    "run_id",
    "worker_run_id",
    "attempt_id",
    "attempt_count",
    "generation_id",
}


class CexDetailSnapshotRepository:
    def __init__(self, conn: Any):
        self.conn = conn

    def upsert_many(self, snapshots: list[dict[str, Any]]) -> int:
        written = 0
        for snapshot in snapshots:
            written += self.upsert_snapshot(snapshot, commit=False)
        if written:
            self.conn.commit()
        return written

    def upsert_snapshot(self, snapshot: dict[str, Any], *, commit: bool = True) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO cex_detail_snapshots(
              snapshot_id, target_type, target_id, exchange, native_market_id, base_symbol, quote_symbol,
              status, baseline_status, coinglass_status, price_usd, mark_price, funding_rate,
              volume_24h_usd, open_interest_usd, oi_change_pct_1h, oi_change_pct_4h, oi_change_pct_24h,
              cvd_delta_1h, cvd_delta_4h, cvd_delta_24h, long_short_ratio, top_trader_position_ratio,
              level_bands_json, degraded_reasons_json, source_refs_json, observed_at_ms, computed_at_ms,
              payload_hash
            )
            VALUES (
              %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
              %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT(snapshot_id) DO UPDATE SET
              target_type = excluded.target_type,
              target_id = excluded.target_id,
              status = excluded.status,
              baseline_status = excluded.baseline_status,
              coinglass_status = excluded.coinglass_status,
              price_usd = excluded.price_usd,
              mark_price = excluded.mark_price,
              funding_rate = excluded.funding_rate,
              volume_24h_usd = excluded.volume_24h_usd,
              open_interest_usd = excluded.open_interest_usd,
              oi_change_pct_1h = excluded.oi_change_pct_1h,
              oi_change_pct_4h = excluded.oi_change_pct_4h,
              oi_change_pct_24h = excluded.oi_change_pct_24h,
              cvd_delta_1h = excluded.cvd_delta_1h,
              cvd_delta_4h = excluded.cvd_delta_4h,
              cvd_delta_24h = excluded.cvd_delta_24h,
              long_short_ratio = excluded.long_short_ratio,
              top_trader_position_ratio = excluded.top_trader_position_ratio,
              level_bands_json = excluded.level_bands_json,
              degraded_reasons_json = excluded.degraded_reasons_json,
              source_refs_json = excluded.source_refs_json,
              observed_at_ms = excluded.observed_at_ms,
              computed_at_ms = excluded.computed_at_ms,
              payload_hash = excluded.payload_hash
            WHERE cex_detail_snapshots.payload_hash IS DISTINCT FROM EXCLUDED.payload_hash
            """,
            (
                snapshot["snapshot_id"],
                snapshot.get("target_type") or "CexToken",
                snapshot["target_id"],
                snapshot.get("exchange") or "binance",
                snapshot["native_market_id"],
                snapshot.get("base_symbol") or "",
                snapshot.get("quote_symbol") or "USDT",
                snapshot.get("status") or "partial",
                snapshot.get("baseline_status") or "missing",
                snapshot.get("coinglass_status") or "unavailable",
                snapshot.get("price_usd"),
                snapshot.get("mark_price"),
                snapshot.get("funding_rate"),
                snapshot.get("volume_24h_usd"),
                snapshot.get("open_interest_usd"),
                snapshot.get("oi_change_pct_1h"),
                snapshot.get("oi_change_pct_4h"),
                snapshot.get("oi_change_pct_24h"),
                snapshot.get("cvd_delta_1h"),
                snapshot.get("cvd_delta_4h"),
                snapshot.get("cvd_delta_24h"),
                snapshot.get("long_short_ratio"),
                snapshot.get("top_trader_position_ratio"),
                Jsonb(list(snapshot.get("level_bands") or [])),
                Jsonb(list(snapshot.get("degraded_reasons") or [])),
                Jsonb(list(snapshot.get("source_refs") or [])),
                snapshot.get("observed_at_ms"),
                int(snapshot["computed_at_ms"]),
                _detail_payload_hash(snapshot),
            ),
        )
        written = _rowcount(cursor)
        if commit and written:
            self.conn.commit()
        return written

    def latest_snapshot(self, *, target_type: str, target_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT *
            FROM cex_detail_snapshots
            WHERE target_type = %s
              AND target_id = %s
            ORDER BY computed_at_ms DESC
            LIMIT 1
            """,
            (target_type, target_id),
        ).fetchone()
        return _public_snapshot(row)

    def latest_snapshot_by_market(self, *, exchange: str, native_market_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT *
            FROM cex_detail_snapshots
            WHERE exchange = %s
              AND native_market_id = %s
            ORDER BY computed_at_ms DESC
            LIMIT 1
            """,
            (exchange.lower(), native_market_id.upper()),
        ).fetchone()
        return _public_snapshot(row)


def _public_snapshot(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    payload = dict(row)
    payload["level_bands"] = payload.pop("level_bands_json", None) or []
    payload["degraded_reasons"] = payload.pop("degraded_reasons_json", None) or []
    payload["source_refs"] = payload.pop("source_refs_json", None) or []
    return payload


def _detail_payload_hash(snapshot: Mapping[str, Any]) -> str:
    payload = {
        "snapshot_id": snapshot.get("snapshot_id"),
        "target_type": snapshot.get("target_type") or "CexToken",
        "target_id": snapshot.get("target_id"),
        "exchange": snapshot.get("exchange") or "binance",
        "native_market_id": snapshot.get("native_market_id"),
        "base_symbol": snapshot.get("base_symbol") or "",
        "quote_symbol": snapshot.get("quote_symbol") or "USDT",
        "status": snapshot.get("status") or "partial",
        "baseline_status": snapshot.get("baseline_status") or "missing",
        "coinglass_status": snapshot.get("coinglass_status") or "unavailable",
        "price_usd": snapshot.get("price_usd"),
        "mark_price": snapshot.get("mark_price"),
        "funding_rate": snapshot.get("funding_rate"),
        "volume_24h_usd": snapshot.get("volume_24h_usd"),
        "open_interest_usd": snapshot.get("open_interest_usd"),
        "oi_change_pct_1h": snapshot.get("oi_change_pct_1h"),
        "oi_change_pct_4h": snapshot.get("oi_change_pct_4h"),
        "oi_change_pct_24h": snapshot.get("oi_change_pct_24h"),
        "cvd_delta_1h": snapshot.get("cvd_delta_1h"),
        "cvd_delta_4h": snapshot.get("cvd_delta_4h"),
        "cvd_delta_24h": snapshot.get("cvd_delta_24h"),
        "long_short_ratio": snapshot.get("long_short_ratio"),
        "top_trader_position_ratio": snapshot.get("top_trader_position_ratio"),
        "level_bands": _list_payload(snapshot.get("level_bands") or snapshot.get("level_bands_json")),
        "degraded_reasons": _list_payload(
            snapshot.get("degraded_reasons") or snapshot.get("degraded_reasons_json")
        ),
        "source_refs": _source_refs_for_hash(snapshot),
        "observed_at_ms": snapshot.get("observed_at_ms"),
    }
    return _stable_payload_hash(payload)


def _source_refs_for_hash(snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    refs = _list_payload(snapshot.get("source_refs") or snapshot.get("source_refs_json"))
    computed_at_ms = _int_or_none(snapshot.get("computed_at_ms"))
    provider_observed_at_ms = _int_or_none(snapshot.get("observed_at_ms"))
    source_refs: list[dict[str, Any]] = []
    for ref in refs:
        if not isinstance(ref, Mapping):
            continue
        ref_payload: dict[str, Any] = {}
        for key, value in ref.items():
            key_text = str(key)
            if key_text in _HASH_METADATA_FIELDS:
                continue
            if key_text == "observed_at_ms":
                ref_observed_at_ms = _int_or_none(value)
                if provider_observed_at_ms is None and ref_observed_at_ms == computed_at_ms:
                    continue
            ref_payload[key_text] = value
        source_refs.append(ref_payload)
    return source_refs


def _stable_payload_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(_json_ready(payload), sort_keys=True, separators=(",", ":"), allow_nan=False)
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(inner) for key, inner in value.items()}
    if isinstance(value, tuple | list):
        return [_json_ready(inner) for inner in value]
    if isinstance(value, set | frozenset):
        return sorted(_json_ready(inner) for inner in value)
    if isinstance(value, Decimal):
        return str(value.normalize())
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _list_payload(value: Any) -> list[Any]:
    if isinstance(value, list | tuple):
        return list(value)
    return []


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _rowcount(cursor: Any) -> int:
    rowcount = int(getattr(cursor, "rowcount", 0) or 0)
    return max(rowcount, 0)
