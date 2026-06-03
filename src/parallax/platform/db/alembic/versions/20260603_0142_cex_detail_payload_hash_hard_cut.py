"""Add payload hash gate to CEX detail snapshots."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "20260603_0142"
down_revision = "20260601_0141"
branch_labels = None
depends_on = None

_BACKFILL_BATCH_SIZE = 1_000
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


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30min'")
    op.execute("ALTER TABLE cex_detail_snapshots ADD COLUMN IF NOT EXISTS payload_hash TEXT")
    _backfill_cex_detail_payload_hashes()
    op.execute("ALTER TABLE cex_detail_snapshots ALTER COLUMN payload_hash SET NOT NULL")
    op.execute("ANALYZE cex_detail_snapshots")


def downgrade() -> None:
    op.execute("ALTER TABLE cex_detail_snapshots DROP COLUMN IF EXISTS payload_hash")


def cex_detail_snapshot_payload_hash(snapshot: Mapping[str, Any]) -> str:
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
        "observed_at_ms": _provider_observed_at_ms(snapshot),
    }
    return _stable_payload_hash(payload)


def _backfill_cex_detail_payload_hashes() -> None:
    bind = op.get_bind()
    select_rows = sa.text(
        """
        SELECT
          ctid::text AS row_ctid,
          snapshot_id,
          target_type,
          target_id,
          exchange,
          native_market_id,
          base_symbol,
          quote_symbol,
          status,
          baseline_status,
          coinglass_status,
          price_usd,
          mark_price,
          funding_rate,
          volume_24h_usd,
          open_interest_usd,
          oi_change_pct_1h,
          oi_change_pct_4h,
          oi_change_pct_24h,
          cvd_delta_1h,
          cvd_delta_4h,
          cvd_delta_24h,
          long_short_ratio,
          top_trader_position_ratio,
          level_bands_json,
          degraded_reasons_json,
          source_refs_json,
          observed_at_ms,
          computed_at_ms
        FROM cex_detail_snapshots
        WHERE payload_hash IS NULL OR payload_hash = ''
        ORDER BY snapshot_id
        LIMIT :limit
        """
    )
    update_hash = sa.text(
        """
        UPDATE cex_detail_snapshots
        SET payload_hash = :payload_hash
        WHERE ctid = CAST(:row_ctid AS tid)
        """
    )
    while True:
        rows = bind.execute(select_rows, {"limit": _BACKFILL_BATCH_SIZE}).mappings().all()
        if not rows:
            break
        for row in rows:
            bind.execute(
                update_hash,
                {
                    "row_ctid": row["row_ctid"],
                    "payload_hash": cex_detail_snapshot_payload_hash(row),
                },
            )


def _source_refs_for_hash(snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    refs = _list_payload(snapshot.get("source_refs") or snapshot.get("source_refs_json"))
    provider_observed_at_ms = _provider_observed_at_ms(snapshot)
    source_refs: list[dict[str, Any]] = []
    for ref in refs:
        if not isinstance(ref, Mapping):
            continue
        ref_payload: dict[str, Any] = {}
        for key, value in ref.items():
            key_text = str(key)
            if key_text in _HASH_METADATA_FIELDS:
                continue
            if key_text == "observed_at_ms" and provider_observed_at_ms is None:
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
    if isinstance(value, bool):
        return value
    if isinstance(value, Decimal):
        return _canonical_number(value)
    if isinstance(value, int | float):
        return _canonical_number(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _provider_observed_at_ms(snapshot: Mapping[str, Any]) -> int | None:
    observed_at_ms = _int_or_none(snapshot.get("observed_at_ms"))
    if observed_at_ms is None:
        return None
    source = str(snapshot.get("observed_at_source") or "").strip().lower()
    if source == "provider":
        return observed_at_ms
    if source == "computed":
        return None
    computed_at_ms = _int_or_none(snapshot.get("computed_at_ms"))
    if computed_at_ms is not None and observed_at_ms == computed_at_ms:
        return None
    return observed_at_ms


def _canonical_number(value: int | float | Decimal) -> str:
    if isinstance(value, float):
        if not math.isfinite(value):
            return str(value)
        number = Decimal(str(value))
    else:
        number = Decimal(value)
    text = format(number.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text == "-0":
        return "0"
    return text or "0"


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
