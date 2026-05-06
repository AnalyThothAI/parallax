from __future__ import annotations

import hashlib
import json
from typing import Any


def sync_okx_cex_universe(
    *,
    assets,
    client,
    inst_types: tuple[str, ...] | list[str],
    observed_at_ms: int,
) -> dict[str, Any]:
    normalized_inst_types = [str(inst_type).strip().upper() for inst_type in inst_types if str(inst_type).strip()]
    venues_written = 0
    snapshots_written = 0
    for inst_type in normalized_inst_types:
        for instrument in client.instruments(inst_type=inst_type):
            if str(instrument.state).lower() not in {"live", "preopen", "test"}:
                continue
            assets.upsert_cex_instrument(
                exchange="okx",
                inst_type=instrument.inst_type,
                inst_id=instrument.inst_id,
                base_symbol=instrument.base_symbol,
                quote_symbol=instrument.quote_symbol,
                observed_at_ms=observed_at_ms,
                source_payload_hash=_payload_hash(instrument.raw),
                commit=False,
            )
            venues_written += 1
        for ticker in client.tickers(inst_type=inst_type):
            venue = assets.venue_for_cex_instrument(exchange="okx", inst_type=ticker.inst_type, inst_id=ticker.inst_id)
            if not venue:
                continue
            assets.insert_market_snapshot(
                asset_id=str(venue["asset_id"]),
                venue_id=str(venue["venue_id"]),
                provider="okx_cex",
                observed_at_ms=observed_at_ms,
                price_usd=ticker.last_price,
                volume_24h_usd=ticker.volume_24h,
                open_interest_usd=ticker.open_interest,
                source_payload_hash=_payload_hash(ticker.raw),
                commit=False,
            )
            snapshots_written += 1
    assets.conn.commit()
    return {
        "inst_types": normalized_inst_types,
        "venues_written": venues_written,
        "market_snapshots_written": snapshots_written,
    }


def _payload_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
