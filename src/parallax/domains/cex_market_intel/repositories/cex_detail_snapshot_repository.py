from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb


class CexDetailSnapshotRepository:
    def __init__(self, conn: Any):
        self.conn = conn

    def upsert_many(self, snapshots: list[dict[str, Any]]) -> int:
        written = 0
        for snapshot in snapshots:
            self.upsert_snapshot(snapshot, commit=False)
            written += 1
        if written:
            self.conn.commit()
        return written

    def upsert_snapshot(self, snapshot: dict[str, Any], *, commit: bool = True) -> None:
        self.conn.execute(
            """
            INSERT INTO cex_detail_snapshots(
              snapshot_id, target_type, target_id, exchange, native_market_id, base_symbol, quote_symbol,
              status, baseline_status, coinglass_status, price_usd, mark_price, funding_rate,
              volume_24h_usd, open_interest_usd, oi_change_pct_1h, oi_change_pct_4h, oi_change_pct_24h,
              cvd_delta_1h, cvd_delta_4h, cvd_delta_24h, long_short_ratio, top_trader_position_ratio,
              level_bands_json, degraded_reasons_json, source_refs_json, observed_at_ms, computed_at_ms
            )
            VALUES (
              %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
              %s, %s, %s, %s, %s
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
              computed_at_ms = excluded.computed_at_ms
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
            ),
        )
        if commit:
            self.conn.commit()

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
