from __future__ import annotations

from hashlib import sha256


def market_tick_id(*, target_type: str, target_id: str, source_provider: str, observed_at_ms: int) -> str:
    key = f"{target_type}\x1f{target_id}\x1f{source_provider}\x1f{observed_at_ms}"
    digest = sha256(key.encode("utf-8")).hexdigest()
    return f"market_tick:{digest}"
