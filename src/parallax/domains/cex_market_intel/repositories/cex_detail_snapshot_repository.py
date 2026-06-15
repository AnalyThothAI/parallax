from __future__ import annotations

from collections.abc import Mapping
from contextlib import AbstractContextManager
from typing import Any, cast

from psycopg.types.json import Jsonb

from parallax.platform.current_read_model_payload_hash import stable_current_payload_hash

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
_SNAPSHOT_STATUS_VALUES = {
    "status": frozenset({"ready", "partial", "missing"}),
    "baseline_status": frozenset({"ready", "missing"}),
    "coinglass_status": frozenset({"ready", "partial", "unavailable"}),
}
_LEGACY_JSON_ALIAS_FIELDS = frozenset({"level_bands_json", "degraded_reasons_json", "source_refs_json"})
_OBSERVED_AT_SOURCE_VALUES = frozenset({"provider", "computed"})


class CexDetailSnapshotRepository:
    def __init__(self, conn: Any):
        self.conn = conn

    def upsert_many(self, snapshots: list[dict[str, Any]], *, commit: bool = True) -> int:
        if commit:
            with _transaction(self.conn):
                return self.upsert_many(snapshots, commit=False)

        written = 0
        for snapshot in snapshots:
            written += self.upsert_snapshot(snapshot, commit=False)
        return written

    def upsert_snapshot(self, snapshot: dict[str, Any], *, commit: bool = True) -> int:
        if commit:
            with _transaction(self.conn):
                return self.upsert_snapshot(snapshot, commit=False)

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
                _required_snapshot_text(snapshot, "target_type"),
                _required_snapshot_text(snapshot, "target_id"),
                _required_snapshot_text(snapshot, "exchange"),
                _required_snapshot_text(snapshot, "native_market_id"),
                _required_snapshot_text(snapshot, "base_symbol"),
                _required_snapshot_text(snapshot, "quote_symbol"),
                _required_snapshot_status(snapshot, "status"),
                _required_snapshot_status(snapshot, "baseline_status"),
                _required_snapshot_status(snapshot, "coinglass_status"),
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
                Jsonb(_required_snapshot_list(snapshot, "level_bands")),
                Jsonb(_required_snapshot_list(snapshot, "degraded_reasons")),
                Jsonb(_required_snapshot_list(snapshot, "source_refs")),
                snapshot.get("observed_at_ms"),
                int(snapshot["computed_at_ms"]),
                _detail_payload_hash(snapshot),
            ),
        )
        written = _rowcount(cursor)
        return written

    def latest_snapshot(self, *, target_type: str, target_id: str) -> dict[str, Any] | None:
        query_target_type = _required_query_text(target_type, "target_type")
        query_target_id = _required_query_text(target_id, "target_id")
        row = self.conn.execute(
            """
            SELECT *
            FROM cex_detail_snapshots
            WHERE target_type = %s
              AND target_id = %s
            ORDER BY computed_at_ms DESC
            LIMIT 1
            """,
            (query_target_type, query_target_id),
        ).fetchone()
        return _public_snapshot(row)

    def latest_snapshot_by_market(self, *, exchange: str, native_market_id: str) -> dict[str, Any] | None:
        query_exchange = _required_query_text(exchange, "exchange").lower()
        query_native_market_id = _required_query_text(native_market_id, "native_market_id").upper()
        row = self.conn.execute(
            """
            SELECT *
            FROM cex_detail_snapshots
            WHERE exchange = %s
              AND native_market_id = %s
            ORDER BY computed_at_ms DESC
            LIMIT 1
            """,
            (query_exchange, query_native_market_id),
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
    _reject_legacy_json_aliases(snapshot)
    payload = {
        "snapshot_id": _required_snapshot_text(snapshot, "snapshot_id"),
        "target_type": _required_snapshot_text(snapshot, "target_type"),
        "target_id": _required_snapshot_text(snapshot, "target_id"),
        "exchange": _required_snapshot_text(snapshot, "exchange"),
        "native_market_id": _required_snapshot_text(snapshot, "native_market_id"),
        "base_symbol": _required_snapshot_text(snapshot, "base_symbol"),
        "quote_symbol": _required_snapshot_text(snapshot, "quote_symbol"),
        "status": _required_snapshot_status(snapshot, "status"),
        "baseline_status": _required_snapshot_status(snapshot, "baseline_status"),
        "coinglass_status": _required_snapshot_status(snapshot, "coinglass_status"),
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
        "level_bands": _required_snapshot_list(snapshot, "level_bands"),
        "degraded_reasons": _required_snapshot_list(snapshot, "degraded_reasons"),
        "source_refs": _source_refs_for_hash(snapshot),
        "observed_at_ms": _provider_observed_at_ms(snapshot),
    }
    return stable_current_payload_hash(payload)


def _required_snapshot_text(snapshot: Mapping[str, Any], field: str) -> str:
    value = str(snapshot.get(field) or "").strip()
    if not value:
        raise ValueError(f"cex_detail_snapshot_identity_required:{field}")
    return value


def _required_snapshot_status(snapshot: Mapping[str, Any], field: str) -> str:
    value = str(snapshot.get(field) or "").strip().lower()
    if not value:
        raise ValueError(f"cex_detail_snapshot_status_required:{field}")
    allowed = _SNAPSHOT_STATUS_VALUES[field]
    if value not in allowed:
        raise ValueError(f"cex_detail_snapshot_status_invalid:{field}")
    return value


def _required_query_text(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"cex_detail_snapshot_query_identity_required:{field}")
    return text


def _required_snapshot_list(snapshot: Mapping[str, Any], field: str) -> list[Any]:
    if field not in snapshot or snapshot.get(field) is None:
        raise ValueError(f"cex_detail_snapshot_payload_required:{field}")
    value = snapshot.get(field)
    if not isinstance(value, list | tuple):
        raise ValueError(f"cex_detail_snapshot_payload_invalid:{field}")
    return list(value)


def _source_refs_for_hash(snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    refs = _required_snapshot_list(snapshot, "source_refs")
    provider_observed_at_ms = _provider_observed_at_ms(snapshot)
    source_refs: list[dict[str, Any]] = []
    for ref in refs:
        if not isinstance(ref, Mapping):
            continue
        ref_payload: dict[str, Any] = {}
        for key, value in ref.items():
            if type(key) is not str:
                raise ValueError(f"current payload hash payload has non-string keys: {(key,)}")
            if key in _HASH_METADATA_FIELDS:
                continue
            if key == "observed_at_ms" and provider_observed_at_ms is None:
                continue
            ref_payload[key] = value
        source_refs.append(ref_payload)
    return source_refs


def _reject_legacy_json_aliases(snapshot: Mapping[str, Any]) -> None:
    for field in _LEGACY_JSON_ALIAS_FIELDS:
        if field in snapshot:
            raise ValueError(f"cex_detail_snapshot_legacy_json_alias:{field}")


def _provider_observed_at_ms(snapshot: Mapping[str, Any]) -> int | None:
    observed_at_ms = _int_or_none(snapshot.get("observed_at_ms"))
    if observed_at_ms is None:
        return None
    source = _required_observed_at_source(snapshot)
    if source == "provider":
        return observed_at_ms
    if source == "computed":
        return None
    raise ValueError("cex_detail_snapshot_observation_invalid:observed_at_source")


def _required_observed_at_source(snapshot: Mapping[str, Any]) -> str:
    value = snapshot.get("observed_at_source")
    if value is None:
        raise ValueError("cex_detail_snapshot_observation_required:observed_at_source")
    source = str(value).strip().lower()
    if not source:
        raise ValueError("cex_detail_snapshot_observation_required:observed_at_source")
    if source not in _OBSERVED_AT_SOURCE_VALUES:
        raise ValueError("cex_detail_snapshot_observation_invalid:observed_at_source")
    return source


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _rowcount(cursor: Any) -> int:
    try:
        rowcount: object = cursor.rowcount
    except AttributeError as exc:
        raise TypeError("cex_detail_snapshot_rowcount_required") from exc
    if isinstance(rowcount, bool) or not isinstance(rowcount, int):
        raise TypeError("cex_detail_snapshot_rowcount_invalid")
    if rowcount < 0:
        raise TypeError("cex_detail_snapshot_rowcount_invalid")
    return rowcount


def _transaction(conn: Any) -> AbstractContextManager[Any]:
    try:
        transaction = conn.transaction
    except AttributeError as exc:
        raise TypeError("cex_detail_snapshot_transaction_required") from exc
    if not callable(transaction):
        raise TypeError("cex_detail_snapshot_transaction_required")
    return cast(AbstractContextManager[Any], transaction())
